"""Command-line interface for the local video enhancer."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from app.batch import build_batch_configs
from app.config import EnhancementConfig
from app.progress import CliProgressMonitor
from pipeline.chaining import parse_model_chain
from pipeline.destinations import parse_destination
from pipeline.distribution import parse_worker_devices
from pipeline.roi import parse_roi
from pipeline.runner import run_enhancement
from utils.ffmpeg import FFmpegNotFoundError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="silukman-video-enhancer",
        description="Offline local-first video enhancement.",
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=("enhance", "desktop"),
        default="enhance",
        help="Run a CLI enhancement job or launch the Python desktop app.",
    )
    parser.add_argument("-i", "--input", type=Path, help="Path to the source video.")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("output.mp4"),
        help="Path to save the enhanced output video.",
    )
    parser.add_argument(
        "-m",
        "--model",
        choices=("realesrgan", "swinir", "srcnn"),
        default="realesrgan",
        help="AI model to use.",
    )
    parser.add_argument(
        "-s",
        "--scale",
        type=int,
        choices=(1, 2, 4),
        default=2,
        help="Upscaling multiplier.",
    )
    parser.add_argument(
        "--device",
        choices=("auto", "cpu", "cuda", "coreml", "directml"),
        default="auto",
        help="Target execution provider.",
    )
    parser.add_argument(
        "--crf",
        type=int,
        default=18,
        help="Constant Rate Factor for output encoding.",
    )
    parser.add_argument("--denoise", action="store_true", help="Enable denoising.")
    parser.add_argument(
        "--audio-restore",
        action="store_true",
        help="Apply FFmpeg FFT audio denoising before final muxing.",
    )
    parser.add_argument(
        "--color-correct",
        action="store_true",
        help="Enable automatic color correction.",
    )
    parser.add_argument(
        "--no-metadata",
        action="store_true",
        help="Skip source metadata, subtitle, and chapter mapping.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Throttle frame processing to reduce heat and foreground lag.",
    )
    parser.add_argument(
        "--benchmark",
        action="store_true",
        help="Run a short startup benchmark before processing.",
    )
    parser.add_argument(
        "--batch",
        action="store_true",
        help="Treat --input as a folder and process all supported videos inside it.",
    )
    parser.add_argument(
        "--chain",
        default="",
        help="Comma-separated model chain, e.g. denoise,realesrgan.",
    )
    parser.add_argument(
        "--roi",
        help="Selective processing region as x,y,width,height.",
    )
    parser.add_argument(
        "--fp16",
        action="store_true",
        help="Enable FP16 quantization when the selected provider supports it.",
    )
    parser.add_argument(
        "--destination",
        action="append",
        default=[],
        help="Extra output destination as path[,start,end,copy].",
    )
    parser.add_argument(
        "--face-model",
        choices=("gfpgan", "codeformer"),
        help="Enable face restoration with the selected ONNX model.",
    )
    parser.add_argument(
        "--dynamic-scale",
        action="store_true",
        help="Enable dynamic spatial-temporal scaling decisions.",
    )
    parser.add_argument(
        "--async-workers",
        type=int,
        default=1,
        help="Thread-pool workers for post-processing.",
    )
    parser.add_argument(
        "--checkpoint-dir",
        type=Path,
        help="Directory for resumable checkpoint state and compressed frame cache.",
    )
    parser.add_argument(
        "--worker-devices",
        default="",
        help="Comma-separated worker devices, e.g. cuda:CUDAExecutionProvider,cpu:CPUExecutionProvider.",
    )
    parser.add_argument(
        "--restore",
        action="append",
        choices=("denoise", "deblur", "artifact"),
        default=[],
        help="Add a restoration operation backed by an ONNX model.",
    )
    parser.add_argument(
        "--target-fps",
        type=float,
        help="Interpolate the final enhanced output to this target frame rate.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and print settings without running the pipeline.",
    )
    return parser


def config_from_args(args: argparse.Namespace) -> EnhancementConfig:
    if args.input is None:
        raise ValueError("CLI enhancement requires --input.")
    roi = parse_roi(args.roi) if args.roi else None
    destinations = tuple(args.destination)
    worker_devices = tuple(device.name for device in parse_worker_devices(args.worker_devices)) if args.worker_devices else ()
    return EnhancementConfig(
        input_path=args.input,
        output_path=args.output,
        model=args.model,
        scale=args.scale,
        device=args.device,
        crf=args.crf,
        denoise=args.denoise,
        color_correct=args.color_correct,
        audio_restore=args.audio_restore,
        preserve_metadata=not args.no_metadata,
        quiet=args.quiet,
        benchmark=args.benchmark,
        batch=args.batch,
        model_chain=tuple(parse_model_chain(args.chain)),
        roi=(roi.x, roi.y, roi.width, roi.height) if roi else None,
        fp16=args.fp16,
        destinations=destinations,
        face_model=args.face_model,
        dynamic_scale=args.dynamic_scale,
        async_workers=args.async_workers,
        checkpoint_dir=args.checkpoint_dir,
        worker_devices=worker_devices,
        restoration_ops=tuple(args.restore),
        target_fps=args.target_fps,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "desktop":
        from ui.desktop import main as desktop_main

        return desktop_main()

    try:
        config = config_from_args(args)
        config.validate(require_existing_input=not args.dry_run)
    except ValueError as exc:
        parser.error(str(exc))

    if args.dry_run:
        print(f"Dry run OK: {config.summary()}")
        return 0

    try:
        with CliProgressMonitor() as progress:
            if config.batch:
                outputs = [
                    run_enhancement(batch_config, progress.update)
                    for batch_config in build_batch_configs(config, config.output_path)
                ]
                output_path = outputs[-1] if outputs else config.output_path
            else:
                output_path = run_enhancement(config, progress.update)
    except FFmpegNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 127
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"Enhanced video written to: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
