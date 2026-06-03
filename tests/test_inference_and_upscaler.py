"""Tests for ONNX runtime provider selection and frame upscaler configuration."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from app.config import EnhancementConfig
from inference.runtime import select_execution_providers
from models.registry import verify_model_file
from pipeline.upscaler import build_upscaler


class ProviderSelectionTests(unittest.TestCase):
    def test_auto_prefers_accelerated_provider_before_cpu(self) -> None:
        selection = select_execution_providers(
            "auto",
            ["CPUExecutionProvider", "CUDAExecutionProvider"],
        )

        self.assertEqual(
            selection.providers,
            ["CUDAExecutionProvider", "CPUExecutionProvider"],
        )

    def test_requested_cpu_uses_cpu_provider(self) -> None:
        selection = select_execution_providers(
            "cpu",
            ["CPUExecutionProvider", "CUDAExecutionProvider"],
        )

        self.assertEqual(selection.providers, ["CPUExecutionProvider"])


class ModelRegistryTests(unittest.TestCase):
    def test_sha256_verification_passes_for_matching_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            model_path = Path(temp_dir) / "model.onnx"
            model_path.write_bytes(b"model")

            self.assertTrue(
                verify_model_file(
                    model_path,
                    "9372c470eeadd5ecd9c3c74c2b3cb633f8e2f2fad799250a0f70d652b6b825e4",
                )
            )


class UpscalerSelectionTests(unittest.TestCase):
    def test_missing_model_uses_ffmpeg_baseline_scaler(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict("os.environ", {"SILUKMAN_MODEL_DIR": temp_dir}):
                upscaler = build_upscaler(
                    EnhancementConfig(
                        input_path=Path("in.mp4"),
                        output_path=Path("out.mp4"),
                        scale=2,
                    ),
                    width=320,
                    height=180,
                )

        self.assertEqual(upscaler.label, "FFmpeg Lanczos baseline")
        self.assertTrue(upscaler.uses_ffmpeg_scale)
        self.assertEqual((upscaler.output_width, upscaler.output_height), (640, 360))

    @patch("pipeline.upscaler.ONNXFrameUpscaler")
    def test_existing_model_uses_onnx_upscaler(self, onnx_upscaler: Mock) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            Path(temp_dir, "realesrgan-x2.onnx").write_bytes(b"model")
            with patch.dict("os.environ", {"SILUKMAN_MODEL_DIR": temp_dir}):
                upscaler = build_upscaler(
                    EnhancementConfig(
                        input_path=Path("in.mp4"),
                        output_path=Path("out.mp4"),
                        scale=2,
                    ),
                    width=320,
                    height=180,
                )

        self.assertEqual(upscaler.label, "ONNX realesrgan")
        self.assertFalse(upscaler.uses_ffmpeg_scale)
        onnx_upscaler.assert_called_once()


if __name__ == "__main__":
    unittest.main()
