"""No hardware. Record the current light fields for the UI."""

from __future__ import annotations

from nightguard.llm import sanitize_pass_a


def apply_pass_a(pass_a: dict) -> dict:
    return {
        "light": pass_a["light"],
        "mode": pass_a["mode"],
        "brightness": pass_a["brightness"],
        "duration_s": pass_a["duration_s"],
        "aim": pass_a["aim"],
    }


def corrective_upgrade(event: dict, first_pass_a: dict) -> dict:
    """One in-window off→on. Code only. Not a Pass A and not an LLM call."""
    try:
        belief = max(float(first_pass_a.get("belief_p", 0.2)), 0.6)
    except (TypeError, ValueError):
        belief = 0.6
    draft = {
        "reasoning": "Corrected: first light off, later lying scratch_burst. Assist now.",
        "belief_state": "possible_harassment",
        "belief_p": belief,
        "mode": "assist_search",
    }
    return sanitize_pass_a(event, draft)
