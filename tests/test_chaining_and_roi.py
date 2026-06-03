"""Tests for model chaining, region of interest (ROI) extraction, and quantization configurations."""

from __future__ import annotations

import unittest
from pathlib import Path

from app.cli import build_parser, config_from_args
from inference.quantization import plan_fp16_quantization
from pipeline.chaining import ModelChain, ModelChainStep, parse_model_chain
from pipeline.destinations import parse_destination
from pipeline.roi import extract_roi_rgb, parse_roi, paste_roi_rgb


class ModelChainingTests(unittest.TestCase):
    def test_model_chain_applies_processors_in_order(self) -> None:
        chain = ModelChain(
            [
                ModelChainStep("first", lambda frame: frame + b"a"),
                ModelChainStep("second", lambda frame: frame + b"b"),
            ]
        )

        self.assertEqual(chain.process(b""), b"ab")
        self.assertEqual(chain.names, ["first", "second"])

    def test_parse_model_chain_ignores_empty_parts(self) -> None:
        self.assertEqual(parse_model_chain("denoise, realesrgan, "), ["denoise", "realesrgan"])


class ROITests(unittest.TestCase):
    def test_extract_and_paste_roi_rgb(self) -> None:
        frame = bytes(range(27))
        roi = parse_roi("1,1,2,2")

        extracted = extract_roi_rgb(frame, 3, 3, roi)
        pasted = paste_roi_rgb(frame, 3, 3, roi, bytes([255] * len(extracted)))

        self.assertEqual(len(extracted), 2 * 2 * 3)
        self.assertNotEqual(pasted, frame)
        self.assertEqual(pasted[12:18], bytes([255] * 6))

    def test_roi_rejects_out_of_bounds(self) -> None:
        roi = parse_roi("2,2,2,2")

        with self.assertRaises(ValueError):
            roi.validate(3, 3)


class QuantizationTests(unittest.TestCase):
    def test_fp16_enabled_for_capable_provider(self) -> None:
        plan = plan_fp16_quantization(True, ["CUDAExecutionProvider"])

        self.assertTrue(plan.enabled)
        self.assertEqual(plan.precision, "fp16")

    def test_fp16_falls_back_for_cpu(self) -> None:
        plan = plan_fp16_quantization(True, ["CPUExecutionProvider"])

        self.assertFalse(plan.enabled)
        self.assertEqual(plan.precision, "fp32")


class DestinationTests(unittest.TestCase):
    def test_parse_destination_with_time_range_and_copy(self) -> None:
        destination = parse_destination("clip.mp4,1.5,4.0,copy")

        self.assertEqual(destination.path, Path("clip.mp4"))
        self.assertEqual(destination.start_seconds, 1.5)
        self.assertEqual(destination.end_seconds, 4.0)
        self.assertTrue(destination.stream_copy)

    def test_parse_destination_rejects_invalid_range(self) -> None:
        with self.assertRaises(ValueError):
            parse_destination("clip.mp4,4,1")


class ChainingAndRoiCliTests(unittest.TestCase):
    def test_cli_maps_phase2_flags(self) -> None:
        args = build_parser().parse_args(
            [
                "enhance",
                "-i",
                "input.mp4",
                "--chain",
                "denoise,realesrgan",
                "--roi",
                "0,0,16,16",
                "--fp16",
                "--destination",
                "clip.mp4,0,5,copy",
            ]
        )

        config = config_from_args(args)

        self.assertEqual(config.model_chain, ("denoise", "realesrgan"))
        self.assertEqual(config.roi, (0, 0, 16, 16))
        self.assertTrue(config.fp16)
        self.assertEqual(config.destinations, ("clip.mp4,0,5,copy",))


if __name__ == "__main__":
    unittest.main()
