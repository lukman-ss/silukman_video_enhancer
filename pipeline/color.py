"""Color pipeline helpers for 3D LUT and HDR planning."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Lut3D:
    title: str
    size: int
    values: tuple[tuple[float, float, float], ...]


@dataclass(frozen=True)
class HdrPlan:
    enabled: bool
    pixel_format: str
    color_primaries: str
    color_trc: str
    colorspace: str

    def ffmpeg_args(self) -> list[str]:
        if not self.enabled:
            return ["-pix_fmt", self.pixel_format]
        return [
            "-pix_fmt",
            self.pixel_format,
            "-color_primaries",
            self.color_primaries,
            "-color_trc",
            self.color_trc,
            "-colorspace",
            self.colorspace,
        ]


@dataclass(frozen=True)
class ToneMapPreset:
    name: str
    filter_chain: str


TONE_MAP_PRESETS = {
    "hdr-to-sdr": ToneMapPreset(
        "hdr-to-sdr",
        "zscale=t=linear:npl=100,tonemap=mobius:param=0.3,zscale=t=bt709:m=bt709:r=tv",
    ),
    "sdr-to-hdr": ToneMapPreset(
        "sdr-to-hdr",
        "zscale=t=linear:npl=100,zscale=t=smpte2084:m=bt2020nc:r=tv",
    ),
    "hdr-passthrough": ToneMapPreset("hdr-passthrough", "null"),
}


def parse_cube_lut(path: Path) -> Lut3D:
    """Parse a local .cube 3D LUT file."""

    if path.suffix.lower() != ".cube":
        raise ValueError("3D LUT files must use the .cube extension.")
    title = path.stem
    size = 0
    values: list[tuple[float, float, float]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        upper = line.upper()
        if upper.startswith("TITLE"):
            title = line.split(maxsplit=1)[1].strip().strip('"')
            continue
        if upper.startswith("LUT_3D_SIZE"):
            size = int(line.split()[1])
            continue
        parts = line.split()
        if len(parts) == 3:
            values.append(tuple(float(part) for part in parts))
    if size <= 0:
        raise ValueError("3D LUT is missing LUT_3D_SIZE.")
    expected = size**3
    if len(values) != expected:
        raise ValueError(f"3D LUT expected {expected} values, found {len(values)}.")
    return Lut3D(title=title, size=size, values=tuple(values))


def lut_filter_arg(path: Path) -> str:
    parse_cube_lut(path)
    return f"lut3d=file='{path.as_posix()}'"


def plan_hdr_output(
    hdr: bool,
    transfer: str = "pq",
    wide_gamut: bool = True,
    ten_bit: bool = True,
) -> HdrPlan:
    """Plan FFmpeg pixel format and HDR metadata flags."""

    pixel_format = "yuv420p10le" if ten_bit else "yuv420p"
    if not hdr:
        return HdrPlan(False, pixel_format, "bt709", "bt709", "bt709")
    color_trc = "smpte2084" if transfer.lower() == "pq" else "arib-std-b67"
    primaries = "bt2020" if wide_gamut else "bt709"
    colorspace = "bt2020nc" if wide_gamut else "bt709"
    return HdrPlan(True, pixel_format, primaries, color_trc, colorspace)


def tone_map_filter(name: str) -> str:
    try:
        return TONE_MAP_PRESETS[name].filter_chain
    except KeyError as exc:
        available = ", ".join(sorted(TONE_MAP_PRESETS))
        raise ValueError(f"Unknown tone-map preset `{name}`. Available: {available}") from exc
