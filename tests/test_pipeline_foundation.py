"""Tests for temporal analysis, ONNX model discovery, batch processing configs, and resource limits tiling planning."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.batch import build_batch_configs, discover_video_inputs
from app.cli import build_parser, config_from_args
from app.config import EnhancementConfig
from models.discovery import build_runtime_registry, discover_onnx_models
from pipeline.resources import ResourceLimits, choose_tiling_plan
from pipeline.temporal import TemporalAnalyzer, ssim_like_similarity


class TemporalAnalyzerTests(unittest.TestCase):
    def test_detects_near_duplicate_frame_skip(self) -> None:
        analyzer = TemporalAnalyzer(1, 1, skip_similarity_threshold=0.99)
        analyzer.analyze(bytes([10, 10, 10]))

        decision = analyzer.analyze(bytes([10, 10, 10]))

        self.assertFalse(decision.scene_cut)
        self.assertTrue(decision.skip_frame)

    def test_detects_scene_cut_from_large_delta(self) -> None:
        analyzer = TemporalAnalyzer(1, 1, scene_cut_threshold=0.5)
        analyzer.analyze(bytes([0, 0, 0]))

        decision = analyzer.analyze(bytes([255, 255, 255]))

        self.assertTrue(decision.scene_cut)
        self.assertFalse(decision.skip_frame)

    def test_similarity_score_uses_byte_delta(self) -> None:
        self.assertEqual(ssim_like_similarity(bytes([1, 1]), bytes([1, 1])), 1.0)
        self.assertLess(ssim_like_similarity(bytes([0]), bytes([255])), 0.01)


class ModelDiscoveryTests(unittest.TestCase):
    def test_discovers_registered_and_community_onnx_models(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "realesrgan-x2.onnx").write_bytes(b"registered")
            (root / "community-model.onnx").write_bytes(b"community")

            discovered = discover_onnx_models(root)
            registry = build_runtime_registry(root)

        self.assertEqual([model.name for model in discovered], ["community-model", "realesrgan"])
        self.assertIn("community-model", registry)


class BatchCliTests(unittest.TestCase):
    def test_discovers_video_inputs_and_builds_output_configs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "a.mp4").write_bytes(b"")
            (root / "b.txt").write_bytes(b"")
            output = root / "out"

            configs = build_batch_configs(
                EnhancementConfig(input_path=root, output_path=output),
                output,
            )

        self.assertEqual(len(configs), 1)
        self.assertEqual(configs[0].output_path.name, "a_enhanced.mp4")

    def test_cli_maps_batch_flag(self) -> None:
        args = build_parser().parse_args(["enhance", "-i", "videos", "-o", "out", "--batch"])

        config = config_from_args(args)

        self.assertTrue(config.batch)

    def test_discover_video_inputs_rejects_missing_folder(self) -> None:
        with self.assertRaises(ValueError):
            discover_video_inputs(Path("missing-folder"))


class ResourcePlanningTests(unittest.TestCase):
    def test_chooses_smaller_tiles_for_tight_budget(self) -> None:
        plan = choose_tiling_plan(
            3840,
            2160,
            ResourceLimits(ram_bytes=512 * 1024 * 1024, vram_bytes=64 * 1024 * 1024),
        )

        self.assertEqual(plan.tile_size, 256)

    def test_chooses_large_tiles_when_budget_allows(self) -> None:
        plan = choose_tiling_plan(
            1280,
            720,
            ResourceLimits(ram_bytes=16 * 1024 * 1024 * 1024),
        )

        self.assertEqual(plan.tile_size, 1024)


if __name__ == "__main__":
    unittest.main()
