"""Temporal consistency, scene cut, and frame skip helpers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TemporalDecision:
    scene_cut: bool
    skip_frame: bool
    similarity: float


class TemporalAnalyzer:
    """Lightweight RGB frame analyzer for Phase 2 temporal decisions."""

    def __init__(
        self,
        width: int,
        height: int,
        scene_cut_threshold: float = 0.22,
        skip_similarity_threshold: float = 0.995,
    ) -> None:
        self.width = width
        self.height = height
        self.scene_cut_threshold = scene_cut_threshold
        self.skip_similarity_threshold = skip_similarity_threshold
        self._previous_frame: bytes | None = None

    def analyze(self, frame: bytes) -> TemporalDecision:
        expected = self.width * self.height * 3
        if len(frame) != expected:
            raise ValueError("Frame byte length does not match RGB dimensions.")
        if self._previous_frame is None:
            self._previous_frame = frame
            return TemporalDecision(scene_cut=False, skip_frame=False, similarity=0.0)

        similarity = ssim_like_similarity(self._previous_frame, frame)
        scene_delta = 1.0 - similarity
        scene_cut = scene_delta >= self.scene_cut_threshold
        skip_frame = (not scene_cut) and similarity >= self.skip_similarity_threshold
        if not skip_frame:
            self._previous_frame = frame
        return TemporalDecision(
            scene_cut=scene_cut,
            skip_frame=skip_frame,
            similarity=similarity,
        )


def ssim_like_similarity(previous: bytes, current: bytes) -> float:
    """Return a cheap SSIM-like byte similarity score in the 0..1 range."""

    if len(previous) != len(current):
        raise ValueError("Frames must have the same byte length.")
    if not previous:
        return 1.0
    total_delta = sum(abs(a - b) for a, b in zip(previous, current))
    max_delta = len(previous) * 255
    return max(0.0, min(1.0, 1.0 - (total_delta / max_delta)))
