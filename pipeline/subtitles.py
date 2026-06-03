"""Subtitle OCR and translation planning."""

from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from utils.ffmpeg import require_binary


@dataclass(frozen=True)
class SubtitleJob:
    input_video: Path
    output_srt: Path
    source_language: str
    target_language: str | None = None


@dataclass(frozen=True)
class SubtitleCue:
    index: int
    start_seconds: float
    end_seconds: float
    text: str


def build_subtitle_job(
    input_video: Path,
    output_srt: Path,
    source_language: str = "auto",
    target_language: str | None = None,
) -> SubtitleJob:
    return SubtitleJob(
        input_video=input_video,
        output_srt=output_srt,
        source_language=source_language,
        target_language=target_language,
    )


OcrEngine = Callable[[Path], str]
Translator = Callable[[str, str, str], str]


@dataclass(frozen=True)
class LocalOcrEngine:
    command: tuple[str, ...]

    def __call__(self, frame_path: Path) -> str:
        result = subprocess.run(
            [*self.command, str(frame_path)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"OCR engine failed: {result.stderr.strip()}")
        return result.stdout.strip()


@dataclass(frozen=True)
class LocalTranslator:
    command: tuple[str, ...]

    def __call__(self, text: str, source_language: str, target_language: str) -> str:
        result = subprocess.run(
            [*self.command, "--source", source_language, "--target", target_language],
            input=text,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Translation engine failed: {result.stderr.strip()}")
        return result.stdout.strip()


def build_local_ocr_engine(command: str | Iterable[str]) -> LocalOcrEngine:
    return LocalOcrEngine(tuple(_split_command(command)))


def build_local_translator(command: str | Iterable[str]) -> LocalTranslator:
    return LocalTranslator(tuple(_split_command(command)))


def run_subtitle_ocr_job(
    job: SubtitleJob,
    ocr_engine: OcrEngine,
    translator: Translator | None = None,
    sample_interval_seconds: float = 2.0,
) -> Path:
    """Extract sampled frames, OCR them, optionally translate, and write SRT."""

    if sample_interval_seconds <= 0:
        raise ValueError("sample_interval_seconds must be greater than zero.")
    with tempfile.TemporaryDirectory(prefix="silukman-subtitles-") as temp_dir:
        frame_dir = Path(temp_dir)
        _extract_sampled_frames(job.input_video, frame_dir, sample_interval_seconds)
        cues = _build_cues_from_frames(
            frame_dir.glob("frame-*.png"),
            job,
            ocr_engine,
            translator,
            sample_interval_seconds,
        )
    write_srt(job.output_srt, cues)
    return job.output_srt


def write_srt(output_path: Path, cues: Iterable[SubtitleCue]) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    blocks = []
    for cue in cues:
        text = cue.text.strip()
        if not text:
            continue
        blocks.append(
            "\n".join(
                [
                    str(cue.index),
                    f"{_format_srt_time(cue.start_seconds)} --> {_format_srt_time(cue.end_seconds)}",
                    text,
                ]
            )
        )
    output_path.write_text("\n\n".join(blocks) + ("\n" if blocks else ""), encoding="utf-8")
    return output_path


def _extract_sampled_frames(
    input_video: Path,
    frame_dir: Path,
    sample_interval_seconds: float,
) -> None:
    ffmpeg = require_binary("ffmpeg")
    output_pattern = frame_dir / "frame-%06d.png"
    result = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(input_video),
            "-vf",
            f"fps=1/{sample_interval_seconds}",
            str(output_pattern),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Subtitle frame extraction failed: {result.stderr.strip()}")


def _build_cues_from_frames(
    frames: Iterable[Path],
    job: SubtitleJob,
    ocr_engine: OcrEngine,
    translator: Translator | None,
    sample_interval_seconds: float,
) -> list[SubtitleCue]:
    cues = []
    for index, frame in enumerate(sorted(frames), start=1):
        text = ocr_engine(frame).strip()
        if text and translator is not None and job.target_language:
            text = translator(text, job.source_language, job.target_language)
        if text:
            start = (index - 1) * sample_interval_seconds
            cues.append(
                SubtitleCue(
                    index=len(cues) + 1,
                    start_seconds=start,
                    end_seconds=start + sample_interval_seconds,
                    text=text,
                )
            )
    return cues


def _format_srt_time(seconds: float) -> str:
    milliseconds = int(round(seconds * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def _split_command(command: str | Iterable[str]) -> list[str]:
    if isinstance(command, str):
        parts = [part for part in command.split(" ") if part]
    else:
        parts = list(command)
    if not parts:
        raise ValueError("Engine command must not be empty.")
    return parts
