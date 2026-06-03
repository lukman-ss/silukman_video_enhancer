"""Region of Interest helpers for selective frame processing."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ROI:
    x: int
    y: int
    width: int
    height: int

    def validate(self, frame_width: int, frame_height: int) -> None:
        if self.x < 0 or self.y < 0 or self.width <= 0 or self.height <= 0:
            raise ValueError("ROI values must be positive and inside the frame.")
        if self.x + self.width > frame_width or self.y + self.height > frame_height:
            raise ValueError("ROI exceeds frame bounds.")


def parse_roi(value: str) -> ROI:
    parts = [int(part.strip()) for part in value.split(",")]
    if len(parts) != 4:
        raise ValueError("ROI must be formatted as x,y,width,height")
    return ROI(*parts)


def extract_roi_rgb(frame: bytes, frame_width: int, frame_height: int, roi: ROI) -> bytes:
    roi.validate(frame_width, frame_height)
    row_stride = frame_width * 3
    roi_stride = roi.width * 3
    output = bytearray(roi_stride * roi.height)
    for row in range(roi.height):
        source = ((roi.y + row) * row_stride) + (roi.x * 3)
        target = row * roi_stride
        output[target : target + roi_stride] = frame[source : source + roi_stride]
    return bytes(output)


def paste_roi_rgb(
    frame: bytes,
    frame_width: int,
    frame_height: int,
    roi: ROI,
    roi_frame: bytes,
) -> bytes:
    roi.validate(frame_width, frame_height)
    expected = roi.width * roi.height * 3
    if len(roi_frame) != expected:
        raise ValueError("ROI frame byte length does not match ROI dimensions.")
    row_stride = frame_width * 3
    roi_stride = roi.width * 3
    output = bytearray(frame)
    for row in range(roi.height):
        target = ((roi.y + row) * row_stride) + (roi.x * 3)
        source = row * roi_stride
        output[target : target + roi_stride] = roi_frame[source : source + roi_stride]
    return bytes(output)
