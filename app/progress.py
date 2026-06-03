"""Non-blocking CLI progress reporting."""

from __future__ import annotations

import queue
import sys
import threading
import time
from dataclasses import dataclass
from typing import TextIO


_STOP = object()


@dataclass(frozen=True)
class ProgressEvent:
    current: int
    total: int | None
    message: str


class CliProgressMonitor:
    """Queue-backed progress monitor that keeps work threads non-blocking."""

    def __init__(self, stream: TextIO | None = None, interval: float = 0.5) -> None:
        self.stream = stream or sys.stderr
        self.interval = interval
        self._events: queue.Queue[ProgressEvent | object] = queue.Queue()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._last_render = 0.0

    def __enter__(self) -> "CliProgressMonitor":
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    def update(self, current: int, total: int | None, message: str) -> None:
        self._events.put(ProgressEvent(current=current, total=total, message=message))

    def close(self) -> None:
        self._events.put(_STOP)
        self._thread.join()

    def _run(self) -> None:
        pending: ProgressEvent | None = None
        while True:
            try:
                event = self._events.get(timeout=self.interval)
            except queue.Empty:
                event = None

            if event is _STOP:
                self._render(pending)
                break
            if event is None:
                self._render(pending)
                pending = None
                continue

            assert isinstance(event, ProgressEvent)
            pending = event
            now = time.monotonic()
            if now - self._last_render >= self.interval:
                self._render(pending)
                pending = None

    def _render(self, event: ProgressEvent | None) -> None:
        if event is None:
            return
        if event.total:
            percent = min(100.0, (event.current / event.total) * 100)
            line = f"{percent:6.2f}% ({event.current}/{event.total}) {event.message}"
        else:
            line = f"{event.current} frames {event.message}"
        print(line, file=self.stream, flush=True)
        self._last_render = time.monotonic()
