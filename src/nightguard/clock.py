"""Clock helpers. elapsed_min is forward; clock_arc_min is shortest arc."""

from __future__ import annotations

from nightguard.schema import MINUTES_PER_DAY


def minutes_from_midnight(t: str) -> int:
    parts = t.split(":")
    return int(parts[0]) * 60 + int(parts[1])


def format_hhmm(minutes: int) -> str:
    minutes = minutes % MINUTES_PER_DAY
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def forward_elapsed_min(start_t: str, end_t: str) -> int:
    """Observation-window elapsed time. Forward across midnight. Not shortest arc."""
    a = minutes_from_midnight(start_t)
    b = minutes_from_midnight(end_t)
    return (b - a) % MINUTES_PER_DAY


def clock_arc_min(a: str | int, b: str | int) -> int:
    """Shortest arc in minutes. Shared by habit clustering and filter intervals."""
    if isinstance(a, str):
        a = minutes_from_midnight(a)
    if isinstance(b, str):
        b = minutes_from_midnight(b)
    fwd = (b - a) % MINUTES_PER_DAY
    return min(fwd, MINUTES_PER_DAY - fwd)


def circular_median_minutes(values: list[int]) -> int:
    """Median on the 24h circle: cut at the largest gap, then linear median."""
    if not values:
        raise ValueError("empty clock sample")
    ordered = sorted(m % MINUTES_PER_DAY for m in values)
    n = len(ordered)
    if n == 1:
        return ordered[0]
    best_gap = -1
    cut = n - 1
    for i in range(n - 1):
        gap = ordered[i + 1] - ordered[i]
        if gap > best_gap:
            best_gap = gap
            cut = i
    wrap_gap = ordered[0] + MINUTES_PER_DAY - ordered[-1]
    if wrap_gap > best_gap:
        cut = n - 1
    unwrapped = [m + MINUTES_PER_DAY for m in ordered[: cut + 1]] + ordered[cut + 1 :]
    unwrapped.sort()
    if n % 2:
        return unwrapped[n // 2] % MINUTES_PER_DAY
    return ((unwrapped[n // 2 - 1] + unwrapped[n // 2]) // 2) % MINUTES_PER_DAY


def time_on_shortest_arc(t: str | int, a: str | int, b: str | int) -> bool:
    """Closed interval on the shorter arc between a and b."""
    tm = minutes_from_midnight(t) if isinstance(t, str) else t
    ta = minutes_from_midnight(a) if isinstance(a, str) else a
    tb = minutes_from_midnight(b) if isinstance(b, str) else b
    return clock_arc_min(ta, tm) + clock_arc_min(tm, tb) == clock_arc_min(ta, tb)


def walk_shortest_arc(a_min: int, b_min: int) -> list[int]:
    fwd = (b_min - a_min) % MINUTES_PER_DAY
    back = (a_min - b_min) % MINUTES_PER_DAY
    if fwd <= back:
        return [(a_min + i) % MINUTES_PER_DAY for i in range(fwd + 1)]
    return [(a_min - i) % MINUTES_PER_DAY for i in range(back + 1)]
