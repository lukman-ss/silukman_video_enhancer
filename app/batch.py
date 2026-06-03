"""Batch CLI planning for folder inputs."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Iterable, List

from app.config import EnhancementConfig


VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm"}


def discover_video_inputs(folder: Path) -> List[Path]:
    if not folder.exists() or not folder.is_dir():
        raise ValueError(f"Batch input folder does not exist: {folder}")
    return sorted(
        path
        for path in folder.iterdir()
        if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS
    )


def build_batch_configs(base: EnhancementConfig, output_dir: Path) -> List[EnhancementConfig]:
    inputs = discover_video_inputs(base.input_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    return [
        replace(
            base,
            input_path=input_path,
            output_path=output_dir / f"{input_path.stem}_enhanced.mp4",
        )
        for input_path in inputs
    ]
