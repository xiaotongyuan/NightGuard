"""Morning filter grammar. Regex only. No split() tokenizing."""

from __future__ import annotations

import re

from nightguard.clock import (
    clock_arc_min,
    minutes_from_midnight,
    time_on_shortest_arc,
    walk_shortest_arc,
)
from nightguard.schema import FILTER_MAX_LINES, FILTER_MAX_SPAN_MIN, HABIT_CLOCK_TOLERANCE_MIN

_WS = re.compile(r"\s+")
_MOTION = r"(scratch_burst|curl|sigh_shift)"
_TIMED = re.compile(
    rf"^(ignore|downweight) ~([01]\d|2[0-3]):([0-5]\d)-([01]\d|2[0-3]):([0-5]\d) motion {_MOTION}$"
)
_BARE = re.compile(rf"^(ignore|downweight) motion {_MOTION}$")


def fold_ws(line: str) -> str:
    return _WS.sub(" ", line.strip())


def parse_filter_line(line: str) -> dict | None:
    folded = fold_ws(line)
    if not folded:
        return None
    timed = _TIMED.fullmatch(folded)
    if timed:
        opcode = timed.group(1)
        start = f"{timed.group(2)}:{timed.group(3)}"
        end = f"{timed.group(4)}:{timed.group(5)}"
        motion = timed.group(6)
        span = clock_arc_min(start, end)
        if span > FILTER_MAX_SPAN_MIN or span == 0:
            return None
        return {
            "opcode": opcode,
            "timed": True,
            "start": start,
            "end": end,
            "span": span,
            "motion": motion,
            "canonical": folded,
        }
    bare = _BARE.fullmatch(folded)
    if bare:
        return {
            "opcode": bare.group(1),
            "timed": False,
            "start": None,
            "end": None,
            "span": None,
            "motion": bare.group(2),
            "canonical": folded,
        }
    return None


def interval_overlaps_cluster(start: str, end: str, median_min: int, tol: int = HABIT_CLOCK_TOLERANCE_MIN) -> bool:
    a = minutes_from_midnight(start)
    b = minutes_from_midnight(end)
    for minute in walk_shortest_arc(a, b):
        if clock_arc_min(minute, median_min) <= tol:
            return True
    return False


def event_hits_filter(event: dict, parsed: dict) -> bool:
    if event["motion_type"] != parsed["motion"]:
        return False
    if not parsed["timed"]:
        return True
    return time_on_shortest_arc(event["t"], parsed["start"], parsed["end"])


def first_hit(filter_text: str, event: dict) -> dict | None:
    if not filter_text or filter_text == "none":
        return None
    for line in filter_text.splitlines():
        parsed = parse_filter_line(line)
        if parsed and event_hits_filter(event, parsed):
            return parsed
    return None


def accept_filter_text(raw: str, clusters: list[dict], morning_habit_motions: set[str], yesterday: str = "none") -> str:
    """Keep legal lines only. Empty result falls back to yesterday."""
    kept: list[str] = []
    for line in (raw or "").splitlines():
        if len(kept) >= FILTER_MAX_LINES:
            break
        parsed = parse_filter_line(line)
        if parsed is None:
            continue
        if parsed["timed"]:
            ok = any(
                parsed["motion"] in cluster["motions"]
                and interval_overlaps_cluster(parsed["start"], parsed["end"], cluster["median"])
                for cluster in clusters
            )
            if not ok:
                continue
        elif parsed["motion"] not in morning_habit_motions:
            continue
        kept.append(parsed["canonical"])
    if not kept:
        return yesterday if yesterday else "none"
    return "\n".join(kept)
