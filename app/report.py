"""Interactive HTML comparison report export."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from html import escape
from pathlib import Path

from utils.ffmpeg import FFmpegNotFoundError, require_binary


@dataclass(frozen=True)
class ReportMetric:
    name: str
    value: str


@dataclass(frozen=True)
class ReportMetadata:
    fps: float | None = None
    hardware_provider: str | None = None

    def as_metrics(self) -> list[ReportMetric]:
        metrics = []
        if self.fps is not None:
            metrics.append(ReportMetric("FPS", f"{self.fps:.2f}"))
        if self.hardware_provider:
            metrics.append(ReportMetric("Hardware Provider", self.hardware_provider))
        return metrics


def render_comparison_report(
    title: str,
    original_path: Path,
    enhanced_path: Path,
    metrics: list[ReportMetric],
    metadata: ReportMetadata | None = None,
) -> str:
    all_metrics = list(metrics)
    if metadata is not None:
        all_metrics.extend(metadata.as_metrics())
    rows = "\n".join(
        f"<tr><th>{escape(metric.name)}</th><td>{escape(metric.value)}</td></tr>"
        for metric in all_metrics
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{escape(title)}</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 2rem; color: #1f2937; }}
    .comparison {{ max-width: 1100px; }}
    .split-view {{ position: relative; overflow: hidden; background: #111827; }}
    .split-view video {{ display: block; width: 100%; }}
    .enhanced-layer {{ position: absolute; inset: 0; clip-path: inset(0 0 0 50%); }}
    .labels {{ display: flex; justify-content: space-between; font-weight: 600; margin: .5rem 0; }}
    input[type="range"] {{ width: 100%; margin: 1rem 0; }}
    table {{ border-collapse: collapse; margin-top: 1rem; }}
    th, td {{ border: 1px solid #d1d5db; padding: .5rem .75rem; text-align: left; }}
  </style>
</head>
<body>
  <main class="comparison">
    <h1>{escape(title)}</h1>
    <div class="labels"><span>Original</span><span>Enhanced</span></div>
    <div class="split-view">
      <video id="original" controls src="{escape(str(original_path))}"></video>
      <video id="enhanced" class="enhanced-layer" muted src="{escape(str(enhanced_path))}"></video>
    </div>
    <input id="split" type="range" min="0" max="100" value="50" aria-label="Comparison split">
    <table>{rows}</table>
  </main>
  <script>
    const split = document.getElementById("split");
    const original = document.getElementById("original");
    const enhanced = document.getElementById("enhanced");
    function updateSplit() {{
      enhanced.style.clipPath = `inset(0 0 0 ${{split.value}}%)`;
    }}
    function syncEnhanced() {{
      if (Math.abs(enhanced.currentTime - original.currentTime) > 0.08) {{
        enhanced.currentTime = original.currentTime;
      }}
    }}
    split.addEventListener("input", updateSplit);
    original.addEventListener("play", () => enhanced.play());
    original.addEventListener("pause", () => enhanced.pause());
    original.addEventListener("seeked", syncEnhanced);
    original.addEventListener("timeupdate", syncEnhanced);
    updateSplit();
  </script>
</body>
</html>"""


def write_comparison_report(
    output_path: Path,
    title: str,
    original_path: Path,
    enhanced_path: Path,
    metrics: list[ReportMetric],
    metadata: ReportMetadata | None = None,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        render_comparison_report(title, original_path, enhanced_path, metrics, metadata),
        encoding="utf-8",
    )
    return output_path


def collect_quality_metrics(original_path: Path, enhanced_path: Path) -> list[ReportMetric]:
    """Collect PSNR/SSIM/VMAF metrics with FFmpeg when available."""

    metrics: list[ReportMetric] = []
    psnr_ssim = _run_ffmpeg_metric(
        [
            "-i",
            str(original_path),
            "-i",
            str(enhanced_path),
            "-lavfi",
            "ssim;[0:v][1:v]psnr",
            "-f",
            "null",
            "-",
        ]
    )
    if psnr_ssim:
        ssim = re.search(r"All:([0-9.]+)", psnr_ssim)
        psnr = re.search(r"average:([0-9.]+)", psnr_ssim)
        if psnr:
            metrics.append(ReportMetric("PSNR", psnr.group(1)))
        if ssim:
            metrics.append(ReportMetric("SSIM", ssim.group(1)))

    vmaf = _run_ffmpeg_metric(
        [
            "-i",
            str(original_path),
            "-i",
            str(enhanced_path),
            "-lavfi",
            "libvmaf",
            "-f",
            "null",
            "-",
        ]
    )
    if vmaf:
        score = re.search(r"VMAF score:\s*([0-9.]+)", vmaf)
        if score:
            metrics.append(ReportMetric("VMAF", score.group(1)))
    return metrics


def _run_ffmpeg_metric(args: list[str]) -> str:
    try:
        ffmpeg = require_binary("ffmpeg")
    except FFmpegNotFoundError:
        return ""
    result = subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "info", *args],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return ""
    return "\n".join([result.stdout, result.stderr])
