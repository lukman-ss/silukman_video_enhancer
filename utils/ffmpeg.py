"""Small FFmpeg/ffprobe helpers for the video pipeline."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import platform
import zipfile
import tarfile
import ssl
import urllib.request


class FFmpegNotFoundError(RuntimeError):
    """Raised when FFmpeg or ffprobe is not available on PATH."""


def _download_binary(name: str, bin_dir: Path) -> Path:
    bin_dir.mkdir(parents=True, exist_ok=True)
    system = platform.system()
    machine = platform.machine()

    ext = ".exe" if system == "Windows" else ""
    target_path = bin_dir / f"{name}{ext}"
    if target_path.exists():
        return target_path

    print(f"Downloading static {name} binary for {system} ({machine}) to {target_path}...")

    # Create a non-verifying SSL context just in case of local certificate issues
    ssl_context = ssl._create_unverified_context()

    url = ""
    if system == "Darwin":
        is_arm = "arm" in machine.lower() or "aarch" in machine.lower()
        if is_arm:
            if name == "ffmpeg":
                url = "https://www.osxexperts.net/ffmpeg71arm.zip"
            else:
                url = "https://www.osxexperts.net/ffprobe71arm.zip"
        else:
            if name == "ffmpeg":
                url = "https://evermeet.cx/ffmpeg/getrelease/zip"
            else:
                url = "https://evermeet.cx/ffmpeg/getrelease/ffprobe/zip"
    elif system == "Windows":
        url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
    elif system == "Linux":
        if "arm" in machine or "aarch" in machine:
            url = "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-arm64-static.tar.xz"
        else:
            url = "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz"
    else:
        raise RuntimeError(f"Unsupported operating system: {system}")

    archive_ext = ".zip" if (system in ("Darwin", "Windows")) else ".tar.xz"
    archive_path = bin_dir / f"temp_{name}{archive_ext}"

    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            },
        )
        with urllib.request.urlopen(req, context=ssl_context) as response, open(
            archive_path, "wb"
        ) as out_file:
            shutil.copyfileobj(response, out_file)

        if archive_ext == ".zip":
            with zipfile.ZipFile(archive_path) as z:
                for member in z.namelist():
                    member_path = Path(member)
                    for bin_name in ("ffmpeg", "ffprobe"):
                        if member_path.name.lower() == f"{bin_name}{ext}".lower():
                            with z.open(member) as source, open(
                                bin_dir / f"{bin_name}{ext}", "wb"
                            ) as target:
                                shutil.copyfileobj(source, target)
        else:
            with tarfile.open(archive_path, "r:xz") as tar:
                for member in tar.getmembers():
                    member_path = Path(member.name)
                    for bin_name in ("ffmpeg", "ffprobe"):
                        if member_path.name == bin_name:
                            f = tar.extractfile(member)
                            if f is not None:
                                with open(bin_dir / bin_name, "wb") as target:
                                    shutil.copyfileobj(f, target)

        if archive_path.exists():
            archive_path.unlink()

        if system != "Windows":
            target_path.chmod(0o755)
            # Also try to chmod the other binary if it was extracted
            other_name = "ffprobe" if name == "ffmpeg" else "ffmpeg"
            other_path = bin_dir / other_name
            if other_path.exists():
                other_path.chmod(0o755)

        print(f"Successfully downloaded and installed {name} to {target_path}")
        return target_path
    except Exception as e:
        if archive_path.exists():
            archive_path.unlink()
        raise RuntimeError(f"Failed to automatically download {name}: {e}") from e


@dataclass(frozen=True)
class VideoInfo:
    width: int
    height: int
    fps: float
    frame_count: int | None
    has_audio: bool


def _expected_arch() -> str:
    """Return the expected binary architecture string for the current machine."""
    machine = platform.machine().lower()
    if "arm" in machine or "aarch" in machine:
        return "arm64"
    return "x86_64"


def _binary_arch(path: Path) -> str | None:
    """Return the architecture of a Mach-O or ELF binary, or None on failure."""
    try:
        result = subprocess.run(
            ["file", str(path)], capture_output=True, text=True, timeout=5
        )
        output = result.stdout.lower()
        if "arm64" in output or "aarch64" in output:
            return "arm64"
        if "x86_64" in output or "x86-64" in output:
            return "x86_64"
    except Exception:
        pass
    return None


def _is_arch_compatible(path: Path) -> bool:
    """Return True if the binary matches the current machine architecture."""
    system = platform.system()
    if system == "Windows":
        return True  # Windows binaries are always .exe; no cross-arch risk here
    arch = _binary_arch(path)
    if arch is None:
        return True  # cannot determine; assume OK
    return arch == _expected_arch()


def require_binary(name: str) -> str:
    path = shutil.which(name)
    if path is not None:
        return path

    bin_dir = Path(__file__).parent.parent / "bin"
    system = platform.system()
    ext = ".exe" if system == "Windows" else ""
    local_path = bin_dir / f"{name}{ext}"
    if local_path.exists():
        if _is_arch_compatible(local_path):
            return str(local_path)
        # Wrong architecture — delete and re-download the correct one
        print(
            f"[ffmpeg] {local_path.name} is {_binary_arch(local_path)} but "
            f"current machine is {_expected_arch()}. Re-downloading correct version..."
        )
        local_path.unlink()

    try:
        downloaded = _download_binary(name, bin_dir)
        if downloaded.exists():
            return str(downloaded)
    except Exception as exc:
        raise FFmpegNotFoundError(
            f"`{name}` was not found on PATH and auto-download failed: {exc}. "
            "Please install FFmpeg manually."
        ) from exc

    raise FFmpegNotFoundError(
        f"`{name}` was not found on PATH. Install FFmpeg and try again."
    )


def probe_video(input_path: Path) -> VideoInfo:
    ffprobe = require_binary("ffprobe")
    command = [
        ffprobe,
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_streams",
        str(input_path),
    ]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    payload = json.loads(result.stdout)
    streams = payload.get("streams", [])
    video_stream = next(
        (stream for stream in streams if stream.get("codec_type") == "video"),
        None,
    )
    if video_stream is None:
        raise ValueError(f"No video stream found in input: {input_path}")

    return VideoInfo(
        width=int(video_stream["width"]),
        height=int(video_stream["height"]),
        fps=_parse_rate(video_stream.get("avg_frame_rate", "0/1")),
        frame_count=_parse_frame_count(video_stream.get("nb_frames")),
        has_audio=any(stream.get("codec_type") == "audio" for stream in streams),
    )


def reader_command(input_path: Path) -> list[str]:
    ffmpeg = require_binary("ffmpeg")
    return [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(input_path),
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-vcodec",
        "rawvideo",
        "-",
    ]


def writer_command(
    output_path: Path,
    input_width: int,
    input_height: int,
    output_width: int,
    output_height: int,
    fps: float,
    crf: int,
    maxrate_kbps: int | None = None,
    bufsize_kbps: int | None = None,
    audio_input_path: Path | None = None,
    metadata_input_path: Path | None = None,
    preserve_metadata: bool = True,
    video_filters: tuple[str, ...] = (),
) -> list[str]:
    ffmpeg = require_binary("ffmpeg")
    command = [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-s:v",
        f"{input_width}x{input_height}",
        "-r",
        f"{fps:.6f}",
        "-i",
        "-",
    ]
    input_index = 1
    audio_index = None
    metadata_index = None
    if audio_input_path is not None:
        command.extend(["-i", str(audio_input_path)])
        audio_index = input_index
        input_index += 1
    if preserve_metadata and metadata_input_path is not None:
        if metadata_input_path == audio_input_path:
            metadata_index = audio_index
        else:
            command.extend(["-i", str(metadata_input_path)])
            metadata_index = input_index
            input_index += 1

    command.extend(
        [
        "-c:v",
        "libx264",
        "-crf",
        str(crf),
        "-pix_fmt",
        "yuv420p",
        ]
    )
    if audio_index is not None:
        command.extend(["-c:a", "copy", "-map", "0:v:0", "-map", f"{audio_index}:a:0?"])
    else:
        command.append("-an")
    if metadata_index is not None:
        command.extend(
            [
                "-map",
                f"{metadata_index}:s?",
                "-map_chapters",
                str(metadata_index),
                "-map_metadata",
                str(metadata_index),
            ]
        )
    if maxrate_kbps is not None and bufsize_kbps is not None:
        command.extend(
            [
                "-maxrate",
                f"{maxrate_kbps}k",
                "-bufsize",
                f"{bufsize_kbps}k",
            ]
        )
    filters = list(video_filters)
    if (output_width, output_height) != (input_width, input_height):
        filters.append(f"scale={output_width}:{output_height}:flags=lanczos")
    if filters:
        command.extend(["-vf", ",".join(filters)])
    command.append(str(output_path))
    return command


def mux_audio_command(
    video_path: Path,
    input_path: Path,
    output_path: Path,
    preserve_metadata: bool = True,
) -> list[str]:
    ffmpeg = require_binary("ffmpeg")
    command = [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(video_path),
        "-i",
        str(input_path),
        "-c:v",
        "copy",
        "-c:a",
        "copy",
        "-map",
        "0:v:0",
        "-map",
        "1:a:0?",
        "-shortest",
    ]
    if preserve_metadata:
        command.extend(
            [
                "-map",
                "1:s?",
                "-map_chapters",
                "1",
                "-map_metadata",
                "1",
            ]
        )
    command.append(str(output_path))
    return command


def restore_audio_command(input_path: Path, output_path: Path) -> list[str]:
    ffmpeg = require_binary("ffmpeg")
    return [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(input_path),
        "-vn",
        "-af",
        "afftdn=nf=-25",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        str(output_path),
    ]


def spatial_complexity_scan_command(input_path: Path, duration: int = 3) -> list[str]:
    ffmpeg = require_binary("ffmpeg")
    return [
        ffmpeg,
        "-hide_banner",
        "-i",
        str(input_path),
        "-t",
        str(duration),
        "-vf",
        "signalstats,metadata=print",
        "-an",
        "-f",
        "null",
        "-",
    ]


def destination_command(source_path: Path, destination: Any) -> list[str]:
    ffmpeg = require_binary("ffmpeg")
    command = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error"]
    if destination.start_seconds is not None:
        command.extend(["-ss", str(destination.start_seconds)])
    command.extend(["-i", str(source_path)])
    if destination.end_seconds is not None and destination.start_seconds is not None:
        command.extend(["-t", str(destination.end_seconds - destination.start_seconds)])
    elif destination.end_seconds is not None:
        command.extend(["-to", str(destination.end_seconds)])
    if destination.stream_copy:
        command.extend(["-c", "copy"])
    command.append(str(destination.path))
    return command


def _parse_rate(rate: str) -> float:
    numerator, _, denominator = rate.partition("/")
    if not denominator:
        return float(numerator or 0)
    denominator_value = float(denominator)
    if denominator_value == 0:
        return 0.0
    return float(numerator) / denominator_value


def _parse_frame_count(value: str | None) -> int | None:
    if value is None or value == "N/A":
        return None
    return int(value)
