"""Denoise, deblur, and compression artifact cleanup model planning."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from inference.runtime import ONNXFrameUpscaler
from models.registry import model_cache_dir


RESTORATION_MODELS = {
    "denoise": "swinir-denoise.onnx",
    "deblur": "dpir-deblur.onnx",
    "artifact": "artifact-cleanup.onnx",
}


@dataclass(frozen=True)
class RestorationPlan:
    operation: str
    model_path: Path
    enabled: bool


def plan_restoration(operation: str, root: Path | None = None) -> RestorationPlan:
    if operation not in RESTORATION_MODELS:
        available = ", ".join(sorted(RESTORATION_MODELS))
        raise ValueError(f"Unknown restoration operation `{operation}`. Available: {available}")
    path = (root or model_cache_dir()) / RESTORATION_MODELS[operation]
    return RestorationPlan(operation=operation, model_path=path, enabled=path.exists())


class RestorationProcessor:
    """ONNX-backed restoration processor for RGB frames."""

    def __init__(self, plan: RestorationPlan, device: str, enable_fp16: bool = False) -> None:
        if not plan.enabled:
            raise FileNotFoundError(f"Restoration model missing: {plan.model_path}")
        self.plan = plan
        self.runtime = ONNXFrameUpscaler(plan.model_path, device, enable_fp16=enable_fp16)

    def process(self, frame: bytes, width: int, height: int) -> bytes:
        return self.runtime.upscale(frame, width, height)
