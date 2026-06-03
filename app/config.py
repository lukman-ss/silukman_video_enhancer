"""Shared enhancement configuration for CLI and desktop UI."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Tuple


DeviceName = Literal["auto", "cpu", "cuda", "coreml", "directml"]
ModelName = Literal["realesrgan", "swinir", "srcnn"]


@dataclass(frozen=True)
class EnhancementConfig:
    """User-facing enhancement settings shared by all interfaces."""

    input_path: Path
    output_path: Path
    model: ModelName = "realesrgan"
    scale: int = 2
    device: DeviceName = "auto"
    crf: int = 18
    denoise: bool = False
    color_correct: bool = False
    audio_restore: bool = False
    preserve_metadata: bool = True
    quiet: bool = False
    benchmark: bool = False
    batch: bool = False
    model_chain: Tuple[str, ...] = ()
    roi: Tuple[int, int, int, int] | None = None
    fp16: bool = False
    destinations: Tuple[str, ...] = ()
    face_model: str | None = None
    dynamic_scale: bool = False
    async_workers: int = 1
    checkpoint_dir: Path | None = None
    worker_devices: Tuple[str, ...] = ()
    restoration_ops: Tuple[str, ...] = ()
    target_fps: float | None = None

    def validate(self, require_existing_input: bool = True) -> None:
        """Validate settings before passing them to a pipeline implementation."""

        if require_existing_input and not self.input_path.exists():
            raise ValueError(f"Input video does not exist: {self.input_path}")
        if self.input_path.is_dir():
            raise ValueError(f"Input path must be a video file: {self.input_path}")
        if self.output_path.is_dir():
            raise ValueError(f"Output path must include a file name: {self.output_path}")
        if self.scale not in {1, 2, 4}:
            raise ValueError("Scale must be one of: 1, 2, 4")
        if not 0 <= self.crf <= 51:
            raise ValueError("CRF must be between 0 and 51")
        if self.target_fps is not None and self.target_fps <= 0:
            raise ValueError("Target FPS must be greater than zero")

    def summary(self) -> str:
        """Return a concise summary for UI logs and CLI dry-runs."""

        filters = []
        if self.denoise:
            filters.append("denoise")
        if self.color_correct:
            filters.append("color-correct")
        if self.audio_restore:
            filters.append("audio-restore")
        if self.model_chain:
            filters.append(f"chain={'+'.join(self.model_chain)}")
        if self.roi:
            filters.append(f"roi={self.roi}")
        if self.face_model:
            filters.append(f"face={self.face_model}")
        if self.restoration_ops:
            filters.append(f"restore={'+'.join(self.restoration_ops)}")
        if self.target_fps:
            filters.append(f"target-fps={self.target_fps:g}")
        filter_label = ", ".join(filters) if filters else "upscale only"
        return (
            f"{self.input_path} -> {self.output_path} | "
            f"model={self.model}, scale={self.scale}x, device={self.device}, "
            f"crf={self.crf}, filters={filter_label}, quiet={self.quiet}"
        )
