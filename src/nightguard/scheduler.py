"""Observation window. Compute elapsed_min before any scratch-to-close rule."""

from __future__ import annotations

from dataclasses import dataclass, field

from nightguard.clock import forward_elapsed_min
from nightguard.schema import LOW_INTENSITY_MOTIONS, WINDOW_MAX_MIN, WINDOW_MIN


@dataclass
class WindowState:
    pending: dict | None = None
    window_open_t: str | None = None
    follow_events: list = field(default_factory=list)
    already_corrected: bool = False

    @property
    def is_open(self) -> bool:
        return self.window_open_t is not None

    def reset(self) -> None:
        self.pending = None
        self.window_open_t = None
        self.follow_events = []
        self.already_corrected = False


@dataclass
class SchedulerDecision:
    window_open: bool
    is_pass_b: bool
    outcome_15min: str | None = None
    later_event: dict | None = None
    new_pass_a: bool = False
    confirm_harass: bool = False


def open_window(state: WindowState, event: dict, pass_a: dict) -> SchedulerDecision:
    state.pending = {"event": event, "pass_a": pass_a}
    state.window_open_t = event["t"]
    state.follow_events = []
    state.already_corrected = False
    return SchedulerDecision(window_open=True, is_pass_b=False, new_pass_a=True)


def restart_after_upgrade(state: WindowState, event: dict, correction: dict) -> None:
    assert state.pending is not None
    state.pending["correction"] = correction
    state.already_corrected = True
    state.window_open_t = event["t"]
    state.follow_events = []


def _interrupt_outcome(event: dict) -> str | None:
    if event["motion_type"] == "leave_bed" or event["posture"] == "off_bed":
        return "left_bed"
    if event["posture"] == "sit":
        return "sat_up"
    return None


def _elapsed(state: WindowState, event: dict) -> int:
    return forward_elapsed_min(state.window_open_t, event["t"])


def _timeout_outcome(state: WindowState) -> tuple[str, dict]:
    """15-minute label. A scratch before minute 5 stays in the opening bout."""
    follows = state.follow_events
    dummy = {"posture": "lie_stable", "motion_type": "none", "human_sound": "none"}
    if not follows or all(e["motion_type"] == "none" for e in follows):
        return "no_new_event", follows[-1] if follows else dummy
    counted = [
        event
        for event in follows
        if not (
            event["motion_type"] == "scratch_burst"
            and _elapsed(state, event) < WINDOW_MIN
        )
    ]
    if not counted or all(event["motion_type"] == "none" for event in counted):
        return "settled_lie", dummy
    if all(event["motion_type"] in LOW_INTENSITY_MOTIONS for event in counted):
        return "settled_lie", counted[-1]
    later_scratch = [
        event
        for event in counted
        if event["motion_type"] == "scratch_burst"
        and event.get("posture") == "lie_stable"
        and _elapsed(state, event) >= WINDOW_MIN
    ]
    if later_scratch:
        return "scratch_again_after_5m", later_scratch[-1]
    return "settled_lie", counted[-1]


def on_follow_event(state: WindowState, event: dict) -> SchedulerDecision:
    """Window is already open. Always record the event. Never open a new Pass A."""
    if not state.is_open:
        raise RuntimeError("on_follow_event requires an open window")
    state.follow_events.append(event)
    elapsed = forward_elapsed_min(state.window_open_t, event["t"])

    interrupt = _interrupt_outcome(event)
    if interrupt is not None:
        return SchedulerDecision(
            window_open=False,
            is_pass_b=True,
            outcome_15min=interrupt,
            later_event=event,
        )

    if WINDOW_MIN <= elapsed < WINDOW_MAX_MIN:
        if event["motion_type"] == "scratch_burst" and event["posture"] == "lie_stable":
            return SchedulerDecision(
                window_open=True,
                is_pass_b=False,
                outcome_15min="scratch_again_after_5m",
                later_event=event,
                confirm_harass=True,
            )

    if elapsed >= WINDOW_MAX_MIN:
        outcome, later = _timeout_outcome(state)
        return SchedulerDecision(
            window_open=False,
            is_pass_b=True,
            outcome_15min=outcome,
            later_event=later,
        )

    return SchedulerDecision(window_open=True, is_pass_b=False)


def maybe_timeout(state: WindowState, now_t: str) -> SchedulerDecision | None:
    if not state.is_open:
        return None
    elapsed = forward_elapsed_min(state.window_open_t, now_t)
    if elapsed < WINDOW_MAX_MIN:
        return None
    outcome, later = _timeout_outcome(state)
    return SchedulerDecision(
        window_open=False,
        is_pass_b=True,
        outcome_15min=outcome,
        later_event=later,
    )
