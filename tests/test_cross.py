from nightguard.events import make_event
from nightguard.prompts import pass_b_input
from nightguard.schema import (
    BELIEF_STATES,
    CORRECTIONS,
    HUMAN_SOUNDS,
    LIGHTS,
    MOTION_TYPES,
    OUTCOMES_15MIN,
    PASS_B_INPUT_KEYS,
    POSTURES,
)

LATER = {
    "settled_lie": {"posture": "lie_stable", "motion_type": "slow_roll", "human_sound": "none"},
    "sat_up": {"posture": "sit", "motion_type": "sit_up", "human_sound": "slap"},
    "left_bed": {"posture": "off_bed", "motion_type": "leave_bed", "human_sound": "footsteps"},
    "scratch_again_after_5m": {"posture": "lie_stable", "motion_type": "scratch_burst", "human_sound": "sheet_rustle"},
    "no_new_event": {"posture": "lie_stable", "motion_type": "none", "human_sound": "none"},
}


def test_twenty_cells_are_legal_pass_b_inputs():
    built = 0
    for belief in BELIEF_STATES:
        for outcome in OUTCOMES_15MIN:
            pending = {
                "event": make_event(),
                "pass_a": {
                    "belief_state": belief,
                    "belief_p": 0.34,
                    "light": "on",
                    "mode": "silent_confirm",
                },
            }
            payload = pass_b_input(pending, outcome, LATER[outcome])
            assert tuple(payload) == PASS_B_INPUT_KEYS
            assert payload["belief_state"] == belief
            assert payload["outcome_15min"] == outcome
            assert payload["later_posture"] in POSTURES
            assert payload["later_motion_type"] in MOTION_TYPES
            assert payload["later_human_sound"] in HUMAN_SOUNDS
            assert payload["first_light"] in LIGHTS
            assert payload["correction"] in CORRECTIONS
            built += 1
    assert built == 20
