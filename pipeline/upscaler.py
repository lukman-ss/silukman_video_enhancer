"""Upscaler selection for the Phase 1 pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from app.config import EnhancementConfig
from inference.runtime import ModelLoadError, ONNXFrameUpscaler, ONNXRuntimeUnavailableError
from models.registry import get_model_spec, resolve_model_path, verify_model_file
from pipeline.frame_padding import (
    PaddingPlan,
    apply_reflect_padding_rgb,
    crop_rgb,
    plan_reflect_padding,
)


def resize_rgb(frame: bytes, width: int, height: int, target_width: int, target_height: int) -> bytes:
    if (width, height) == (target_width, target_height):
        return frame
    output = bytearray(target_width * target_height * 3)
    x_ratio = width / target_width
    y_ratio = height / target_height
    for y in range(target_height):
        src_y = int(y * y_ratio)
        src_row_offset = src_y * width * 3
        dst_row_offset = y * target_width * 3
        for x in range(target_width):
            src_x = int(x * x_ratio)
            src_pixel = src_row_offset + src_x * 3
            dst_pixel = dst_row_offset + x * 3
            output[dst_pixel : dst_pixel + 3] = frame[src_pixel : src_pixel + 3]
    return bytes(output)


@dataclass
class Upscaler:
    input_width: int
    input_height: int
    output_width: int
    output_height: int
    label: str
    padding: PaddingPlan
    onnx: Optional[ONNXFrameUpscaler] = None
    active_scale: Optional[int] = None

    @property
    def uses_ffmpeg_scale(self) -> bool:
        return self.onnx is None and (
            self.output_width != self.input_width
            or self.output_height != self.input_height
        )

    def process(self, frame: bytes) -> bytes:
        if self.onnx is None:
            return frame
        base_scale = max(1, self.output_width // self.input_width)
        current_scale = self.active_scale if self.active_scale is not None else base_scale

        if current_scale == 1:
            return resize_rgb(frame, self.input_width, self.input_height, self.output_width, self.output_height)

        padded = apply_reflect_padding_rgb(
            frame,
            self.input_width,
            self.input_height,
            self.padding,
        )
        padded_output = self.onnx.upscale(
            padded,
            self.padding.padded_width,
            self.padding.padded_height,
        )
        return_frame = crop_rgb(
            padded_output,
            self.padding.padded_width * base_scale,
            self.padding.padded_height * base_scale,
            self.output_width,
            self.output_height,
        )

        if current_scale != base_scale:
            temp_w = self.input_width * current_scale
            temp_h = self.input_height * current_scale
            downsampled = resize_rgb(return_frame, self.output_width, self.output_height, temp_w, temp_h)
            return resize_rgb(downsampled, temp_w, temp_h, self.output_width, self.output_height)

        return return_frame


def build_upscaler(
    config: EnhancementConfig,
    width: int,
    height: int,
    provider_override: Optional[Sequence[str]] = None,
) -> Upscaler:
    spec = get_model_spec(config.model)
    padding = plan_reflect_padding(width, height)
    output_width = width * config.scale
    output_height = height * config.scale
    model_path = resolve_model_path(config.model)

    if model_path.exists() and verify_model_file(model_path, spec.sha256):
        try:
            return Upscaler(
                input_width=width,
                input_height=height,
                output_width=output_width,
                output_height=output_height,
                label=f"ONNX {config.model}",
                padding=padding,
                onnx=ONNXFrameUpscaler(
                    model_path,
                    config.device,
                    provider_override=provider_override,
                    enable_fp16=config.fp16,
                ),
            )
        except (ModelLoadError, ONNXRuntimeUnavailableError):
            pass

    return Upscaler(
        input_width=width,
        input_height=height,
        output_width=output_width,
        output_height=output_height,
        label="FFmpeg Lanczos baseline",
        padding=padding,
    )
