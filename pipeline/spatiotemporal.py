"""Dynamic spatial-temporal scaling helpers."""

from __future__ import annotations

from dataclasses import dataclass

from pipeline.temporal import TemporalDecision


@dataclass(frozen=True)
class SpatialTemporalScalePlan:
    scale: int
    reason: str


def choose_spatiotemporal_scale(
    base_scale: int,
    decision: TemporalDecision,
    motion_score: float,
) -> SpatialTemporalScalePlan:
    """Adapt scaling based on scene changes and motion intensity."""

    if decision.scene_cut:
        return SpatialTemporalScalePlan(scale=base_scale, reason="scene cut reset")
    if motion_score > 0.75 and base_scale > 1:
        return SpatialTemporalScalePlan(scale=max(1, base_scale // 2), reason="high motion")
    if decision.skip_frame:
        return SpatialTemporalScalePlan(scale=1, reason="duplicate frame")
    return SpatialTemporalScalePlan(scale=base_scale, reason="default")
