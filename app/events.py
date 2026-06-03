"""Live job log streaming and replay state."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class JobEvent:
    id: int
    timestamp: float
    job_id: str
    type: str
    message: str

    def to_payload(self) -> dict:
        return asdict(self)


class EventLog:
    def __init__(self) -> None:
        self._events: list[JobEvent] = []
        self._next_id = 1

    def append(self, job_id: str, event_type: str, message: str) -> JobEvent:
        event = JobEvent(
            id=self._next_id,
            timestamp=time.time(),
            job_id=job_id,
            type=event_type,
            message=message,
        )
        self._next_id += 1
        self._events.append(event)
        return event

    def replay_after(self, last_event_id: int) -> list[JobEvent]:
        return [event for event in self._events if event.id > last_event_id]

    def as_sse(self, events: list[JobEvent]) -> str:
        return "".join(
            f"id: {event.id}\nevent: {event.type}\ndata: {event.message}\n\n"
            for event in events
        )
