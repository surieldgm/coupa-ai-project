"""Trace port and adapters.

Flat JSONL events with OTel GenAI attribute names, no OTel SDK — see
docs/adr/0001. One line = one event; every event carries session_id,
turn, seq, and ts, so any slice of a file is analyzable on its own.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

TraceEvent = dict[str, Any]


class TraceSink(Protocol):
    def emit(self, event: TraceEvent) -> None: ...


class InMemorySink:
    """Test/eval adapter: events kept in a list."""

    def __init__(self) -> None:
        self.events: list[TraceEvent] = []

    def emit(self, event: TraceEvent) -> None:
        self.events.append(event)


class JsonlSink:
    """Production adapter: append-only JSONL file, one event per line.

    Opens per emit so every event is durable the moment it is written —
    a crashed turn keeps everything emitted before the crash.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, event: TraceEvent) -> None:
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
