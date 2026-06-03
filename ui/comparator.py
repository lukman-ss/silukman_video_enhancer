"""Visual comparator state for original/enhanced previews."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from utils.ffmpeg import require_binary


@dataclass(frozen=True)
class ComparatorState:
    original_path: Path
    enhanced_path: Path
    split_position: float = 0.5

    def normalized_split(self) -> float:
        return min(1.0, max(0.0, self.split_position))

    def label(self) -> str:
        return f"{self.original_path.name} vs {self.enhanced_path.name}"


@dataclass(frozen=True)
class PreviewRequest:
    timestamp_seconds: float
    crop_x: int = 0
    crop_y: int = 0
    crop_width: int = 256
    crop_height: int = 256


@dataclass(frozen=True)
class PreviewPair:
    original_frame: Path
    enhanced_frame: Path


@dataclass(frozen=True)
class TimelinePreviewFrame:
    timestamp_seconds: float
    original_frame: Path
    enhanced_frame: Path


def render_sampled_preview(
    state: ComparatorState,
    request: PreviewRequest,
    output_dir: Path,
) -> PreviewPair:
    """Render sampled original/enhanced preview crops with FFmpeg."""

    output_dir.mkdir(parents=True, exist_ok=True)
    original_frame = output_dir / "preview-original.png"
    enhanced_frame = output_dir / "preview-enhanced.png"
    _extract_preview_frame(state.original_path, original_frame, request)
    _extract_preview_frame(state.enhanced_path, enhanced_frame, request)
    return PreviewPair(original_frame=original_frame, enhanced_frame=enhanced_frame)


def plan_timeline_preview_requests(
    duration_seconds: float,
    frames: int,
    crop_x: int = 0,
    crop_y: int = 0,
    crop_width: int = 256,
    crop_height: int = 256,
) -> list[PreviewRequest]:
    """Plan evenly spaced crop previews for a video timeline."""

    if duration_seconds <= 0:
        raise ValueError("duration_seconds must be greater than zero.")
    if frames <= 0:
        raise ValueError("frames must be greater than zero.")
    if frames == 1:
        timestamps = [0.0]
    else:
        step = duration_seconds / (frames - 1)
        timestamps = [min(duration_seconds, index * step) for index in range(frames)]
    return [
        PreviewRequest(
            timestamp_seconds=timestamp,
            crop_x=crop_x,
            crop_y=crop_y,
            crop_width=crop_width,
            crop_height=crop_height,
        )
        for timestamp in timestamps
    ]


def render_timeline_preview(
    state: ComparatorState,
    requests: list[PreviewRequest],
    output_dir: Path,
) -> list[TimelinePreviewFrame]:
    """Render multi-frame original/enhanced timeline crop previews."""

    frames = []
    for index, request in enumerate(requests):
        pair = render_sampled_preview(state, request, output_dir / f"frame-{index:03}")
        frames.append(
            TimelinePreviewFrame(
                timestamp_seconds=request.timestamp_seconds,
                original_frame=pair.original_frame,
                enhanced_frame=pair.enhanced_frame,
            )
        )
    return frames


def _extract_preview_frame(input_path: Path, output_path: Path, request: PreviewRequest) -> None:
    if request.crop_width <= 0 or request.crop_height <= 0:
        raise ValueError("Preview crop dimensions must be greater than zero.")
    ffmpeg = require_binary("ffmpeg")
    crop_filter = (
        f"crop={request.crop_width}:{request.crop_height}:"
        f"{request.crop_x}:{request.crop_y}"
    )
    result = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            f"{max(0.0, request.timestamp_seconds):.3f}",
            "-i",
            str(input_path),
            "-frames:v",
            "1",
            "-vf",
            crop_filter,
            str(output_path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Preview frame extraction failed: {result.stderr.strip()}")
