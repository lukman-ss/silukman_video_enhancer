"""Visual artifact anomaly detection."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ArtifactReport:
    corrupted: bool
    black_frame: bool
    score: float


def detect_artifact(frame: bytes, black_threshold: int = 3) -> ArtifactReport:
    if not frame:
        return ArtifactReport(corrupted=True, black_frame=False, score=1.0)
    average = sum(frame) / len(frame)
    black = average <= black_threshold
    unique_ratio = len(set(frame)) / min(len(frame), 256)
    corrupted = unique_ratio < 0.01 or black
    return ArtifactReport(corrupted=corrupted, black_frame=black, score=1.0 - unique_ratio)
