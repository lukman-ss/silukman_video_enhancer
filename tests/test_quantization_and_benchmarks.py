"""Tests for INT8 quantization, dataset benchmarking, job queues, preset import/export, and render protocols."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app.config import EnhancementConfig
from app.jobs import JobQueue
from app.presets import export_encrypted_preset, import_encrypted_preset, sync_encrypted_preset
from app.report import ReportMetric
from app.cli import build_parser, config_from_args
from inference.quantization import plan_int8_quantization, quantize_onnx_int8
from inference.dataset_benchmark import (
    BenchmarkPair,
    discover_benchmark_pairs,
    run_dataset_benchmark,
    write_benchmark_summary,
)
from models.setup import import_offline_model, inspect_model_setup
from pipeline.artifacts import ArtifactReport
from pipeline.render_farm import (
    RenderNode,
    RenderFarmCoordinator,
    merge_shard_outputs,
    plan_distributed_transcode,
)
from pipeline.render_node import RenderNodeCapabilities, RenderNodeState
from pipeline.runner import run_enhancement
from pipeline.subtitles import build_local_ocr_engine, build_local_translator
from utils.ffmpeg import VideoInfo
from tools.qa_smoke import run_packaged_cli_smoke, summarize_smoke_results
from tools.release import build_release_pipeline, write_release_script
from ui.comparator import (
    ComparatorState,
    PreviewPair,
    PreviewRequest,
    plan_timeline_preview_requests,
    render_timeline_preview,
)


class ModelSetupTests(unittest.TestCase):
    def test_import_offline_model_copies_and_records_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "custom.onnx"
            source.write_bytes(b"model")
            cache = root / "cache"

            imported = import_offline_model(source, name="custom", root=cache)
            status = inspect_model_setup(cache)

            self.assertTrue(imported.path.exists())
            self.assertTrue((cache / "imported_models.json").exists())
            self.assertIn("custom", [model.name for model in status.imported_models])


class BenchmarkDatasetTests(unittest.TestCase):
    def test_discover_and_run_dataset_benchmark(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "original").mkdir()
            (root / "enhanced").mkdir()
            (root / "original" / "clip.mp4").write_bytes(b"original")
            (root / "enhanced" / "clip.mp4").write_bytes(b"enhanced")

            pairs = discover_benchmark_pairs(root)
            summary = run_dataset_benchmark(
                pairs,
                metric_collector=lambda _a, _b: [ReportMetric("VMAF", "95")],
                artifact_collector=lambda _path: ArtifactReport(False, False, 0.1),
                baselines={"clip": {"VMAF": 90}},
            )
            output = write_benchmark_summary(summary, root / "summary.json")

            self.assertEqual(len(pairs), 1)
            self.assertTrue(summary.passed)
            self.assertTrue(output.exists())

    def test_dataset_benchmark_flags_baseline_regression(self) -> None:
        pair = BenchmarkPair("clip", Path("a.mp4"), Path("b.mp4"))

        summary = run_dataset_benchmark(
            [pair],
            metric_collector=lambda _a, _b: [ReportMetric("VMAF", "80")],
            artifact_collector=lambda _path: ArtifactReport(False, False, 0.1),
            baselines={"clip": {"VMAF": 90}},
        )

        self.assertFalse(summary.passed)
        self.assertIn("below baseline", summary.cases[0].failure_reason)


class JobQueueTests(unittest.TestCase):
    def test_job_queue_tracks_submit_update_cancel(self) -> None:
        queue = JobQueue()
        config = EnhancementConfig(Path("in.mp4"), Path("out.mp4"))

        job = queue.submit(config)
        running = queue.update(job.id, status="running", progress=50, message="encoding")
        cancelled = queue.cancel(job.id)

        self.assertEqual(queue.next_queued(), None)
        self.assertEqual(running.progress, 50)
        self.assertEqual(cancelled.status, "cancelled")
        self.assertEqual(queue.list()[0].id, job.id)

    @mock.patch("app.jobs.send_notification", return_value=True)
    def test_job_queue_pause_resume_and_notifications(self, notify) -> None:
        queue = JobQueue()
        job = queue.submit(EnhancementConfig(Path("in.mp4"), Path("out.mp4")))

        paused = queue.pause(job.id)
        resumed = queue.resume(job.id)
        completed = queue.complete(job.id)

        self.assertEqual(paused.status, "paused")
        self.assertEqual(resumed.status, "queued")
        self.assertEqual(completed.status, "completed")
        notify.assert_called_once()


class RenderNodeProtocolTests(unittest.TestCase):
    def test_render_node_state_exposes_protocol_operations(self) -> None:
        state = RenderNodeState(
            RenderNodeCapabilities(
                name="node-a",
                providers=("CPUExecutionProvider",),
                max_workers=2,
            )
        )

        job = state.submit({"job_id": "render-1", "start_frame": 0, "end_frame": 10})
        cancelled = state.cancel(job.id)

        self.assertEqual(state.health()["status"], "ready")
        self.assertEqual(job.status, "queued")
        self.assertEqual(cancelled.status, "cancelled")
        self.assertEqual(state.result(job.id).status, "cancelled")

    def test_render_farm_retries_failed_shards(self) -> None:
        coordinator = RenderFarmCoordinator([RenderNode("a", "127.0.0.1", 8001)])
        calls = []

        def fake_dispatch(shard, payload):
            calls.append(payload)
            return mock.Mock(shard=shard, success=len(calls) > 1, message="ok")

        coordinator._dispatch_shard = fake_dispatch

        results = coordinator.dispatch_with_retries(4, {"input": "in.mp4"}, max_retries=1)

        self.assertTrue(results[0].success)
        self.assertEqual(len(calls), 2)

    @mock.patch("pipeline.render_farm.require_binary", return_value="ffmpeg")
    @mock.patch("pipeline.render_farm.subprocess.run")
    def test_merge_shard_outputs_uses_concat(self, run, _ffmpeg) -> None:
        run.return_value.returncode = 0
        run.return_value.stderr = ""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output = merge_shard_outputs([root / "a.mp4", root / "b.mp4"], root / "out.mp4")

        self.assertEqual(output.name, "out.mp4")
        self.assertIn("concat", run.call_args.args[0])

    def test_distributed_transcode_plan_round_robins_segments(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            nodes = [RenderNode("a", "127.0.0.1", 8001), RenderNode("b", "127.0.0.2", 8001)]
            plan = plan_distributed_transcode(10, 4, nodes, Path(temp_dir))

            self.assertEqual(len(plan.segments), 3)
            self.assertEqual(plan.segments[1].node.name, "b")
            self.assertEqual(plan.merge_mode, "stream-copy")


class PackagedSmokeTests(unittest.TestCase):
    def test_packaged_cli_smoke_runs_help_command(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            executable = Path(temp_dir) / "app"
            executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")

            with mock.patch("tools.qa_smoke.subprocess.run") as run:
                run.return_value.returncode = 0
                run.return_value.stdout = "help"
                run.return_value.stderr = ""
                results = run_packaged_cli_smoke(executable)

            self.assertTrue(summarize_smoke_results(results))
            self.assertEqual(results[0].name, "help")

    def test_release_pipeline_writes_build_script(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            plan = build_release_pipeline("linux", root / "bundle", ffmpeg_binary=root / "ffmpeg")
            script = write_release_script(plan, root / "release.sh")

            self.assertIn("pyinstaller", script.read_text(encoding="utf-8"))
            self.assertIn("dpkg-deb", plan.installer_command)


class RunnerInterpolationTests(unittest.TestCase):
    def test_cli_maps_target_fps(self) -> None:
        args = build_parser().parse_args(["enhance", "-i", "input.mp4", "--target-fps", "60"])

        self.assertEqual(config_from_args(args).target_fps, 60)

    @mock.patch("pipeline.runner.run_interpolation")
    @mock.patch("pipeline.runner._stream_frames")
    @mock.patch("pipeline.runner.calibrate_bitrate_from_scan", return_value=mock.Mock(crf=18, maxrate_kbps=None, bufsize_kbps=None))
    @mock.patch("pipeline.runner.scan_spatial_complexity", return_value=0.5)
    @mock.patch("pipeline.runner.build_upscaler")
    @mock.patch("pipeline.runner.probe_video")
    def test_runner_applies_interpolation_output_stage(
        self,
        probe,
        build_upscaler,
        _scan,
        _bitrate,
        _stream,
        interpolate,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_path = root / "in.mp4"
            output_path = root / "out.mp4"
            input_path.write_bytes(b"in")
            output_path.write_bytes(b"out")
            probe.return_value = VideoInfo(width=1, height=1, fps=24, frame_count=1, has_audio=False)
            build_upscaler.return_value = mock.Mock(
                label="mock",
                padding=mock.Mock(needs_padding=False),
            )

            def fake_stream(*_args, **_kwargs):
                output_path.write_bytes(b"enhanced")

            def fake_interpolate(_input, interpolated, _plan):
                interpolated.write_bytes(b"interpolated")
                return interpolated

            _stream.side_effect = fake_stream
            interpolate.side_effect = fake_interpolate

            run_enhancement(
                EnhancementConfig(
                    input_path=input_path,
                    output_path=output_path,
                    target_fps=60,
                )
            )

            self.assertEqual(output_path.read_bytes(), b"interpolated")
            interpolate.assert_called_once()


class PresetSyncTests(unittest.TestCase):
    def test_encrypted_preset_round_trips_and_syncs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config = EnhancementConfig(
                input_path=Path("in.mp4"),
                output_path=Path("out.mp4"),
                target_fps=60,
            )
            preset = export_encrypted_preset(config, root / "preset.enc", "secret")
            synced = sync_encrypted_preset(preset, root / "sync")
            restored = import_encrypted_preset(synced, "secret")

            self.assertNotIn("in.mp4", preset.read_text(encoding="latin1"))
            self.assertEqual(restored.input_path, Path("in.mp4"))
            self.assertEqual(restored.target_fps, 60)


class SubtitleEngineTests(unittest.TestCase):
    @mock.patch("pipeline.subtitles.subprocess.run")
    def test_local_ocr_and_translator_adapters_call_commands(self, run) -> None:
        run.return_value.returncode = 0
        run.return_value.stdout = "Halo\n"
        run.return_value.stderr = ""

        text = build_local_ocr_engine(["ocr-bin"])(Path("frame.png"))
        translated = build_local_translator(["translate-bin"])("Halo", "id", "en")

        self.assertEqual(text, "Halo")
        self.assertEqual(translated, "Halo")
        self.assertEqual(run.call_count, 2)


class QuantizationTests(unittest.TestCase):
    def test_int8_quantization_plan_prefers_cpu_provider(self) -> None:
        plan = plan_int8_quantization(True, ["CPUExecutionProvider"])

        self.assertTrue(plan.enabled)
        self.assertEqual(plan.precision, "int8")

    @mock.patch("inference.quantization._quant_type_qint8", return_value="QInt8")
    @mock.patch("inference.quantization._import_quantize_dynamic")
    def test_quantize_onnx_int8_delegates_to_onnxruntime(self, importer, _quant_type) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            model = root / "model.onnx"
            output = root / "model-int8.onnx"
            model.write_bytes(b"model")
            quantize = mock.Mock()
            importer.return_value = quantize

            result = quantize_onnx_int8(model, output)

            self.assertEqual(result, output)
            quantize.assert_called_once()


class TimelinePreviewTests(unittest.TestCase):
    def test_timeline_preview_requests_are_evenly_spaced(self) -> None:
        requests = plan_timeline_preview_requests(10, 3)

        self.assertEqual([request.timestamp_seconds for request in requests], [0, 5, 10])

    @mock.patch("ui.comparator.render_sampled_preview")
    def test_render_timeline_preview_uses_sampled_preview(self, sampled) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            sampled.return_value = PreviewPair(Path("orig.png"), Path("enh.png"))
            frames = render_timeline_preview(
                ComparatorState(Path("a.mp4"), Path("b.mp4")),
                [PreviewRequest(0), PreviewRequest(1)],
                Path(temp_dir),
            )

            self.assertEqual(len(frames), 2)
            self.assertEqual(sampled.call_count, 2)


if __name__ == "__main__":
    unittest.main()
