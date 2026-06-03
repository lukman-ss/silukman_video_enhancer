"""Desktop batch queue state helpers."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from pathlib import Path
import time
from typing import Iterable, List

from app.config import EnhancementConfig


VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}
OUTPUT_FORMATS = (".mp4", ".mkv", ".mov")


def is_supported_video(path: Path) -> bool:
    """Return True when *path* has a supported video extension."""

    return path.suffix.lower() in VIDEO_EXTENSIONS


def supported_video_paths(paths: Iterable[Path]) -> List[Path]:
    """Filter local paths to supported video files while preserving order."""

    return [Path(path) for path in paths if is_supported_video(Path(path))]


def normalize_output_format(extension: str) -> str:
    """Return a supported output extension with a leading dot."""

    normalized = extension.lower()
    if not normalized.startswith("."):
        normalized = f".{normalized}"
    if normalized not in OUTPUT_FORMATS:
        raise ValueError(f"Unsupported output format: {extension}")
    return normalized


def with_output_format(path: Path, extension: str) -> Path:
    """Return *path* with a supported output container extension."""

    return path.with_suffix(normalize_output_format(extension))


def default_batch_output_path(input_path: Path, extension: str = ".mp4") -> Path:
    """Return the default batch output path for *input_path*."""

    return input_path.with_name(f"{input_path.stem}_enhanced{normalize_output_format(extension)}")


@dataclass
class DesktopQueueItem:
    input_path: Path
    output_path: Path
    output_format: str = ".mp4"
    status: str = "Pending"
    progress: int = 0
    message: str = ""


class DesktopQueueModel:
    """Small testable model behind the desktop file queue table."""

    def __init__(self) -> None:
        self._items: List[DesktopQueueItem] = []

    def add_files(self, paths: Iterable[Path], output_format: str = ".mp4") -> List[DesktopQueueItem]:
        added: List[DesktopQueueItem] = []
        existing = {item.input_path for item in self._items}
        output_format = normalize_output_format(output_format)
        for path in supported_video_paths(paths):
            path = Path(path)
            if path in existing:
                continue
            item = DesktopQueueItem(
                input_path=path,
                output_path=default_batch_output_path(path, output_format),
                output_format=output_format,
            )
            self._items.append(item)
            added.append(item)
            existing.add(path)
        return added

    def remove(self, index: int) -> DesktopQueueItem:
        return self._items.pop(index)

    def remove_many(self, indexes: Iterable[int]) -> List[DesktopQueueItem]:
        removed: List[DesktopQueueItem] = []
        for index in sorted(set(indexes), reverse=True):
            removed.append(self._items.pop(index))
        removed.reverse()
        return removed

    def clear(self) -> None:
        self._items.clear()

    def move(self, source_index: int, destination_index: int) -> DesktopQueueItem:
        item = self._items.pop(source_index)
        destination_index = min(max(0, destination_index), len(self._items))
        self._items.insert(destination_index, item)
        return item

    def reorder_by_input_paths(self, input_paths: Iterable[Path]) -> None:
        ordered_paths = [Path(path) for path in input_paths]
        by_path = {item.input_path: item for item in self._items}
        seen: set[Path] = set()
        reordered: List[DesktopQueueItem] = []
        for path in ordered_paths:
            item = by_path.get(path)
            if item is None or path in seen:
                continue
            reordered.append(item)
            seen.add(path)
        reordered.extend(item for item in self._items if item.input_path not in seen)
        self._items = reordered

    def set_output_format(self, index: int, extension: str) -> DesktopQueueItem:
        output_format = normalize_output_format(extension)
        item = self._items[index]
        item.output_format = output_format
        item.output_path = with_output_format(item.output_path, output_format)
        return item

    def set_all_output_format(self, extension: str) -> List[DesktopQueueItem]:
        return [self.set_output_format(index, extension) for index in range(len(self._items))]

    def update(self, index: int, *, status: str | None = None, progress: int | None = None, message: str | None = None) -> DesktopQueueItem:
        item = self._items[index]
        if status is not None:
            item.status = status
        if progress is not None:
            item.progress = min(100, max(0, progress))
        if message is not None:
            item.message = message
        return item

    def failed_items(self) -> List[DesktopQueueItem]:
        return [item for item in self._items if item.status == "Error"]

    def retry_failed(self) -> List[DesktopQueueItem]:
        retried: List[DesktopQueueItem] = []
        for item in self.failed_items():
            item.status = "Pending"
            item.progress = 0
            item.message = "Retry queued"
            retried.append(item)
        return retried

    def configs_from_base(self, base: EnhancementConfig) -> List[EnhancementConfig]:
        return [
            dataclasses.replace(
                base,
                input_path=item.input_path,
                output_path=item.output_path,
                batch=True,
            )
            for item in self._items
        ]

    def items(self) -> List[DesktopQueueItem]:
        return list(self._items)

    def __len__(self) -> int:
        return len(self._items)


class DesktopEtaTracker:
    """Tracks progress ticks and formats a simple ETA estimate."""

    def __init__(self) -> None:
        self._start: float | None = None

    def reset(self, now: float | None = None) -> None:
        self._start = time.monotonic() if now is None else now

    def eta_seconds(self, percent: int, now: float | None = None) -> float | None:
        if percent <= 0:
            return None
        current = time.monotonic() if now is None else now
        if self._start is None:
            self._start = current
            return None
        elapsed = max(0.0, current - self._start)
        if elapsed <= 0 or percent >= 100:
            return 0.0
        return elapsed * ((100 - percent) / percent)

    def label(self, percent: int, now: float | None = None) -> str:
        seconds = self.eta_seconds(percent, now=now)
        if seconds is None:
            return "ETA calculating..."
        if seconds <= 0:
            return "ETA 00:00"
        minutes, secs = divmod(round(seconds), 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"ETA {hours:02}:{minutes:02}:{secs:02}"
        return f"ETA {minutes:02}:{secs:02}"
