"""Local frame interpolation planning."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from utils.ffmpeg import require_binary


@dataclass(frozen=True)
class InterpolationPlan:
    source_fps: float
    target_fps: float
    factor: int
    model_name: str = "rife"


def plan_interpolation(source_fps: float, target_fps: float) -> InterpolationPlan:
    if target_fps <= source_fps:
        return InterpolationPlan(source_fps, target_fps, factor=1)
    factor = max(1, round(target_fps / source_fps))
    return InterpolationPlan(source_fps, target_fps, factor=factor)


RifeRunner = Callable[[Path, Path, InterpolationPlan], Path]


def run_interpolation(
    input_path: Path,
    output_path: Path,
    plan: InterpolationPlan,
    rife_runner: RifeRunner | None = None,
) -> Path:
    """Create a target-FPS video using RIFE when available, otherwise FFmpeg."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if plan.factor <= 1 or plan.target_fps <= plan.source_fps:
        _copy_with_target_fps(input_path, output_path, plan.target_fps)
        return output_path
    if rife_runner is not None:
        return rife_runner(input_path, output_path, plan)
    return _run_ffmpeg_interpolation(input_path, output_path, plan.target_fps)


def _copy_with_target_fps(input_path: Path, output_path: Path, fps: float) -> None:
    ffmpeg = require_binary("ffmpeg")
    result = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(input_path),
            "-filter:v",
            f"fps={fps:.6f}",
            "-c:a",
            "copy",
            str(output_path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Frame-rate conversion failed: {result.stderr.strip()}")


def _run_ffmpeg_interpolation(input_path: Path, output_path: Path, fps: float) -> Path:
    ffmpeg = require_binary("ffmpeg")
    result = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(input_path),
            "-filter:v",
            f"minterpolate=fps={fps:.6f}:mi_mode=mci",
            "-c:a",
            "copy",
            str(output_path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Frame interpolation failed: {result.stderr.strip()}")
    return output_path
