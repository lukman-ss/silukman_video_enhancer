"""Tests for execution providers (Vulkan/experimental), LUT filtering, hardware encoders, and model packaging."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from inference.providers import plan_accelerator_provider, plan_experimental_provider
from inference.runtime import select_execution_providers
from models.optimization import plan_distillation, plan_pruning, run_model_optimization
from models.package import create_model_package, import_model_package, read_model_package_manifest
from models.validation import validate_custom_onnx_model
from pipeline.color import lut_filter_arg, parse_cube_lut, plan_hdr_output, tone_map_filter
from pipeline.delivery import delivery_command_args, get_delivery_preset
from pipeline.encoders import probe_hardware_encoders, select_hardware_encoder
from pipeline.tiling import plan_high_resolution_tiling


class ProviderExpansionTests(unittest.TestCase):
    def test_vulkan_provider_plans_fallback(self) -> None:
        plan = plan_experimental_provider("vulkan", ["CPUExecutionProvider"])

        self.assertFalse(plan.available)
        self.assertEqual(plan.providers, ["CPUExecutionProvider"])

    def test_runtime_selection_accepts_webgpu_provider(self) -> None:
        selection = select_execution_providers(
            "webgpu",
            ["WebGPUExecutionProvider", "CPUExecutionProvider"],
        )

        self.assertEqual(selection.providers[0], "WebGPUExecutionProvider")

    def test_openvino_and_qnn_plan_with_fallback(self) -> None:
        openvino = plan_accelerator_provider(
            "openvino",
            ["OpenVINOExecutionProvider", "CPUExecutionProvider"],
        )
        qnn = select_execution_providers(
            "qnn",
            ["QNNExecutionProvider", "CPUExecutionProvider"],
        )

        self.assertTrue(openvino.available)
        self.assertEqual(qnn.providers[0], "QNNExecutionProvider")


class DeliveryPresetTests(unittest.TestCase):
    def test_delivery_presets_emit_codec_arguments(self) -> None:
        av1 = delivery_command_args("av1")
        prores = get_delivery_preset("prores").ffmpeg_args()

        self.assertIn("libsvtav1", av1)
        self.assertIn("prores_ks", prores)


class ColorPipelineTests(unittest.TestCase):
    def test_parse_cube_lut_and_filter_arg(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            lut = Path(temp_dir) / "look.cube"
            lut.write_text(
                "\n".join(
                    [
                        'TITLE "Look"',
                        "LUT_3D_SIZE 2",
                        "0 0 0",
                        "0 0 1",
                        "0 1 0",
                        "0 1 1",
                        "1 0 0",
                        "1 0 1",
                        "1 1 0",
                        "1 1 1",
                    ]
                ),
                encoding="utf-8",
            )

            parsed = parse_cube_lut(lut)
            filter_arg = lut_filter_arg(lut)

            self.assertEqual(parsed.title, "Look")
            self.assertEqual(parsed.size, 2)
            self.assertIn("lut3d", filter_arg)

    def test_hdr_plan_emits_bt2020_10bit_metadata(self) -> None:
        args = plan_hdr_output(hdr=True, transfer="pq").ffmpeg_args()

        self.assertIn("yuv420p10le", args)
        self.assertIn("bt2020", args)
        self.assertIn("smpte2084", args)

    def test_tone_map_presets_emit_filter_chains(self) -> None:
        self.assertIn("tonemap", tone_map_filter("hdr-to-sdr"))
        self.assertEqual(tone_map_filter("hdr-passthrough"), "null")


class ModelValidationTests(unittest.TestCase):
    def test_custom_onnx_metadata_validation_accepts_valid_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            model = root / "custom.onnx"
            metadata = root / "custom.metadata.json"
            model.write_bytes(b"onnx")
            metadata.write_text(
                json.dumps(
                    {
                        "input_shape": [1, 3, 64, 64],
                        "output_shape": [1, 3, 128, 128],
                        "opset": 17,
                        "scale": 2,
                    }
                ),
                encoding="utf-8",
            )

            result = validate_custom_onnx_model(model)

            self.assertTrue(result.valid)
            self.assertEqual(result.metadata.scale, 2)

    def test_custom_onnx_metadata_validation_rejects_bad_shape(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            model = root / "bad.onnx"
            metadata = root / "bad.metadata.json"
            model.write_bytes(b"onnx")
            metadata.write_text(
                json.dumps(
                    {
                        "input_shape": [1, 4, 64, 64],
                        "output_shape": [1, 3, 128, 128],
                        "opset": 10,
                        "scale": 8,
                    }
                ),
                encoding="utf-8",
            )

            result = validate_custom_onnx_model(model)

            self.assertFalse(result.valid)
            self.assertGreaterEqual(len(result.errors), 3)


class ModelOptimizationTests(unittest.TestCase):
    def test_plan_pruning_and_distillation_commands(self) -> None:
        prune = plan_pruning(
            Path("student.onnx"),
            Path("student-pruned.onnx"),
            ["optimizer"],
            target_sparsity=0.4,
        )
        distill = plan_distillation(
            Path("teacher.onnx"),
            Path("student.onnx"),
            Path("student-distilled.onnx"),
            "distiller",
        )

        self.assertEqual(prune.operation, "prune")
        self.assertEqual(prune.target_sparsity, 0.4)
        self.assertEqual(distill.operation, "distill")
        self.assertEqual(distill.teacher_model, Path("teacher.onnx"))

    @mock.patch("models.optimization.subprocess.run")
    def test_run_model_optimization_returns_output_hash(self, run) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "student.onnx"
            output = root / "student-pruned.onnx"
            source.write_bytes(b"student")

            def fake_run(command, capture_output, text):
                output.write_bytes(b"optimized")
                return mock.Mock(returncode=0, stderr="")

            run.side_effect = fake_run
            plan = plan_pruning(source, output, ["optimizer"])
            result = run_model_optimization(plan)

            self.assertEqual(result.output_model, output)
            self.assertIn("--target-sparsity", result.command)
            self.assertEqual(len(result.sha256), 64)


class EncoderAndTilingTests(unittest.TestCase):
    def test_hardware_encoder_probe_and_selection(self) -> None:
        profiles = probe_hardware_encoders(" V..... h264_nvenc\n V..... h264_qsv")
        selected = select_hardware_encoder(profiles, system="Linux")

        self.assertEqual(selected.name, "nvenc")
        self.assertTrue(any(profile.name == "qsv" and profile.available for profile in profiles))

    def test_high_resolution_tiling_plans_multiple_tiles(self) -> None:
        plan = plan_high_resolution_tiling(7680, 4320, memory_budget_mb=64)

        self.assertGreater(len(plan.tiles), 1)
        self.assertLessEqual(plan.estimated_tile_memory_mb, 70)


class ModelPackageTests(unittest.TestCase):
    def test_model_package_create_and_import(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            model = root / "model.onnx"
            metadata = root / "model.metadata.json"
            package = root / "package"
            cache = root / "cache"
            model.write_bytes(b"model")
            metadata.write_text("{}", encoding="utf-8")

            manifest = create_model_package("custom", "1.0.0", model, package, metadata)
            imported = import_model_package(package, root=cache, minimum_version="1.0.0")
            read_back = read_model_package_manifest(package)

            self.assertEqual(manifest.name, "custom")
            self.assertEqual(read_back.sha256, manifest.sha256)
            self.assertTrue(imported.exists())


if __name__ == "__main__":
    unittest.main()
