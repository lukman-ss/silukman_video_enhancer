"""Tests for pipeline helper utilities: CLI config, bitrate, frame padding, resource governor, and benchmarking."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from app.cli import build_parser, config_from_args
from inference.benchmark import run_onnx_provider_benchmark, run_warmup_benchmark
from pipeline.bitrate import calibrate_bitrate, calibrate_bitrate_from_scan
from pipeline.frame_padding import apply_reflect_padding_rgb, crop_rgb, plan_reflect_padding
from pipeline.resource_governor import ResourceGovernor
from utils.ffmpeg import (
    VideoInfo,
    mux_audio_command,
    restore_audio_command,
    spatial_complexity_scan_command,
    writer_command,
)


class PipelineHelperTests(unittest.TestCase):
    def test_cli_maps_phase1_flags_to_config(self) -> None:
        args = build_parser().parse_args(
            [
                "enhance",
                "-i",
                "input.mp4",
                "--audio-restore",
                "--no-metadata",
                "--quiet",
                "--benchmark",
            ]
        )

        config = config_from_args(args)

        self.assertTrue(config.audio_restore)
        self.assertFalse(config.preserve_metadata)
        self.assertTrue(config.quiet)
        self.assertTrue(config.benchmark)

    def test_warmup_benchmark_ranks_fastest_provider(self) -> None:
        delays = {"CPUExecutionProvider": 2, "CUDAExecutionProvider": 1}

        def warmup(provider: str) -> None:
            for _ in range(delays[provider]):
                pass

        results = run_warmup_benchmark(
            ["CPUExecutionProvider", "CUDAExecutionProvider"],
            warmup,
            frames=2,
        )

        self.assertEqual(results[0].provider, "CUDAExecutionProvider")

    def test_bitrate_calibration_returns_encoder_envelope(self) -> None:
        plan = calibrate_bitrate(
            VideoInfo(width=1280, height=720, fps=30.0, frame_count=10, has_audio=True),
            scale=2,
            requested_crf=18,
        )

        self.assertEqual(plan.crf, 18)
        self.assertGreaterEqual(plan.maxrate_kbps, 2500)
        self.assertEqual(plan.bufsize_kbps, plan.maxrate_kbps * 2)

    def test_bitrate_calibration_accepts_complexity_scan_score(self) -> None:
        info = VideoInfo(width=1280, height=720, fps=30.0, frame_count=10, has_audio=True)
        base = calibrate_bitrate(info, scale=2, requested_crf=18)
        scanned = calibrate_bitrate_from_scan(
            info,
            scale=2,
            requested_crf=18,
            complexity_score=1.25,
        )

        self.assertGreater(scanned.maxrate_kbps, base.maxrate_kbps)

    def test_writer_command_includes_calibrated_rate_limits(self) -> None:
        with patch("utils.ffmpeg.shutil.which", return_value="/usr/bin/ffmpeg"):
            command = writer_command(
                Path("out.mp4"),
                320,
                180,
                640,
                360,
                30.0,
                18,
                maxrate_kbps=2500,
                bufsize_kbps=5000,
            )

        self.assertIn("-maxrate", command)
        self.assertIn("2500k", command)
        self.assertIn("-bufsize", command)
        self.assertIn("5000k", command)

    def test_reflect_padding_rounds_to_model_divisor(self) -> None:
        plan = plan_reflect_padding(1919, 1079, divisor=4)

        self.assertTrue(plan.needs_padding)
        self.assertEqual((plan.padded_width, plan.padded_height), (1920, 1080))

    def test_reflect_padding_and_crop_modify_rgb_bytes(self) -> None:
        plan = plan_reflect_padding(2, 2, divisor=4)
        frame = bytes(
            [
                1,
                1,
                1,
                2,
                2,
                2,
                3,
                3,
                3,
                4,
                4,
                4,
            ]
        )

        padded = apply_reflect_padding_rgb(frame, 2, 2, plan)
        cropped = crop_rgb(padded, 4, 4, 2, 2)

        self.assertEqual(len(padded), 4 * 4 * 3)
        self.assertEqual(cropped, frame)

    def test_spatial_complexity_scan_command_uses_signalstats(self) -> None:
        with patch("utils.ffmpeg.shutil.which", return_value="/usr/bin/ffmpeg"):
            command = spatial_complexity_scan_command(Path("input.mp4"), duration=3)

        self.assertIn("signalstats,metadata=print", command)
        self.assertIn("-t", command)

    def test_mux_command_preserves_metadata_by_default(self) -> None:
        with patch("utils.ffmpeg.shutil.which", return_value="/usr/bin/ffmpeg"):
            command = mux_audio_command(Path("video.mp4"), Path("input.mp4"), Path("out.mp4"))

        self.assertIn("-map_chapters", command)
        self.assertIn("-map_metadata", command)
        self.assertIn("1:s?", command)

    def test_mux_command_can_skip_metadata(self) -> None:
        with patch("utils.ffmpeg.shutil.which", return_value="/usr/bin/ffmpeg"):
            command = mux_audio_command(
                Path("video.mp4"),
                Path("input.mp4"),
                Path("out.mp4"),
                preserve_metadata=False,
            )

        self.assertNotIn("-map_chapters", command)
        self.assertNotIn("-map_metadata", command)

    def test_restore_audio_command_uses_ffmpeg_fft_denoiser(self) -> None:
        with patch("utils.ffmpeg.shutil.which", return_value="/usr/bin/ffmpeg"):
            command = restore_audio_command(Path("input.mp4"), Path("audio.m4a"))

        self.assertIn("-af", command)
        self.assertIn("afftdn=nf=-25", command)

    def test_resource_governor_throttles_only_in_quiet_mode(self) -> None:
        with patch("pipeline.resource_governor.time.sleep") as sleep:
            ResourceGovernor(quiet=False).throttle()
            ResourceGovernor(quiet=True, delay_seconds=0.01).throttle()

        sleep.assert_called_once_with(0.01)

    @patch("inference.benchmark.ONNXFrameUpscaler")
    def test_onnx_provider_benchmark_runs_real_upscaler_calls(self, upscaler: Mock) -> None:
        run_onnx_provider_benchmark(
            Path("model.onnx"),
            ["CPUExecutionProvider"],
            width=2,
            height=2,
            frames=2,
        )

        self.assertEqual(upscaler.return_value.upscale.call_count, 2)


if __name__ == "__main__":
    unittest.main()
