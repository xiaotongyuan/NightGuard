"""Append-only event log."""

from __future__ import annotations

import json
from pathlib import Path


class EventLog:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    def append(self, event: dict) -> None:
        self.rows.append(dict(event))

    def write_jsonl(self, path: Path) -> None:
        path.write_text(
            "\n".join(json.dumps(row, ensure_ascii=True) for row in self.rows) + ("\n" if self.rows else ""),
            encoding="utf-8",
        )
