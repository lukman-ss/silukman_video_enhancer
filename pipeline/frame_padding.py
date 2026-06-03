"""Frame padding helpers for ONNX compatibility."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PaddingPlan:
    original_width: int
    original_height: int
    padded_width: int
    padded_height: int
    divisor: int = 4

    @property
    def needs_padding(self) -> bool:
        return (self.original_width, self.original_height) != (
            self.padded_width,
            self.padded_height,
        )


def plan_reflect_padding(width: int, height: int, divisor: int = 4) -> PaddingPlan:
    padded_width = _round_up(width, divisor)
    padded_height = _round_up(height, divisor)
    return PaddingPlan(
        original_width=width,
        original_height=height,
        padded_width=padded_width,
        padded_height=padded_height,
        divisor=divisor,
    )


def apply_reflect_padding_rgb(frame: bytes, width: int, height: int, plan: PaddingPlan) -> bytes:
    """Pad an RGB frame by reflecting edge pixels to the planned dimensions."""

    if not plan.needs_padding:
        return frame
    row_stride = width * 3
    if len(frame) != row_stride * height:
        raise ValueError("Frame byte length does not match RGB dimensions.")

    padded = bytearray(plan.padded_width * plan.padded_height * 3)
    for y in range(plan.padded_height):
        source_y = _reflect_index(y, height)
        for x in range(plan.padded_width):
            source_x = _reflect_index(x, width)
            source = source_y * row_stride + source_x * 3
            target = (y * plan.padded_width + x) * 3
            padded[target : target + 3] = frame[source : source + 3]
    return bytes(padded)


def crop_rgb(frame: bytes, width: int, height: int, target_width: int, target_height: int) -> bytes:
    """Crop an RGB frame from the top-left corner to target dimensions."""

    if (width, height) == (target_width, target_height):
        return frame
    if target_width > width or target_height > height:
        raise ValueError("Crop target cannot exceed frame dimensions.")
    row_stride = width * 3
    target_stride = target_width * 3
    cropped = bytearray(target_stride * target_height)
    for y in range(target_height):
        source = y * row_stride
        target = y * target_stride
        cropped[target : target + target_stride] = frame[source : source + target_stride]
    return bytes(cropped)


def _round_up(value: int, divisor: int) -> int:
    remainder = value % divisor
    if remainder == 0:
        return value
    return value + divisor - remainder


def _reflect_index(index: int, size: int) -> int:
    if size <= 1:
        return 0
    while index >= size:
        index = (size * 2 - 2) - index
    return max(index, 0)
