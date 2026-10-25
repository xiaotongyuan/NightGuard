"""S4 is written first. Scratch before 5 minutes must not close the window."""

from nightguard.events import make_event
from nightguard.scheduler import WindowState, maybe_timeout, on_follow_event, open_window
from tests.helpers import add_minutes

OPEN_T = "02:00:00"


def _open(pass_a=None) -> WindowState:
    state = WindowState()
    event = make_event(t=OPEN_T)
    open_window(state, event, pass_a or {"belief_state": "possible_harassment", "belief_p": 0.3, "light": "on", "mode": "silent_confirm"})
    return state


def test_S4_second_scratch_at_2min_keeps_window_open():
    state = _open()
    follow = make_event(t=add_minutes(OPEN_T, 2), motion_type="scratch_burst", posture="lie_stable")
    decision = on_follow_event(state, follow)
    assert decision.window_open is True
    assert decision.is_pass_b is False
    assert decision.outcome_15min != "scratch_again_after_5m"
    assert decision.outcome_15min is None
    assert state.is_open is True
    assert follow in state.follow_events


def test_S4b_early_scratch_times_out_as_settled_lie():
    state = _open()
    follow = make_event(t=add_minutes(OPEN_T, 2), motion_type="scratch_burst", posture="lie_stable")
    on_follow_event(state, follow)
    decision = maybe_timeout(state, add_minutes(OPEN_T, 15))
    assert decision is not None
    assert decision.is_pass_b is True
    assert decision.outcome_15min == "settled_lie"
    assert decision.later_event["motion_type"] == "none"


def test_S5b_scratch_after_5min_still_in_window_times_out_as_scratch_again_after_5m():
    state = _open()
    follow = make_event(t=add_minutes(OPEN_T, 6), motion_type="scratch_burst", posture="lie_stable")
    kept = on_follow_event(state, follow)
    assert kept.confirm_harass is True
    assert state.is_open is True
    decision = maybe_timeout(state, add_minutes(OPEN_T, 15))
    assert decision is not None
    assert decision.outcome_15min == "scratch_again_after_5m"
    assert decision.later_event["motion_type"] == "scratch_burst"


def test_S1_opening_is_not_pass_b():
    state = WindowState()
    event = make_event(t=OPEN_T, motion_type="scratch_burst")
    decision = open_window(state, event, {"belief_state": "quiet", "belief_p": 0.2, "light": "off", "mode": "none"})
    assert state.is_open is True
    assert decision.is_pass_b is False
    assert decision.new_pass_a is True


def test_S2_sit_without_slap_is_sat_up():
    state = _open()
    follow = make_event(t=add_minutes(OPEN_T, 1), posture="sit", motion_type="sit_up", human_sound="none")
    decision = on_follow_event(state, follow)
    assert decision.is_pass_b is True
    assert decision.outcome_15min == "sat_up"
    assert decision.window_open is False


def test_S3_leave_bed_is_left_bed():
    state = _open()
    follow = make_event(t=add_minutes(OPEN_T, 1), motion_type="leave_bed", posture="off_bed")
    decision = on_follow_event(state, follow)
    assert decision.outcome_15min == "left_bed"
    assert decision.is_pass_b is True


def test_S5_scratch_after_6min_is_confirm_harass_scheduler_does_not_close():
    state = _open()
    follow = make_event(t=add_minutes(OPEN_T, 6), motion_type="scratch_burst", posture="lie_stable")
    decision = on_follow_event(state, follow)
    assert decision.confirm_harass is True
    assert decision.outcome_15min == "scratch_again_after_5m"
    assert decision.is_pass_b is False
    assert decision.window_open is True
    assert state.is_open is True


def test_S6_empty_follow_times_out_to_no_new_event():
    state = _open()
    decision = maybe_timeout(state, add_minutes(OPEN_T, 15))
    assert decision is not None
    assert decision.outcome_15min == "no_new_event"
    assert decision.is_pass_b is True


def test_S7_only_slow_roll_is_settled_lie():
    state = _open()
    follow = make_event(t=add_minutes(OPEN_T, 3), motion_type="slow_roll", posture="lie_stable")
    kept = on_follow_event(state, follow)
    assert kept.window_open is True
    decision = maybe_timeout(state, add_minutes(OPEN_T, 15))
    assert decision is not None
    assert decision.outcome_15min == "settled_lie"


def test_S8_sit_while_open_goes_to_follow_not_gate():
    state = _open()
    follow = make_event(t=add_minutes(OPEN_T, 1), posture="sit", motion_type="sit_up")
    decision = on_follow_event(state, follow)
    assert follow in state.follow_events
    assert decision.new_pass_a is False
    assert decision.outcome_15min == "sat_up"
