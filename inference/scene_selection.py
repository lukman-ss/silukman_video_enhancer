"""Scene-based model selection."""

from __future__ import annotations


def classify_scene(brightness: float, motion: float) -> str:
    if brightness < 0.25:
        return "low_light"
    if motion > 0.75:
        return "high_motion"
    return "general"


def select_model_for_scene(scene: str) -> str:
    return {
        "low_light": "swinir",
        "high_motion": "srcnn",
        "general": "realesrgan",
    }.get(scene, "realesrgan")
