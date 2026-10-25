"""Event dict helpers. Flat golden keys, no nesting."""

from __future__ import annotations

from nightguard.schema import EVENT_KEYS


def make_event(**overrides) -> dict:
    event = {
        "night_id": "n1",
        "t": "02:15:00",
        "temp_c": 26.4,
        "rain_mm_24h": 0.0,
        "humidity": 60,
        "motion_type": "scratch_burst",
        "body_zone": "left_calf",
        "amp": 0.31,
        "duration_s": 4.2,
        "centroid_shift": 0.08,
        "human_sound": "none",
        "posture": "lie_stable",
    }
    event.update(overrides)
    missing = [k for k in EVENT_KEYS if k not in event]
    if missing:
        raise KeyError(f"event missing {missing}")
    return {k: event[k] for k in EVENT_KEYS}


def hhmm(t: str) -> str:
    return t[:5]
