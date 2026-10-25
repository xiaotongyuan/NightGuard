"""Rule gate before any LLM call. No pardon for sit + slap."""

from __future__ import annotations

from nightguard.schema import (
    LLM_BUDGET_PER_NIGHT,
    PASS_A_KEYS,
    PASS_A_TRIGGER_MOTIONS,
    TEMP_GATE_C,
)


def gate_reason(
    *,
    temp_c: float,
    posture: str,
    motion_type: str,
    llm_calls_tonight: int,
) -> str | None:
    """Return a fixed English reasoning string if the event must not reach the LLM."""
    if temp_c <= TEMP_GATE_C:
        return "Gated: indoor temp_c<=10. No LLM."
    if posture in ("sit", "off_bed"):
        return "Gated: person already up. No LLM."
    if motion_type == "leave_bed":
        return "Gated: leave_bed. No LLM."
    if posture == "lie_stable" and motion_type == "none":
        return "Gated: settled lie. Lights off. No LLM."
    if motion_type not in PASS_A_TRIGGER_MOTIONS:
        return "Gated: motion not a trigger. No LLM."
    if llm_calls_tonight >= LLM_BUDGET_PER_NIGHT:
        return "Gated: night llm budget. No LLM."
    return None


def gated_pass_a(reasoning: str, *, awake: bool = False) -> dict:
    """Same flat Pass A shape, conservative lights-off."""
    out = {
        "reasoning": reasoning,
        "belief_state": "quiet",
        "belief_p": 0.05,
        "awake": awake,
        "light": "off",
        "mode": "none",
        "brightness": "none",
        "duration_s": 0,
        "aim": "none",
    }
    assert tuple(out.keys()) == PASS_A_KEYS
    return out


def decide_llm(
    *,
    temp_c: float,
    posture: str,
    motion_type: str,
    llm_calls_tonight: int,
) -> tuple[bool, dict | None]:
    """If blocked, return (False, pass_a_dict). If allowed, (True, None)."""
    reason = gate_reason(
        temp_c=temp_c,
        posture=posture,
        motion_type=motion_type,
        llm_calls_tonight=llm_calls_tonight,
    )
    if reason is None:
        return True, None
    awake = posture in ("sit", "off_bed") or motion_type == "leave_bed"
    return False, gated_pass_a(reason, awake=awake)
