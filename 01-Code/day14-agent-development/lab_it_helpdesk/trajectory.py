"""Trajectory logging: one JSON object per line, one file per scenario run.

Logged: observable events only (user request, the model's chosen action or final reply, tool calls
with validated arguments, permission level, approval state, result, errors/timeouts, final outcome).
The model's private reasoning is never requested or stored.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path


class TrajectoryLogger:
    def __init__(self, scenario_id: str, path: Path | None = None):
        self.scenario_id = scenario_id
        self.path = path
        self.events: list[dict] = []
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("", encoding="utf-8")

    def event(self, kind: str, **data) -> dict:
        rec = {
            "scenario_id": self.scenario_id,
            "seq": len(self.events) + 1,
            "time_utc": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "event": kind,
            **data,
        }
        self.events.append(rec)
        if self.path:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
        return rec

    def of(self, kind: str) -> list[dict]:
        return [e for e in self.events if e["event"] == kind]
