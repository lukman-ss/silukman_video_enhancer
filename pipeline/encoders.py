"""Hardware encoder profiling and preset selection."""

from __future__ import annotations

import platform
import subprocess
from dataclasses import dataclass

from utils.ffmpeg import require_binary


@dataclass(frozen=True)
class EncoderProfile:
    name: str
    encoder: str
    available: bool
    quality_hint: str


HARDWARE_ENCODERS = {
    "nvenc": "h264_nvenc",
    "qsv": "h264_qsv",
    "amf": "h264_amf",
    "videotoolbox": "h264_videotoolbox",
}


def probe_hardware_encoders(encoder_output: str | None = None) -> list[EncoderProfile]:
    """Probe FFmpeg hardware encoders and return availability profiles."""

    output = encoder_output if encoder_output is not None else _ffmpeg_encoder_output()
    profiles = []
    for name, encoder in HARDWARE_ENCODERS.items():
        profiles.append(
            EncoderProfile(
                name=name,
                encoder=encoder,
                available=encoder in output,
                quality_hint=_quality_hint(name),
            )
        )
    return profiles


def select_hardware_encoder(
    profiles: list[EncoderProfile],
    system: str | None = None,
) -> EncoderProfile | None:
    """Select a safe hardware encoder for the current platform."""

    os_name = system or platform.system()
    priority = {
        "Darwin": ("videotoolbox", "qsv", "nvenc", "amf"),
        "Windows": ("nvenc", "qsv", "amf", "videotoolbox"),
        "Linux": ("nvenc", "qsv", "amf", "videotoolbox"),
    }.get(os_name, ("nvenc", "qsv", "amf", "videotoolbox"))
    by_name = {profile.name: profile for profile in profiles if profile.available}
    for name in priority:
        if name in by_name:
            return by_name[name]
    return None


def _ffmpeg_encoder_output() -> str:
    ffmpeg = require_binary("ffmpeg")
    result = subprocess.run(
        [ffmpeg, "-hide_banner", "-encoders"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg encoder probe failed: {result.stderr.strip()}")
    return result.stdout


def _quality_hint(name: str) -> str:
    if name == "nvenc":
        return "fast GPU encode with broad NVIDIA support"
    if name == "qsv":
        return "efficient Intel iGPU/NPU-adjacent encode"
    if name == "amf":
        return "AMD hardware encode"
    return "Apple platform hardware encode"
