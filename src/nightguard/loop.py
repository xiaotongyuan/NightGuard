"""Main night loop: window first, then hard gate, then filter, then Pass A."""

from __future__ import annotations

from nightguard import action, gates, prompts
from nightguard.filters import accept_filter_text, first_hit
from nightguard.llm import FakeLLM, LLMClient, invoke
from nightguard.log import EventLog
from nightguard.memory import MemoryStore, clock_clusters, make_card, morning_habit_motions, render_memory_text
from nightguard.scheduler import (
    WindowState,
    maybe_timeout,
    on_follow_event,
    open_window,
    restart_after_upgrade,
)


class NightLoop:
    def __init__(self, llm: LLMClient | None = None) -> None:
        self.llm = llm or FakeLLM()
        self.window = WindowState()
        self.memory = MemoryStore()
        self.log = EventLog()
        self.filter_text = "none"
        self.llm_calls_tonight = 0
        self.current_night: str | None = None
        self.pass_a_count = 0
        self.pass_b_count = 0
        self.total_llm_calls = 0
        self.last_pass_a: dict | None = None
        self.last_pass_b_input: dict | None = None
        self.last_action: dict | None = None
        self.llm_parse_failed = False
        self.pass_a_payloads: list[dict] = []
        self.morning_llm_calls = 0
        self.morning_done_night: str | None = None
        self.last_morning: dict | None = None
        self.morning_refused: str | None = None

    def _reset_night(self, night_id: str) -> None:
        if self.window.is_open:
            self.window.reset()
        self.llm_calls_tonight = 0
        self.current_night = night_id
        self.pass_a_count = 0
        self.pass_b_count = 0

    def _run_pass_b(self, outcome_15min: str, later_event: dict | None) -> None:
        pending = self.window.pending
        assert pending is not None
        payload = prompts.pass_b_input(pending, outcome_15min, later_event)
        self.last_pass_b_input = payload
        result, attempts, failed = invoke(self.llm, "pass_b", payload, pending["event"])
        self.llm_calls_tonight += attempts
        self.total_llm_calls += attempts
        self.pass_b_count += 1
        self.llm_parse_failed = failed
        card = make_card(
            event=pending["event"],
            pass_a=pending["pass_a"],
            pass_b=result,
            outcome_15min=outcome_15min,
            correction_action=pending.get("correction"),
        )
        self.memory.add_card(card)
        self.window.reset()

    def _flush_timeout(self, now_t: str) -> None:
        decision = maybe_timeout(self.window, now_t)
        if decision and decision.is_pass_b:
            self._run_pass_b(decision.outcome_15min, decision.later_event)

    def _lights_off(self, reasoning: str, event: dict) -> dict:
        awake = event["posture"] != "lie_stable" or event["motion_type"] == "leave_bed"
        out = gates.gated_pass_a(reasoning, awake=awake)
        self.last_pass_a = out
        self.last_action = action.apply_pass_a(out)
        return out

    def _run_pass_a(self, event: dict, active_filter: str) -> dict:
        memory_text, uncertain = render_memory_text(
            self.memory.cards,
            current_event=event,
        )
        payload = prompts.pass_a_input(event, memory_text, uncertain, active_filter)
        self.pass_a_payloads.append(payload)
        result, attempts, failed = invoke(
            self.llm,
            "pass_a",
            payload,
            event,
            active_filter=active_filter,
        )
        self.llm_calls_tonight += attempts
        self.total_llm_calls += attempts
        self.pass_a_count += 1
        self.llm_parse_failed = failed
        self.last_pass_a = result
        self.last_action = action.apply_pass_a(result)
        open_window(self.window, event, result)
        return result

    def on_event(self, event: dict) -> dict | None:
        self.log.append(event)
        if self.current_night is None:
            self.current_night = event["night_id"]
        elif event["night_id"] != self.current_night:
            self._reset_night(event["night_id"])

        self._flush_timeout(event["t"])

        if self.window.is_open:
            decision = on_follow_event(self.window, event)
            if decision.confirm_harass:
                first = self.window.pending["pass_a"] if self.window.pending else {}
                if first.get("light") == "off" and not self.window.already_corrected:
                    upgraded = action.corrective_upgrade(event, first)
                    restart_after_upgrade(self.window, event, upgraded)
                    self.last_action = action.apply_pass_a(upgraded)
                    return upgraded
                self._run_pass_b("scratch_again_after_5m", decision.later_event)
                return None
            if decision.is_pass_b:
                self._run_pass_b(decision.outcome_15min, decision.later_event)
            return None

        allowed, gated = gates.decide_llm(
            temp_c=event["temp_c"],
            posture=event["posture"],
            motion_type=event["motion_type"],
            llm_calls_tonight=self.llm_calls_tonight,
        )
        if not allowed:
            return self._lights_off(gated["reasoning"], event)

        hit = first_hit(self.filter_text, event)
        if hit and hit["opcode"] == "ignore":
            return self._lights_off(f"Filtered: {hit['canonical']}", event)

        active = hit["canonical"] if hit and hit["opcode"] == "downweight" else "none"
        return self._run_pass_a(event, active)

    def advance_clock(self, now_t: str) -> None:
        self._flush_timeout(now_t)

    def apply_morning_label(self, night_id: str, label: str) -> None:
        self.memory.apply_morning_label(night_id, label)

    def run_morning_brief(self, morning_label: str = "none", now_t: str | None = None) -> dict | None:
        """Out of the night loop. Not a window timer. Does not spend the night 6."""
        if now_t:
            self._flush_timeout(now_t)
        if self.window.is_open:
            self.morning_refused = "window_open"
            return None
        night = self.current_night or "n1"
        if self.morning_done_night == night:
            self.morning_refused = "already_done"
            return self.last_morning
        cards_this_night = [c for c in self.memory.cards if c["night_id"] == night]
        habit_text, _ = render_memory_text(self.memory.cards, current_event=None)
        habit_only = "\n".join(
            ln for ln in habit_text.splitlines() if ln.startswith("habit:")
        ) or "none"
        last_night_text = "\n".join(
            f"{c['night_id']} {c['t'][:5]} | motion_type: {c['motion_type']} ({c['body_zone']}) | "
            f"outcome_15min: {c['outcome_15min']} | first_light: {c.get('first_light', c['light'])} | "
            f"correction: {c.get('correction', 'none')} | response_verdict: {c['verdict']} | "
            f"morning_label: {c['morning_label']}"
            for c in cards_this_night
        ) or "none"
        payload = prompts.morning_input(
            night,
            habit_only,
            last_night_text,
            self.filter_text,
            morning_label,
        )
        result, attempts, failed = invoke(self.llm, "morning", payload, {})
        self.morning_llm_calls += attempts
        self.llm_parse_failed = failed
        kept = self.accept_morning_filter(result["filter_text"])
        result = dict(result)
        result["filter_text"] = kept
        self.last_morning = result
        self.morning_done_night = night
        self.morning_refused = None
        return result

    def accept_morning_filter(self, raw: str) -> str:
        clusters = clock_clusters(self.memory.cards)
        motions = morning_habit_motions(self.memory.cards, "not_mosquito")
        self.filter_text = accept_filter_text(
            raw,
            clusters,
            motions,
            yesterday=self.filter_text,
        )
        return self.filter_text
