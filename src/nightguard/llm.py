"""Parse LLM JSON, then sanitize. Never return json.loads alone."""

from __future__ import annotations

import json
import math
from typing import Callable, Protocol

from nightguard.schema import (
    BELIEF_STATES,
    FORBIDDEN_LLM_KEYS,
    MODES,
    MORNING_OUTPUT_KEYS,
    PASS_A_KEYS,
    PASS_A_MODEL_KEYS,
    PASS_B_OUTPUT_KEYS,
    VERDICTS,
    AIM_FROM_ZONE,
)


def fallback_pass_a(event: dict) -> dict:
    awake = event.get("posture", "lie_stable") != "lie_stable"
    return {
        "reasoning": "parse_failed. Conservative default.",
        "belief_state": "quiet",
        "belief_p": 0.2,
        "awake": awake,
        "light": "off",
        "mode": "none",
        "brightness": "none",
        "duration_s": 0,
        "aim": "none",
    }


def sanitize_pass_a(event: dict, parsed: dict, active_filter: str = "none") -> dict:
    """Code wins over the model. Must run after every successful parse."""
    out = {k: parsed[k] for k in PASS_A_MODEL_KEYS}
    out["awake"] = event.get("posture", "lie_stable") != "lie_stable"
    zone = event.get("body_zone", "none")
    if out["mode"] == "none":
        out["light"] = "off"
        out["brightness"] = "none"
        out["duration_s"] = 0
        out["aim"] = "none"
    elif out["mode"] == "silent_confirm":
        out["light"] = "on"
        out["brightness"] = "very_low"
        out["duration_s"] = 4
        out["aim"] = AIM_FROM_ZONE.get(zone, "none")
    else:
        out["light"] = "on"
        out["brightness"] = "medium"
        out["duration_s"] = 6
        out["aim"] = AIM_FROM_ZONE.get(zone, "none")
    if isinstance(active_filter, str) and active_filter.startswith("downweight"):
        try:
            out["belief_p"] = min(float(out.get("belief_p", 0.0)), 0.3)
        except (TypeError, ValueError):
            out["belief_p"] = 0.3
        if out.get("mode") == "assist_search":
            out["mode"] = "silent_confirm"
            out["brightness"] = "very_low"
            out["duration_s"] = 4
    return {k: out[k] for k in PASS_A_KEYS}


def _is_flat_object(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    return all(not isinstance(v, (dict, list)) for v in value.values())


def parse_pass_a_json(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        raise ValueError("markdown fence")
    data = json.loads(text)
    if not _is_flat_object(data):
        raise ValueError("nested or not an object")
    extra = set(data) - set(PASS_A_MODEL_KEYS)
    missing = set(PASS_A_MODEL_KEYS) - set(data)
    if extra or missing:
        raise ValueError(f"keys extra={extra} missing={missing}")
    if any(k in data for k in FORBIDDEN_LLM_KEYS):
        raise ValueError("forbidden key")
    if data["belief_state"] not in BELIEF_STATES:
        raise ValueError("belief_state")
    if data["mode"] not in MODES:
        raise ValueError("mode")
    if not isinstance(data["reasoning"], str) or "\n" in data["reasoning"]:
        raise ValueError("reasoning")
    belief_p = float(data["belief_p"])
    if not math.isfinite(belief_p) or not 0.0 <= belief_p <= 1.0:
        raise ValueError("belief_p")
    return data


def parse_morning_json(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        raise ValueError("markdown fence")
    data = json.loads(text)
    if not _is_flat_object(data):
        raise ValueError("nested or not an object")
    if set(data) != set(MORNING_OUTPUT_KEYS):
        raise ValueError("morning keys")
    if any(k in data for k in FORBIDDEN_LLM_KEYS):
        raise ValueError("forbidden key")
    for key in MORNING_OUTPUT_KEYS:
        if not isinstance(data[key], str):
            raise ValueError(key)
        if "\n" in data[key] and key != "filter_text":
            raise ValueError(f"{key} must be one line")
    return data


def fallback_morning(payload: dict) -> dict:
    return {
        "brief": "parse_failed. Conservative default.",
        "timeline": "none",
        "filter_text": payload.get("yesterday_filter") or "none",
    }


def has_forbidden_keys(data: dict) -> bool:
    return any(k in data for k in FORBIDDEN_LLM_KEYS)


def parse_pass_b_json(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        raise ValueError("markdown fence")
    data = json.loads(text)
    if not _is_flat_object(data):
        raise ValueError("nested or not an object")
    if set(data) != set(PASS_B_OUTPUT_KEYS):
        raise ValueError("pass b keys")
    if data["verdict"] not in VERDICTS:
        raise ValueError("verdict")
    revised = float(data["revised_belief_p"])
    if not math.isfinite(revised) or not 0.0 <= revised <= 1.0:
        raise ValueError("revised_belief_p")
    if not isinstance(data["reason"], str) or "\n" in data["reason"]:
        raise ValueError("reason")
    return data


def sanitize_pass_b(payload: dict, parsed: dict) -> dict:
    """Keep deterministic Pass B contract rules out of model control."""
    out = {k: parsed[k] for k in PASS_B_OUTPUT_KEYS}
    if payload.get("outcome_15min") == "no_new_event":
        out["verdict"] = "inconclusive"
    return out


def default_pass_a_text(payload: dict | None = None) -> str:
    payload = payload or {}
    motion = payload.get("motion_type")
    memory_lines = str(payload.get("memory_text") or "").splitlines()
    same_motion_not_mosquito = any(
        (
            f"motion_type: {motion} " in line
            and "morning_label: not_mosquito" in line
        )
        or f"habit: {motion} morning not_mosquito" in line
        for line in memory_lines
    )
    if same_motion_not_mosquito:
        return json.dumps(
            {
                "reasoning": "Same motion was marked not_mosquito. Keep the light off.",
                "belief_state": "quiet",
                "belief_p": 0.1,
                "mode": "none",
            }
        )
    if motion == "sigh_shift":
        return json.dumps(
            {
                "reasoning": "Still lying. Sigh shift. Observe without light.",
                "belief_state": "quiet",
                "belief_p": 0.18,
                "mode": "none",
            }
        )
    return json.dumps(
        {
            "reasoning": "Still lying. Scratch burst. Low belief.",
            "belief_state": "possible_harassment",
            "belief_p": 0.34,
            "mode": "silent_confirm",
        }
    )


WATER_IGNORE = "ignore ~01:55-02:15 motion sigh_shift"
SCRATCH_IGNORE = "ignore motion scratch_burst"


def suggested_morning_filter(payload: dict) -> str:
    """Legal demo line when yesterday is empty and a habit already exists."""
    yesterday = payload.get("yesterday_filter") or "none"
    if yesterday != "none":
        return yesterday
    habit = payload.get("habit_text") or ""
    if "outcome_15min=left_bed" in habit:
        return WATER_IGNORE
    if "scratch_burst morning not_mosquito" in habit:
        return SCRATCH_IGNORE
    return "none"


def default_morning_text(payload: dict) -> str:
    return json.dumps(
        {
            "brief": "Night seed: local stand-in. No remote call.",
            "timeline": "none",
            "filter_text": suggested_morning_filter(payload),
        }
    )


def default_pass_b_text(payload: dict) -> str:
    outcome = payload.get("outcome_15min", "settled_lie")
    later_motion = payload.get("later_motion_type", "none")
    later_posture = payload.get("later_posture", "lie_stable")
    if outcome == "no_new_event":
        verdict = "inconclusive"
        belief = 0.25
    elif outcome in ("sat_up", "scratch_again_after_5m"):
        verdict = "too_weak"
        belief = 0.62
    elif outcome == "settled_lie" and payload.get("light") == "on":
        verdict = "too_strong"
        belief = 0.2
    elif outcome == "left_bed" and payload.get("light") == "on":
        verdict = "inconclusive"
        belief = 0.4
    else:
        verdict = "appropriate"
        belief = 0.4
    reason = (
        f"outcome_15min={outcome}; later_posture={later_posture}; "
        f"later_motion_type={later_motion}."
    )
    return json.dumps(
        {
            "verdict": verdict,
            "revised_belief_p": belief,
            "reason": reason,
        }
    )


class LLMClient(Protocol):
    def complete(self, kind: str, payload: dict) -> str: ...


class FakeLLM:
    """Deterministic stand-in. No network."""

    def __init__(self, script: list[str] | None = None) -> None:
        self.script = list(script or [])
        self.calls: list[tuple[str, dict]] = []

    def complete(self, kind: str, payload: dict) -> str:
        self.calls.append((kind, payload))
        if self.script:
            return self.script.pop(0)
        if kind == "pass_a":
            return default_pass_a_text(payload)
        if kind == "morning":
            return default_morning_text(payload)
        return default_pass_b_text(payload)


def _pays_remote(client: object, kind: str) -> bool:
    """True when the next complete() for this kind would open an HTTP bill."""
    if not hasattr(client, "encode"):
        return False
    if getattr(client, "out_of_usage", False):
        return False
    kinds = getattr(client, "remote_kinds", None)
    if kinds is not None and kind not in kinds:
        return False
    hourly = getattr(client, "hourly", None)
    if hourly is not None and hourly.exhausted():
        return False
    return True


def invoke(
    client: LLMClient,
    kind: str,
    payload: dict,
    event: dict,
    active_filter: str = "none",
    complete: Callable[..., str] | None = None,
) -> tuple[dict, int, bool]:
    """Parse, retry once locally, sanitize. A remote kind is not paid twice."""
    complete = complete or client.complete
    last_error: Exception | None = None
    attempts = 0
    tries = 1 if _pays_remote(client, kind) else 2
    for _ in range(tries):
        attempts += 1
        raw = complete(kind, payload)
        try:
            if kind == "pass_a":
                parsed = parse_pass_a_json(raw)
                return sanitize_pass_a(event, parsed, active_filter), attempts, False
            if kind == "morning":
                return parse_morning_json(raw), attempts, False
            parsed_b = parse_pass_b_json(raw)
            return sanitize_pass_b(payload, parsed_b), attempts, False
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            last_error = exc
    if kind == "pass_a":
        return fallback_pass_a(event), attempts, True
    if kind == "morning":
        return fallback_morning(payload), attempts, True
    return (
        {
            "verdict": "inconclusive",
            "revised_belief_p": 0.2,
            "reason": f"parse_failed. outcome_15min={payload.get('outcome_15min')} later_motion_type={payload.get('later_motion_type')}.",
        },
        attempts,
        True,
    )
