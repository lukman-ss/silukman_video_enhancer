"""RAM/VRAM planning helpers for auto-tiling."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ResourceLimits:
    ram_bytes: int
    vram_bytes: int | None = None


@dataclass(frozen=True)
class TilingPlan:
    tile_size: int
    overlap: int = 16


def detect_ram_limit() -> int:
    if hasattr(os, "sysconf"):
        page_size = os.sysconf("SC_PAGE_SIZE")
        pages = os.sysconf("SC_PHYS_PAGES")
        return int(page_size * pages)
    return 4 * 1024 * 1024 * 1024


def choose_tiling_plan(width: int, height: int, limits: ResourceLimits) -> TilingPlan:
    pixels = width * height
    budget = limits.vram_bytes or int(limits.ram_bytes * 0.25)
    frame_bytes = pixels * 3 * 4
    if frame_bytes * 4 <= budget:
        return TilingPlan(tile_size=1024)
    if frame_bytes * 2 <= budget:
        return TilingPlan(tile_size=512)
    return TilingPlan(tile_size=256)
