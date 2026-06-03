"""Tests for pipeline checkpointing, frame distribution across devices, and restoration processing."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.cli import build_parser, config_from_args
from inference.restoration import RestorationProcessor, plan_restoration
from pipeline.checkpoint import CheckpointState, CheckpointStore
from pipeline.distribution import assign_frames_to_devices, parse_worker_devices


class CheckpointTests(unittest.TestCase):
    def test_checkpoint_store_saves_state_and_compressed_frame(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = CheckpointStore(Path(temp_dir))
            state = CheckpointState(
                input_path="in.mp4",
                output_path="out.mp4",
                last_processed_frame_index=7,
                settings_hash="abc",
            )

            store.save_state(state)
            frame_path = store.save_frame(7, b"frame-bytes")
            loaded = store.load_state()
            frame = store.load_frame(7)

        self.assertEqual(loaded, state)
        self.assertEqual(frame, b"frame-bytes")
        self.assertEqual(frame_path.suffix, ".zlib")


class DistributionTests(unittest.TestCase):
    def test_parse_worker_devices_and_assign_round_robin(self) -> None:
        devices = parse_worker_devices("cuda0:CUDAExecutionProvider,cpu:CPUExecutionProvider")
        assignments = assign_frames_to_devices(range(4), devices)

        self.assertEqual([device.name for device in devices], ["cuda0", "cpu"])
        self.assertEqual(
            [assignment.device.name for assignment in assignments],
            ["cuda0", "cpu", "cuda0", "cpu"],
        )

    def test_parse_worker_devices_rejects_empty_value(self) -> None:
        with self.assertRaises(ValueError):
            parse_worker_devices("")


class RestorationTests(unittest.TestCase):
    def test_restoration_plan_detects_model_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "swinir-denoise.onnx").write_bytes(b"model")

            plan = plan_restoration("denoise", root)

        self.assertTrue(plan.enabled)
        self.assertEqual(plan.operation, "denoise")

    @patch("inference.restoration.ONNXFrameUpscaler")
    def test_restoration_processor_delegates_to_onnx(self, upscaler) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "artifact-cleanup.onnx").write_bytes(b"model")
            plan = plan_restoration("artifact", root)

            processor = RestorationProcessor(plan, "cpu")
            processor.process(b"abc", 1, 1)

        upscaler.return_value.upscale.assert_called_once_with(b"abc", 1, 1)


class CheckpointAndRestorationCliTests(unittest.TestCase):
    def test_cli_maps_completion_flags(self) -> None:
        args = build_parser().parse_args(
            [
                "enhance",
                "-i",
                "input.mp4",
                "--checkpoint-dir",
                ".cache/job",
                "--worker-devices",
                "cuda0:CUDAExecutionProvider,cpu:CPUExecutionProvider",
                "--restore",
                "denoise",
                "--restore",
                "artifact",
            ]
        )

        config = config_from_args(args)

        self.assertEqual(config.checkpoint_dir, Path(".cache/job"))
        self.assertEqual(config.worker_devices, ("cuda0", "cpu"))
        self.assertEqual(config.restoration_ops, ("denoise", "artifact"))


if __name__ == "__main__":
    unittest.main()
