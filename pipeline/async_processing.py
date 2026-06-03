"""Async frame processing helpers."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable, Iterable, List


FrameProcessor = Callable[[bytes], bytes]


@dataclass(frozen=True)
class ProcessedFrame:
    index: int
    frame: bytes


class AsyncFrameProcessor:
    """Thread-pool post-processing that preserves frame order."""

    def __init__(self, processor: FrameProcessor, max_workers: int = 2) -> None:
        self.processor = processor
        self.max_workers = max_workers

    def process(self, frames: Iterable[bytes]) -> List[ProcessedFrame]:
        indexed = list(enumerate(frames))
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = [
                executor.submit(self.processor, frame)
                for _, frame in indexed
            ]
            processed = [
                ProcessedFrame(index=indexed[index][0], frame=future.result())
                for index, future in enumerate(futures)
            ]
        return sorted(processed, key=lambda item: item.index)


class DoubleBuffer:
    """Tiny double buffer abstraction for upload/process/download staging."""

    def __init__(self) -> None:
        self._slots: list[bytes | None] = [None, None]
        self._cursor = 0

    def push(self, frame: bytes) -> int:
        slot = self._cursor
        self._slots[slot] = frame
        self._cursor = 1 - self._cursor
        return slot

    def get(self, slot: int) -> bytes | None:
        return self._slots[slot]
