"""UI session. Thin wrapper over NightLoop. No extra product rules."""

from __future__ import annotations

import json
from typing import Any

from nightguard.clock import forward_elapsed_min
from nightguard.events import make_event
from nightguard.example_walk import SCRIPT, ExampleWalk
from nightguard.filters import first_hit, parse_filter_line
from nightguard.llm import WATER_IGNORE, FakeLLM, default_pass_a_text
from nightguard.loop import NightLoop
from nightguard.memory import recent_high_weight_cards, render_card_line, render_memory_text
from nightguard.schema import (
    FORBIDDEN_LLM_KEYS,
    MINUTES_PER_DAY,
    MORNING_LABELS,
)

OPEN_CHOICES = (
    "open.scratch.head",
    "open.scratch.left_calf",
    "open.scratch.right_calf",
    "open.scratch.left_foot",
    "open.scratch.right_foot",
    "open.curl.torso",
    "open.sigh.torso",
    "open.slow.torso",
    "open.lie",
    "open.sit",
    "open.leave",
)
FOLLOW_CHOICES = (
    "follow.scratch.plus2",
    "follow.scratch.plus6",
    "follow.sit.plus1",
    "follow.leave.plus1",
    "follow.wait15",
)
ALL_CHOICES = OPEN_CHOICES + FOLLOW_CHOICES

_OPEN_SPEC = {
    "open.scratch.head": {"motion_type": "scratch_burst", "body_zone": "head", "posture": "lie_stable", "dt": 0},
    "open.scratch.left_calf": {"motion_type": "scratch_burst", "body_zone": "left_calf", "posture": "lie_stable", "dt": 0},
    "open.scratch.right_calf": {"motion_type": "scratch_burst", "body_zone": "right_calf", "posture": "lie_stable", "dt": 0},
    "open.scratch.left_foot": {"motion_type": "scratch_burst", "body_zone": "left_foot", "posture": "lie_stable", "dt": 0},
    "open.scratch.right_foot": {"motion_type": "scratch_burst", "body_zone": "right_foot", "posture": "lie_stable", "dt": 0},
    "open.curl.torso": {"motion_type": "curl", "body_zone": "torso", "posture": "lie_stable", "dt": 0},
    "open.sigh.torso": {"motion_type": "sigh_shift", "body_zone": "torso", "posture": "lie_stable", "dt": 0},
    "open.slow.torso": {"motion_type": "slow_roll", "body_zone": "torso", "posture": "lie_stable", "dt": 0},
    "open.lie": {"motion_type": "none", "body_zone": "none", "posture": "lie_stable", "dt": 0},
    "open.sit": {"motion_type": "sit_up", "body_zone": "none", "posture": "sit", "dt": 0},
    "open.leave": {"motion_type": "leave_bed", "body_zone": "none", "posture": "off_bed", "dt": 0},
}

_HARD = (
    ("temp", "temp_c<=10", "temp_c<=10"),
    ("up", "sit|off_bed", "already up"),
    ("leave", "leave_bed", "leave_bed"),
    ("trigger", "not a trigger", "not a trigger"),
    ("settle", "settled lie", "settled lie"),
    ("budget", "night llm budget", "budget"),
)


class UiError(Exception):
    def __init__(self, code: str, status: int = 400) -> None:
        self.code = code
        self.status = status
        super().__init__(code)


def _as_temp(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise UiError("bad_json", 400) from exc


def add_minutes(t: str, minutes: int) -> str:
    parts = t.split(":")
    h, m = int(parts[0]), int(parts[1])
    s = int(parts[2]) if len(parts) > 2 else 0
    total = (h * 60 + m + minutes) % MINUTES_PER_DAY
    return f"{total // 60:02d}:{total % 60:02d}:{s:02d}"


def next_night_id(night_id: str) -> str:
    tail = night_id[1:]
    n = int(tail) if tail.isdigit() else 1
    return f"n{n + 1}"


def _pass_a_text(fixture: str, payload: dict | None = None) -> str:
    if fixture == "off":
        return json.dumps(
            {
                "reasoning": "Low belief. Do not disturb.",
                "belief_state": "quiet",
                "belief_p": 0.2,
                "mode": "none",
            }
        )
    if fixture == "on":
        return json.dumps(
            {
                "reasoning": "Still lying. Scratch burst. Confirm dim.",
                "belief_state": "possible_harassment",
                "belief_p": 0.34,
                "mode": "silent_confirm",
            }
        )
    if fixture == "assist":
        return json.dumps(
            {
                "reasoning": "Prior miss. Assist search.",
                "belief_state": "possible_harassment",
                "belief_p": 0.62,
                "mode": "assist_search",
            }
        )
    return default_pass_a_text(payload)


class FixtureLLM(FakeLLM):
    def __init__(self, pass_a_fixture: str = "default") -> None:
        super().__init__()
        self.pass_a_fixture = pass_a_fixture
        self.morning_override: str | None = None

    def complete(self, kind: str, payload: dict) -> str:
        if kind == "pass_a":
            self.calls.append((kind, payload))
            return _pass_a_text(self.pass_a_fixture, payload)
        if kind == "morning" and self.morning_override is not None:
            self.calls.append((kind, payload))
            text = self.morning_override
            self.morning_override = None
            return json.dumps(
                {
                    "brief": "Local stand-in.",
                    "timeline": "none",
                    "filter_text": text,
                }
            )
        return super().complete(kind, payload)


def _drop_forbidden(data: Any) -> Any:
    if not isinstance(data, dict):
        return data
    return {k: v for k, v in data.items() if k not in FORBIDDEN_LLM_KEYS}


def _lines(text: str) -> list[str]:
    if not text or text == "none":
        return []
    return [ln for ln in text.splitlines() if ln.strip()]


def _soft_diff(before: str, after: str) -> dict:
    old = set(_lines(before))
    new = set(_lines(after))
    return {
        "added": sorted(new - old),
        "removed": sorted(old - new),
        "kept": sorted(old & new),
    }


def _gate_id(reasoning: str) -> str:
    for hid, _text, needle in _HARD:
        if needle in reasoning:
            return hid
    return "none"


def backend_label(llm: Any) -> str:
    """Page word. fake, nano, gemini, hour cap, out of usage, or remote error."""
    if getattr(llm, "out_of_usage", False):
        return "out of usage"
    hourly = getattr(llm, "hourly", None)
    if hourly is not None and hourly.exhausted():
        return "hour cap"
    if getattr(llm, "last_fallback", None):
        return "remote error"
    provider = getattr(llm, "provider", "") or ""
    if provider == "nemotron":
        return "nano"
    if provider == "gemini":
        return "gemini"
    return "fake"


def enabled_choices(window_open: bool) -> list[str]:
    if window_open:
        return list(FOLLOW_CHOICES)
    return list(OPEN_CHOICES)


class UiSession:
    def __init__(
        self,
        mode: str = "inspect",
        temp_c: float = 26.4,
        pass_a_fixture: str = "default",
        filter_text: str = "none",
        llm: Any = None,
        start_example: bool = False,
    ) -> None:
        if mode not in ("inspect", "continue"):
            mode = "inspect"
        self.mode = mode
        self.temp_c = _as_temp(temp_c)
        self.mosquito_draw = "none"
        self.t = "02:00:00"
        self.night_id = "n1"
        self.last_zone = "none"
        self.last_step = {
            "kind": "none",
            "choice_id": "none",
            "llm_called": False,
            "llm_kind": "none",
            "gate_hit": "none",
            "filter_hit": "none",
            "correction": "none",
            "llm_parse_failed": False,
        }
        self.last_llm_input: dict | None = None
        self.last_llm_output: dict | None = None
        self.soft_diff = {"added": [], "removed": [], "kept": []}
        self.llm = llm if llm is not None else FixtureLLM(pass_a_fixture)
        self.llm_backend = backend_label(self.llm)
        self.loop = NightLoop(llm=self.llm)
        self.loop.current_night = self.night_id
        self._install_preset_filter(filter_text)
        self.example = ExampleWalk()
        if start_example:
            self.example.start()

    def _example_morning_due(self) -> bool:
        if self.example.state != "guiding" or self.example.step >= len(SCRIPT):
            return False
        return SCRIPT[self.example.step][0] == "morning"

    def _pin_example_water_ignore(self) -> None:
        """Example night 4 needs ignore, not Nano downweight. Downweight still opens Pass A."""
        self.loop.accept_morning_filter(WATER_IGNORE)
        if self.loop.filter_text != WATER_IGNORE:
            self.loop.filter_text = WATER_IGNORE

    def _install_preset_filter(self, raw: str) -> None:
        """Already-accepted yesterday text: syntax only. Morning still uses accept."""
        if not raw or raw == "none":
            self.loop.filter_text = "none"
            return
        kept = []
        for line in raw.splitlines():
            parsed = parse_filter_line(line)
            if parsed:
                kept.append(parsed["canonical"])
        self.loop.filter_text = "\n".join(kept) if kept else "none"

    def reset_night(self) -> dict:
        self.loop.window.reset()
        self.loop.llm_calls_tonight = 0
        self.loop.pass_a_count = 0
        self.loop.pass_b_count = 0
        self.loop.last_pass_a = None
        self.loop.last_pass_b_input = None
        self.loop.last_action = None
        self.loop.llm_parse_failed = False
        self.t = "02:00:00"
        self.last_zone = "none"
        self.last_step = {
            "kind": "none",
            "choice_id": "none",
            "llm_called": False,
            "llm_kind": "none",
            "gate_hit": "none",
            "filter_hit": "none",
            "correction": "none",
            "llm_parse_failed": False,
        }
        self.last_llm_input = None
        self.last_llm_output = None
        self.example.note("reset_night")
        return self.snapshot()

    def _advance_night(self, *, keep_llm: bool) -> None:
        self.night_id = next_night_id(self.night_id)
        self.loop._reset_night(self.night_id)
        self.loop.last_action = None
        self.loop.last_pass_a = None
        self.loop.last_pass_b_input = None
        self.t = "02:00:00"
        self.last_zone = "none"
        if not keep_llm:
            self.last_llm_input = None
            self.last_llm_output = None
            self.last_step = {
                "kind": "none",
                "choice_id": "none",
                "llm_called": False,
                "llm_kind": "none",
                "gate_hit": "none",
                "filter_hit": "none",
                "correction": "none",
                "llm_parse_failed": False,
            }

    def next_night(self) -> dict:
        self._advance_night(keep_llm=False)
        self.example.note("next_night")
        return self.snapshot()

    def set_ui(self, body: dict) -> dict:
        if "mosquito_draw" in body:
            self.mosquito_draw = str(body["mosquito_draw"] or "none")
        if "temp_c" in body:
            self.temp_c = _as_temp(body["temp_c"])
        if body.get("mode") in ("inspect", "continue"):
            self.mode = body["mode"]
        return self.snapshot()

    def play(self, choice_id: str) -> dict:
        if choice_id not in ALL_CHOICES:
            raise UiError("unknown_choice", 400)
        if self.mode == "inspect" and choice_id.startswith("open."):
            self.reset_night()
        if choice_id not in enabled_choices(self.loop.window.is_open):
            raise UiError("choice_disabled", 409)
        before_open = self.loop.window.is_open
        before_corrected = self.loop.window.already_corrected
        before_a = self.loop.pass_a_count
        before_b = self.loop.pass_b_count
        if choice_id == "follow.wait15":
            self.t = add_minutes(self.t, 15)
            self.loop.advance_clock(self.t)
        else:
            event = self._event_for(choice_id)
            self.t = event["t"]
            self.loop.on_event(event)
        self._record_step(choice_id, before_open, before_corrected, before_a, before_b)
        self.example.note("play", choice_id)
        return self.snapshot()

    def morning(self, morning_label: str = "none", script_filter_text: str | None = None) -> dict:
        if self.loop.window.is_open:
            raise UiError("window_open", 409)
        if morning_label not in MORNING_LABELS:
            raise UiError("unknown_label", 400)
        closed_night = self.night_id
        if morning_label in ("mosquito", "not_mosquito", "unsure"):
            self.loop.apply_morning_label(closed_night, morning_label)
        before = self.loop.filter_text
        pin_water = script_filter_text is None and self._example_morning_due()
        if script_filter_text is not None:
            self.llm.morning_override = script_filter_text
        out = self.loop.run_morning_brief(morning_label=morning_label)
        if out is None:
            raise UiError(self.loop.morning_refused or "morning_refused", 409)
        if pin_water:
            self._pin_example_water_ignore()
        after = self.loop.filter_text
        self.soft_diff = _soft_diff(before, after)
        payload = None
        for kind, item in reversed(self.llm.calls):
            if kind == "morning":
                payload = item
                break
        self.last_llm_input = _drop_forbidden(payload)
        self.last_llm_output = _drop_forbidden(out)
        self.last_step = {
            "kind": "morning",
            "choice_id": "morning",
            "llm_called": True,
            "llm_kind": "morning",
            "gate_hit": "none",
            "filter_hit": "none",
            "correction": "none",
            "llm_parse_failed": bool(self.loop.llm_parse_failed),
        }
        if self.loop.morning_done_night == closed_night:
            self._advance_night(keep_llm=True)
        self.example.note("morning")
        return self.snapshot()

    def label(self, morning_label: str) -> dict:
        if morning_label not in ("mosquito", "not_mosquito", "unsure"):
            raise UiError("unknown_label", 400)
        self.loop.apply_morning_label(self.night_id, morning_label)
        self.last_step = {
            "kind": "label",
            "choice_id": "label",
            "llm_called": False,
            "llm_kind": "none",
            "gate_hit": "none",
            "filter_hit": "none",
            "correction": "none",
            "llm_parse_failed": False,
        }
        return self.snapshot()

    def _event_for(self, choice_id: str) -> dict:
        if choice_id.startswith("open."):
            spec = _OPEN_SPEC[choice_id]
            zone = spec["body_zone"]
            if spec["motion_type"] == "scratch_burst":
                self.last_zone = zone
            posture = spec["posture"]
            motion = spec["motion_type"]
            dt = spec["dt"]
        elif choice_id == "follow.scratch.plus2":
            zone = self.last_zone if self.last_zone != "none" else "left_calf"
            posture, motion, dt = "lie_stable", "scratch_burst", 2
        elif choice_id == "follow.scratch.plus6":
            zone = self.last_zone if self.last_zone != "none" else "left_calf"
            posture, motion, dt = "lie_stable", "scratch_burst", 6
        elif choice_id == "follow.sit.plus1":
            zone, posture, motion, dt = "none", "sit", "sit_up", 1
        elif choice_id == "follow.leave.plus1":
            zone, posture, motion, dt = "none", "off_bed", "leave_bed", 1
        else:
            raise UiError("unknown_choice", 400)
        sound = "slap" if posture == "sit" else "none"
        return make_event(
            night_id=self.night_id,
            t=add_minutes(self.t, dt),
            temp_c=self.temp_c,
            motion_type=motion,
            body_zone=zone,
            posture=posture,
            human_sound=sound,
        )

    def _record_step(
        self,
        choice_id: str,
        before_open: bool,
        before_corrected: bool,
        before_a: int,
        before_b: int,
    ) -> None:
        reasoning = ""
        if self.loop.last_pass_a:
            reasoning = str(self.loop.last_pass_a.get("reasoning", ""))
        kind = "none"
        llm_kind = "none"
        llm_called = False
        gate_hit = "none"
        filter_hit = "none"
        correction = "none"
        if self.loop.pass_b_count > before_b:
            kind = "pass_b"
            llm_called = True
            llm_kind = "pass_b"
            self.last_llm_input = _drop_forbidden(self.loop.last_pass_b_input)
            card = self.loop.memory.cards[-1] if self.loop.memory.cards else None
            self.last_llm_output = (
                _drop_forbidden(
                    {
                        "verdict": card["verdict"],
                        "revised_belief_p": card["revised_belief_p"],
                        "reason": card["reason"],
                    }
                )
                if card
                else None
            )
            if card:
                correction = card.get("correction", "none")
        elif self.loop.window.already_corrected and not before_corrected:
            kind = "upgrade"
            correction = "upgraded_on"
        elif self.loop.pass_a_count > before_a:
            kind = "pass_a"
            llm_called = True
            llm_kind = "pass_a"
            payload = self.loop.pass_a_payloads[-1] if self.loop.pass_a_payloads else None
            self.last_llm_input = _drop_forbidden(payload)
            self.last_llm_output = _drop_forbidden(self.loop.last_pass_a)
        elif self.loop.window.is_open and before_open:
            kind = "follow"
        elif reasoning.startswith("Filtered:"):
            kind = "filtered"
            filter_hit = reasoning.split("Filtered:", 1)[-1].strip()
        elif reasoning.startswith("Gated:"):
            kind = "gated"
            gate_hit = _gate_id(reasoning)
        event = self.loop.log.rows[-1] if self.loop.log.rows else None
        if event and filter_hit == "none":
            hit = first_hit(self.loop.filter_text, event)
            if hit:
                filter_hit = hit["canonical"]
        self.last_step = {
            "kind": kind,
            "choice_id": choice_id,
            "llm_called": llm_called,
            "llm_kind": llm_kind,
            "gate_hit": gate_hit,
            "filter_hit": filter_hit,
            "correction": correction,
            "llm_parse_failed": bool(llm_called and self.loop.llm_parse_failed),
        }

    def snapshot(self) -> dict:
        win = self.loop.window
        pending = win.pending
        if not win.is_open:
            phase = "closed"
            first_light = "none"
            elapsed: int | None = None
        else:
            phase = "upgraded" if win.already_corrected else "watch"
            first_light = pending["pass_a"]["light"] if pending else "none"
            elapsed = forward_elapsed_min(win.window_open_t, self.t) if win.window_open_t else 0
        enabled = enabled_choices(win.is_open)
        disabled = [c for c in ALL_CHOICES if c not in enabled]
        action = self.loop.last_action or {
            "light": "off",
            "mode": "none",
            "brightness": "none",
            "duration_s": 0,
            "aim": "none",
        }
        last_event = self.loop.log.rows[-1] if self.loop.log.rows else None
        person = {
            "posture": last_event["posture"] if last_event else "lie_stable",
            "body_zone": last_event["body_zone"] if last_event else "none",
        }
        reasoning = ""
        if self.loop.last_pass_a:
            reasoning = str(self.loop.last_pass_a.get("reasoning", ""))
        hard = []
        for hid, text, needle in _HARD:
            hit = self.last_step["kind"] == "gated" and needle in reasoning
            hard.append({"id": hid, "text": text, "hit": hit})
        filt = self.loop.filter_text or "none"
        if filt == "none":
            soft = [{"line": "none", "hit": False}]
        else:
            soft = [{"line": ln, "hit": ln == self.last_step["filter_hit"]} for ln in _lines(filt)]
        self.llm_backend = backend_label(self.llm)
        rendered, uncertain = render_memory_text(self.loop.memory.cards, current_event=None, filter_text=filt)
        habit = "\n".join(ln for ln in rendered.splitlines() if ln.startswith("habit:")) or "none"
        cards = [render_card_line(c) for c in recent_high_weight_cards(self.loop.memory.cards, filt)]
        return {
            "mode": self.mode,
            "llm_backend": self.llm_backend,
            "night_id": self.night_id,
            "t": self.t,
            "temp_c": self.temp_c,
            "mosquito_draw": self.mosquito_draw,
            "window": {
                "open": win.is_open,
                "phase": phase,
                "first_light": first_light,
                "already_corrected": win.already_corrected,
                "elapsed_min": elapsed,
            },
            "budget": {
                "llm_calls_tonight": self.loop.llm_calls_tonight,
                "pass_a_count": self.loop.pass_a_count,
                "pass_b_count": self.loop.pass_b_count,
                "morning_llm_calls": self.loop.morning_llm_calls,
            },
            "enabled_choices": enabled,
            "disabled_choices": disabled,
            "last_step": dict(self.last_step),
            "llm": {
                "input": self.last_llm_input,
                "output": self.last_llm_output,
                "remote": getattr(self.llm, "last_remote", None) if self.last_llm_input else None,
                "hourly": self.llm.hourly.status() if getattr(self.llm, "hourly", None) else None,
                "fallback": getattr(self.llm, "last_fallback", None),
            },
            "action": dict(action),
            "person": person,
            "rules": {
                "hard": hard,
                "soft": soft,
                "soft_diff": dict(self.soft_diff),
            },
            "memory": {
                "cards": cards,
                "habit_text": habit,
                "uncertain_count": uncertain,
                "filter_text": filt,
            },
            "morning": self.loop.last_morning,
            "example": self.example.view(),
        }
