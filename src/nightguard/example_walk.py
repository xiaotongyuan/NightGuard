"""Guided demo walk. Page chrome only. No product rules."""

from __future__ import annotations

STATES = ("idle", "guiding", "finished", "left")
START_BUTTON = "Start this example"
RESTART_BUTTON = "Restart this example"
FINISHED_MESSAGE = "Example finished. The scratch asked for a judgment."
LEFT_MESSAGE = "Left the example. Start this example to reset."

# Linear click list. Labels and temperature are ignored.
SCRIPT = (
    ("play", "open.sigh.torso"),
    ("play", "follow.leave.plus1"),
    ("next_night",),
    ("play", "open.sigh.torso"),
    ("play", "follow.leave.plus1"),
    ("next_night",),
    ("play", "open.sigh.torso"),
    ("play", "follow.leave.plus1"),
    ("morning",),
    ("play", "open.sigh.torso"),
    ("play", "open.scratch.left_calf"),
)

_EMPTY_HIGHLIGHT = {
    "choice_id": "",
    "select": False,
    "morning": False,
    "list_index": -1,
}

_GUIDE = (
    {
        "message": "Next: sigh shift",
        "choice_id": "open.sigh.torso",
        "select": False,
        "morning": False,
        "list_index": 0,
    },
    {
        "message": "Next: leave bed (+1 min)",
        "choice_id": "follow.leave.plus1",
        "select": False,
        "morning": False,
        "list_index": 1,
    },
    {
        "message": "Next: Time → next night",
        "choice_id": "",
        "select": True,
        "morning": False,
        "list_index": 2,
    },
    {
        "message": "Next: sigh shift",
        "choice_id": "open.sigh.torso",
        "select": False,
        "morning": False,
        "list_index": 0,
    },
    {
        "message": "Next: leave bed (+1 min)",
        "choice_id": "follow.leave.plus1",
        "select": False,
        "morning": False,
        "list_index": 1,
    },
    {
        "message": "Next: Time → next night",
        "choice_id": "",
        "select": True,
        "morning": False,
        "list_index": 2,
    },
    {
        "message": "Next: sigh shift",
        "choice_id": "open.sigh.torso",
        "select": False,
        "morning": False,
        "list_index": 0,
    },
    {
        "message": "Next: leave bed (+1 min)",
        "choice_id": "follow.leave.plus1",
        "select": False,
        "morning": False,
        "list_index": 1,
    },
    {
        "message": "Next: Update tomorrow's rules",
        "choice_id": "",
        "select": False,
        "morning": True,
        "list_index": 3,
    },
    {
        "message": "Next: sigh shift",
        "choice_id": "open.sigh.torso",
        "select": False,
        "morning": False,
        "list_index": 4,
    },
    {
        "message": "Next: scratch left calf",
        "choice_id": "open.scratch.left_calf",
        "select": False,
        "morning": False,
        "list_index": 4,
    },
)


def _highlight_from(row: dict) -> dict:
    return {
        "choice_id": row["choice_id"],
        "select": row["select"],
        "morning": row["morning"],
        "list_index": row["list_index"],
    }


def _matches(expected: tuple, kind: str, choice_id: str | None) -> bool:
    if expected[0] != kind:
        return False
    if kind == "play":
        return expected[1] == choice_id
    return True


class ExampleWalk:
    def __init__(self) -> None:
        self.state = "idle"
        self.step = 0

    def start(self) -> None:
        self.state = "guiding"
        self.step = 0

    def mark_left(self) -> None:
        self.state = "left"

    def note(self, kind: str, choice_id: str | None = None) -> None:
        if self.state != "guiding":
            return
        expected = SCRIPT[self.step]
        if _matches(expected, kind, choice_id):
            self.step += 1
            if self.step >= len(SCRIPT):
                self.state = "finished"
            return
        self.state = "left"

    def view(self) -> dict:
        if self.state == "guiding":
            row = _GUIDE[self.step]
            return {
                "state": self.state,
                "step": self.step,
                "message": row["message"],
                "button": RESTART_BUTTON,
                "highlight": _highlight_from(row),
            }
        if self.state == "finished":
            return {
                "state": self.state,
                "step": self.step,
                "message": FINISHED_MESSAGE,
                "button": RESTART_BUTTON,
                "highlight": dict(_EMPTY_HIGHLIGHT),
            }
        if self.state == "left":
            return {
                "state": self.state,
                "step": self.step,
                "message": LEFT_MESSAGE,
                "button": RESTART_BUTTON,
                "highlight": dict(_EMPTY_HIGHLIGHT),
            }
        return {
            "state": "idle",
            "step": 0,
            "message": "",
            "button": START_BUTTON,
            "highlight": dict(_EMPTY_HIGHLIGHT),
        }
