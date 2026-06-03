"""Minimal Phase 1 FFmpeg frame streaming pipeline."""

from __future__ import annotations

import subprocess
import tempfile
import time
from pathlib import Path
from typing import Callable, Optional

from app.config import EnhancementConfig
from inference.benchmark import run_warmup_benchmark
from inference.face_restoration import FaceRestorer, plan_face_restoration
from inference.restoration import RestorationProcessor, plan_restoration
from pipeline.bitrate import calibrate_bitrate_from_scan, scan_spatial_complexity
from pipeline.async_processing import AsyncFrameProcessor, DoubleBuffer
from pipeline.checkpoint import CheckpointState, CheckpointStore
from pipeline.chaining import ModelChain, ModelChainStep
from pipeline.destinations import emit_destination, parse_destination
from pipeline.interpolation import plan_interpolation, run_interpolation
from pipeline.artifact_manifest import write_render_manifest
from pipeline.plugin_runtime import call_stage_plugins, collect_ffmpeg_filters
from pipeline.telemetry_collector import TelemetryCollector
from pipeline.resource_governor import ResourceGovernor
from pipeline.roi import ROI, extract_roi_rgb, paste_roi_rgb
from pipeline.temporal import TemporalAnalyzer
from pipeline.upscaler import build_upscaler
from utils.ffmpeg import (
    VideoInfo,
    probe_video,
    reader_command,
    restore_audio_command,
    writer_command,
)


ProgressCallback = Callable[[int, Optional[int], str], None]


def run_enhancement(
    config: EnhancementConfig,
    progress: ProgressCallback | None = None,
    telemetry: TelemetryCollector | None = None,
) -> Path:
    """Stream frames through FFmpeg and preserve audio in the final output."""

    started = time.monotonic()
    config.validate(require_existing_input=True)
    info = probe_video(config.input_path)
    upscaler = build_upscaler(config, info.width, info.height)
    complexity_score = scan_spatial_complexity(config.input_path)
    bitrate_plan = calibrate_bitrate_from_scan(
        info,
        config.scale,
        config.crf,
        complexity_score,
    )
    governor = ResourceGovernor(quiet=config.quiet)
    checkpoint = CheckpointStore(config.checkpoint_dir) if config.checkpoint_dir else None
    config.output_path.parent.mkdir(parents=True, exist_ok=True)
    if progress:
        progress(0, info.frame_count, f"using {upscaler.label}")
        if upscaler.padding.needs_padding:
            progress(
                0,
                info.frame_count,
                (
                    "planned reflective padding "
                    f"{upscaler.padding.original_width}x{upscaler.padding.original_height} "
                    f"-> {upscaler.padding.padded_width}x{upscaler.padding.padded_height}"
                ),
            )
        if config.benchmark:
            benchmark = _benchmark_upscaler(upscaler)
            progress(0, info.frame_count, f"benchmark FPS {benchmark[0].fps:.2f}")

    with tempfile.TemporaryDirectory(prefix="silukman-video-") as temp_dir:
        temp_audio = Path(temp_dir) / "restored_audio.m4a"
        audio_source = config.input_path if info.has_audio else None
        if info.has_audio:
            if config.audio_restore:
                _restore_audio(config.input_path, temp_audio)
                audio_source = temp_audio
        _stream_frames(
            config,
            info,
            config.output_path,
            upscaler,
            bitrate_plan,
            governor,
            progress,
            audio_source=audio_source,
            metadata_source=config.input_path if config.preserve_metadata else None,
            checkpoint=checkpoint,
        )

    for destination in config.destinations:
        emit_destination(config.output_path, parse_destination(destination))

    if config.target_fps and info.fps and config.target_fps > info.fps:
        interpolated_path = config.output_path.with_name(
            f"{config.output_path.stem}_interpolated{config.output_path.suffix}"
        )
        plan = plan_interpolation(info.fps, config.target_fps)
        if progress:
            progress(info.frame_count or 0, info.frame_count, f"interpolating to {config.target_fps:g} fps")
        run_interpolation(config.output_path, interpolated_path, plan)
        interpolated_path.replace(config.output_path)

    if progress:
        progress(info.frame_count or 0, info.frame_count, "completed")
    call_stage_plugins(
        "export_hook",
        config.output_path,
        config=config,
        info=info,
    )
    write_render_manifest(
        config,
        job_id=f"render:{config.output_path.name}",
        notes="Generated automatically after local enhancement.",
    )
    if telemetry is not None:
        elapsed = max(0.001, time.monotonic() - started)
        fps = (info.frame_count or 0) / elapsed if info.frame_count else 0.0
        telemetry.record(
            f"render:{config.output_path.name}",
            provider=config.device,
            fps=fps,
            output_path=str(config.output_path),
            input_path=str(config.input_path),
        )
    return config.output_path


def _stream_frames(
    config: EnhancementConfig,
    info: VideoInfo,
    output_path: Path,
    upscaler,
    bitrate_plan,
    governor: ResourceGovernor,
    progress: ProgressCallback | None,
    audio_source: Path | None = None,
    metadata_source: Path | None = None,
    checkpoint: CheckpointStore | None = None,
) -> None:
    read_frame_size = info.width * info.height * 3
    temporal = TemporalAnalyzer(info.width, info.height)
    processor = _build_frame_processor(config, info, upscaler)
    async_processor = (
        AsyncFrameProcessor(processor, max_workers=config.async_workers)
        if config.async_workers > 1
        else None
    )
    double_buffer = DoubleBuffer() if config.async_workers > 1 else None
    resume_from = _resume_frame_index(checkpoint, config) if checkpoint else 0
    reader = subprocess.Popen(
        reader_command(config.input_path),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    writer = subprocess.Popen(
        writer_command(
            output_path=output_path,
            input_width=info.width if upscaler.uses_ffmpeg_scale else upscaler.output_width,
            input_height=info.height if upscaler.uses_ffmpeg_scale else upscaler.output_height,
            output_width=upscaler.output_width,
            output_height=upscaler.output_height,
            fps=info.fps or 30.0,
            crf=bitrate_plan.crf,
            maxrate_kbps=bitrate_plan.maxrate_kbps,
            bufsize_kbps=bitrate_plan.bufsize_kbps,
            audio_input_path=audio_source,
            metadata_input_path=metadata_source,
            preserve_metadata=config.preserve_metadata,
            video_filters=collect_ffmpeg_filters(config=config, info=info),
        ),
        stdin=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    frame_index = 0
    previous_output: bytes | None = None
    try:
        assert reader.stdout is not None
        assert writer.stdin is not None
        while True:
            frame = reader.stdout.read(read_frame_size)
            if not frame:
                break
            if len(frame) != read_frame_size:
                raise RuntimeError("Received an incomplete frame from FFmpeg.")
            frame_index += 1
            if frame_index <= resume_from and checkpoint is not None:
                processed = checkpoint.load_frame(frame_index)
            else:
                if double_buffer is not None:
                    slot = double_buffer.push(frame)
                    staged_frame = double_buffer.get(slot) or frame
                else:
                    staged_frame = frame

                decision = temporal.analyze(staged_frame)
                if config.dynamic_scale:
                    motion_score = 1.0 - decision.similarity
                    from pipeline.spatiotemporal import choose_spatiotemporal_scale
                    scale_plan = choose_spatiotemporal_scale(config.scale, decision, motion_score)
                    upscaler.active_scale = scale_plan.scale
                else:
                    upscaler.active_scale = config.scale

                if decision.skip_frame and previous_output is not None:
                    processed = previous_output
                elif async_processor is not None:
                    processed = async_processor.process([staged_frame])[0].frame
                else:
                    processed = processor(staged_frame)
                previous_output = processed
                if checkpoint is not None:
                    checkpoint.save_frame(frame_index, processed)
                    checkpoint.save_state(
                        CheckpointState(
                            input_path=str(config.input_path),
                            output_path=str(config.output_path),
                            last_processed_frame_index=frame_index,
                            settings_hash=config.summary(),
                        )
                    )

            # Detect FFmpeg writer crash before writing to avoid "flush of closed file"
            if writer.poll() is not None:
                writer_stderr_early = b""
                if writer.stderr:
                    writer_stderr_early = writer.stderr.read()
                raise RuntimeError(
                    f"FFmpeg writer exited early at frame {frame_index} "
                    f"(code {writer.returncode}): "
                    f"{writer_stderr_early.decode(errors='replace').strip()}"
                )

            try:
                writer.stdin.write(processed)
            except (BrokenPipeError, OSError) as exc:
                writer_stderr_early = b""
                if writer.stderr:
                    writer_stderr_early = writer.stderr.read()
                raise RuntimeError(
                    f"FFmpeg writer pipe broken at frame {frame_index}: "
                    f"{writer_stderr_early.decode(errors='replace').strip() or str(exc)}"
                ) from exc

            governor.throttle()
            if progress:
                progress(frame_index, info.frame_count, "streaming frames")
    finally:
        if writer.stdin and not writer.stdin.closed:
            try:
                writer.stdin.close()
            except (OSError, ValueError):
                pass
        reader_stdout = reader.stdout
        if reader_stdout:
            reader_stdout.close()

    reader_stderr = _communicate_stderr(reader)
    writer_stderr = _communicate_stderr(writer)
    if reader.returncode:
        raise RuntimeError(f"FFmpeg reader failed: {reader_stderr}")
    if writer.returncode:
        raise RuntimeError(f"FFmpeg writer failed: {writer_stderr}")



def _restore_audio(input_path: Path, output_path: Path) -> None:
    result = subprocess.run(
        restore_audio_command(input_path, output_path),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg audio restoration failed: {result.stderr.strip()}")


def _benchmark_upscaler(upscaler):
    frame = bytes(upscaler.input_width * upscaler.input_height * 3)
    return run_warmup_benchmark(["active"], lambda _provider: upscaler.process(frame), frames=3)


def _build_frame_processor(config: EnhancementConfig, info: VideoInfo, upscaler):
    if config.worker_devices:
        from pipeline.distribution import parse_worker_devices
        devices = parse_worker_devices(",".join(config.worker_devices))

        class DistributedFrameProcessor:
            def __init__(self, config: EnhancementConfig, info: VideoInfo, devices):
                self.devices = devices
                self.processors = []
                import dataclasses
                for dev in devices:
                    dev_config = dataclasses.replace(config, device=dev.name)
                    dev_upscaler = build_upscaler(dev_config, info.width, info.height, provider_override=[dev.provider])
                    proc = _build_frame_processor_for_device(dev_config, info, dev_upscaler)
                    self.processors.append((dev_upscaler, proc))
                self._frame_counter = 0

            def __call__(self, frame: bytes) -> bytes:
                current_upscaler, proc = self.processors[self._frame_counter % len(self.processors)]
                current_upscaler.active_scale = upscaler.active_scale
                self._frame_counter += 1
                return proc(frame)

        return DistributedFrameProcessor(config, info, devices)

    return _build_frame_processor_for_device(config, info, upscaler)


def _build_frame_processor_for_device(config: EnhancementConfig, info: VideoInfo, upscaler):
    steps = []
    operations = config.model_chain or config.restoration_ops
    for operation in operations:
        if operation == config.model:
            steps.append(ModelChainStep(operation, upscaler.process))
            continue
        if operation in {"denoise", "deblur", "artifact"}:
            plan = plan_restoration(operation)
            if not plan.enabled:
                continue
            restoration = RestorationProcessor(plan, config.device, enable_fp16=config.fp16)
            steps.append(
                ModelChainStep(
                    operation,
                    lambda frame, restoration=restoration: restoration.process(
                        frame,
                        info.width,
                        info.height,
                    ),
                )
            )
    if config.face_model:
        face_plan = plan_face_restoration(config.face_model)
        if face_plan.enabled:
            face_restorer = FaceRestorer(face_plan, config.device, enable_fp16=config.fp16)
            steps.append(
                ModelChainStep(
                    config.face_model,
                    lambda frame, face_restorer=face_restorer: face_restorer.restore(
                        frame,
                        info.width,
                        info.height,
                    ),
                )
            )
    if not any(step.name == config.model for step in steps):
        steps.append(ModelChainStep(config.model, upscaler.process))
    chain = ModelChain(steps)
    roi = ROI(*config.roi) if config.roi and config.scale == 1 else None

    def process(frame: bytes) -> bytes:
        if roi is None:
            processed = chain.process(frame)
            return call_stage_plugins(
                "model",
                processed,
                config=config,
                info=info,
                width=upscaler.output_width,
                height=upscaler.output_height,
            )
        region = extract_roi_rgb(frame, info.width, info.height, roi)
        processed_region = chain.process(region)
        processed_region = call_stage_plugins(
            "model",
            processed_region,
            config=config,
            info=info,
            width=roi.width,
            height=roi.height,
        )
        return paste_roi_rgb(frame, info.width, info.height, roi, processed_region)

    return process


def _resume_frame_index(checkpoint: CheckpointStore, config: EnhancementConfig) -> int:
    state = checkpoint.load_state()
    if state is None:
        return 0
    if state.input_path != str(config.input_path) or state.output_path != str(config.output_path):
        return 0
    if state.settings_hash != config.summary():
        return 0
    return state.last_processed_frame_index


def _communicate_stderr(process: subprocess.Popen) -> str:
    _, stderr = process.communicate()
    if isinstance(stderr, bytes):
        return stderr.decode(errors="replace").strip()
    return (stderr or "").strip()
