"""Professional delivery codec presets."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DeliveryPreset:
    name: str
    video_args: tuple[str, ...]
    audio_args: tuple[str, ...] = ("-c:a", "aac", "-b:a", "192k")

    def ffmpeg_args(self) -> list[str]:
        return [*self.video_args, *self.audio_args]


DELIVERY_PRESETS = {
    "av1": DeliveryPreset(
        "av1",
        ("-c:v", "libsvtav1", "-crf", "28", "-pix_fmt", "yuv420p10le"),
    ),
    "hevc-10bit": DeliveryPreset(
        "hevc-10bit",
        ("-c:v", "libx265", "-crf", "20", "-pix_fmt", "yuv420p10le"),
    ),
    "prores": DeliveryPreset(
        "prores",
        ("-c:v", "prores_ks", "-profile:v", "3", "-pix_fmt", "yuv422p10le"),
        ("-c:a", "pcm_s16le"),
    ),
    "dnxhr": DeliveryPreset(
        "dnxhr",
        ("-c:v", "dnxhd", "-profile:v", "dnxhr_hq", "-pix_fmt", "yuv422p"),
        ("-c:a", "pcm_s16le"),
    ),
    "archival": DeliveryPreset(
        "archival",
        ("-c:v", "ffv1", "-level", "3", "-pix_fmt", "yuv444p10le"),
        ("-c:a", "flac"),
    ),
}


def get_delivery_preset(name: str) -> DeliveryPreset:
    try:
        return DELIVERY_PRESETS[name]
    except KeyError as exc:
        available = ", ".join(sorted(DELIVERY_PRESETS))
        raise ValueError(f"Unknown delivery preset `{name}`. Available: {available}") from exc


def delivery_command_args(name: str) -> list[str]:
    return get_delivery_preset(name).ffmpeg_args()
