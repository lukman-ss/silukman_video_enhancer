"""Tests for ONNX-based face restoration using GFPGAN and face parsing."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.cli import build_parser, config_from_args
from inference.face_restoration import FaceRestorer, plan_face_restoration
from pipeline.async_processing import AsyncFrameProcessor, DoubleBuffer
from pipeline.spatiotemporal import choose_spatiotemporal_scale
from pipeline.temporal import TemporalDecision


class FaceRestorationTests(unittest.TestCase):
    def test_face_restoration_plan_detects_model_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "gfpgan.onnx").write_bytes(b"model")

            plan = plan_face_restoration("gfpgan", root)

        self.assertTrue(plan.enabled)
        self.assertEqual(plan.model_name, "gfpgan")

    @patch("inference.face_restoration.ONNXFrameUpscaler")
    def test_face_restorer_delegates_to_onnx_runtime(self, upscaler) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "codeformer.onnx").write_bytes(b"model")
            plan = plan_face_restoration("codeformer", root)

            restorer = FaceRestorer(plan, "cpu")
            restorer.restore(b"abc", 1, 1)

        upscaler.return_value.upscale.assert_called_once_with(b"abc", 1, 1)


class SpatialTemporalScalingTests(unittest.TestCase):
    def test_dynamic_scale_reduces_high_motion(self) -> None:
        plan = choose_spatiotemporal_scale(
            4,
            TemporalDecision(scene_cut=False, skip_frame=False, similarity=0.5),
            motion_score=0.9,
        )

        self.assertEqual(plan.scale, 2)
        self.assertEqual(plan.reason, "high motion")

    def test_dynamic_scale_uses_one_for_duplicate_frame(self) -> None:
        plan = choose_spatiotemporal_scale(
            2,
            TemporalDecision(scene_cut=False, skip_frame=True, similarity=0.999),
            motion_score=0.0,
        )

        self.assertEqual(plan.scale, 1)


class AsyncProcessingTests(unittest.TestCase):
    def test_async_processor_preserves_frame_order(self) -> None:
        processor = AsyncFrameProcessor(lambda frame: frame.upper(), max_workers=2)

        processed = processor.process([b"a", b"b", b"c"])

        self.assertEqual([item.index for item in processed], [0, 1, 2])
        self.assertEqual([item.frame for item in processed], [b"A", b"B", b"C"])

    def test_double_buffer_alternates_slots(self) -> None:
        buffer = DoubleBuffer()

        first = buffer.push(b"first")
        second = buffer.push(b"second")

        self.assertEqual((first, second), (0, 1))
        self.assertEqual(buffer.get(first), b"first")
        self.assertEqual(buffer.get(second), b"second")


class FaceRestorationCliTests(unittest.TestCase):
    def test_cli_maps_task2_flags(self) -> None:
        args = build_parser().parse_args(
            [
                "enhance",
                "-i",
                "input.mp4",
                "--face-model",
                "gfpgan",
                "--dynamic-scale",
                "--async-workers",
                "4",
            ]
        )

        config = config_from_args(args)

        self.assertEqual(config.face_model, "gfpgan")
        self.assertTrue(config.dynamic_scale)
        self.assertEqual(config.async_workers, 4)


if __name__ == "__main__":
    unittest.main()
