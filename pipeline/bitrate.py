"""Output bitrate and CRF calibration helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess

from utils.ffmpeg import VideoInfo, spatial_complexity_scan_command


@dataclass(frozen=True)
class BitratePlan:
    crf: int
    maxrate_kbps: int
    bufsize_kbps: int


def calibrate_bitrate(info: VideoInfo, scale: int, requested_crf: int) -> BitratePlan:
    """Estimate a conservative bitrate envelope from resolution and frame rate."""

    output_pixels = info.width * info.height * scale * scale
    fps = max(info.fps, 1.0)
    bits_per_pixel = 0.085 if output_pixels >= 1920 * 1080 else 0.11
    maxrate_kbps = int((output_pixels * fps * bits_per_pixel) / 1000)
    maxrate_kbps = max(maxrate_kbps, 2500)
    return BitratePlan(
        crf=requested_crf,
        maxrate_kbps=maxrate_kbps,
        bufsize_kbps=maxrate_kbps * 2,
    )


def scan_spatial_complexity(input_path: Path, duration: int = 3) -> float:
    """Run a short FFmpeg signalstats scan and return a coarse complexity score."""

    result = subprocess.run(
        spatial_complexity_scan_command(input_path, duration=duration),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return 1.0
    scores = []
    for line in result.stderr.splitlines():
        marker = "lavfi.signalstats.YDIF="
        if marker in line:
            _, _, tail = line.partition(marker)
            value, _, _ = tail.partition(" ")
            try:
                scores.append(float(value))
            except ValueError:
                continue
    if not scores:
        return 1.0
    return max(0.75, min(1.5, 1.0 + (sum(scores) / len(scores)) / 255.0))


def calibrate_bitrate_from_scan(
    info: VideoInfo,
    scale: int,
    requested_crf: int,
    complexity_score: float,
) -> BitratePlan:
    base = calibrate_bitrate(info, scale, requested_crf)
    adjusted = int(base.maxrate_kbps * complexity_score)
    return BitratePlan(
        crf=base.crf,
        maxrate_kbps=max(adjusted, 2500),
        bufsize_kbps=max(adjusted, 2500) * 2,
    )
