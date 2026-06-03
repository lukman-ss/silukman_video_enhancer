"""Multi-destination output planning."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess

from utils.ffmpeg import destination_command


@dataclass(frozen=True)
class OutputDestination:
    path: Path
    start_seconds: float | None = None
    end_seconds: float | None = None
    stream_copy: bool = False


def parse_destination(value: str) -> OutputDestination:
    """Parse `path[,start,end,copy]` into an output destination."""

    parts = [part.strip() for part in value.split(",")]
    if not parts or not parts[0]:
        raise ValueError("Destination must include an output path.")
    start = float(parts[1]) if len(parts) > 1 and parts[1] else None
    end = float(parts[2]) if len(parts) > 2 and parts[2] else None
    stream_copy = len(parts) > 3 and parts[3].lower() in {"copy", "streamcopy", "true"}
    if start is not None and end is not None and end <= start:
        raise ValueError("Destination end time must be greater than start time.")
    return OutputDestination(
        path=Path(parts[0]),
        start_seconds=start,
        end_seconds=end,
        stream_copy=stream_copy,
    )


def emit_destination(source: Path, destination: OutputDestination) -> Path:
    if destination.start_seconds is None and destination.end_seconds is None:
        destination.path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination.path)
        return destination.path
    result = subprocess.run(
        destination_command(source, destination),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Destination export failed: {result.stderr.strip()}")
    return destination.path
