"""High-resolution tiled render planning."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RenderTile:
    x: int
    y: int
    width: int
    height: int
    overlap: int


@dataclass(frozen=True)
class TiledRenderPlan:
    output_width: int
    output_height: int
    tile_size: int
    overlap: int
    tiles: tuple[RenderTile, ...]
    estimated_tile_memory_mb: float


def plan_high_resolution_tiling(
    output_width: int,
    output_height: int,
    memory_budget_mb: int,
    bytes_per_pixel: int = 6,
    overlap: int = 32,
) -> TiledRenderPlan:
    """Plan memory-safe tiles for 8K/16K style outputs."""

    if output_width <= 0 or output_height <= 0:
        raise ValueError("Output dimensions must be greater than zero.")
    if memory_budget_mb <= 0:
        raise ValueError("memory_budget_mb must be greater than zero.")
    max_pixels = max(1, (memory_budget_mb * 1024 * 1024) // bytes_per_pixel)
    tile_size = max(64, int(max_pixels**0.5) - overlap * 2)
    tile_size = min(tile_size, output_width, output_height)
    tiles = []
    y = 0
    while y < output_height:
        x = 0
        height = min(tile_size, output_height - y)
        while x < output_width:
            width = min(tile_size, output_width - x)
            tiles.append(RenderTile(x=x, y=y, width=width, height=height, overlap=overlap))
            x += tile_size
        y += tile_size
    estimated = ((tile_size + overlap * 2) ** 2 * bytes_per_pixel) / (1024 * 1024)
    return TiledRenderPlan(
        output_width=output_width,
        output_height=output_height,
        tile_size=tile_size,
        overlap=overlap,
        tiles=tuple(tiles),
        estimated_tile_memory_mb=estimated,
    )
