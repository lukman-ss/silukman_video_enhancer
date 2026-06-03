"""Tests for HTML comparison reports, web UI dashboard, scene interpolation, power throttling, and render farm distribution."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app.notifications import Notification, notification_command
from app.report import ReportMetadata, ReportMetric, render_comparison_report, write_comparison_report
from app.webui import DashboardState, WebUIConfig, dashboard_status
from inference.scene_selection import classify_scene, select_model_for_scene
from models.encryption import decrypt_bytes, encrypt_bytes
from pipeline.artifacts import detect_artifact
from pipeline.interpolation import plan_interpolation, run_interpolation
from pipeline.power import BatteryState, ThermalState, should_pause_for_battery, throttle_delay_seconds
from pipeline.render_farm import RenderFarmCoordinator, RenderNode, shard_frames
from pipeline.subtitles import SubtitleCue, build_subtitle_job, write_srt
from tools.pyinstaller_spec import platform_installer_command, pyinstaller_command
from ui.comparator import ComparatorState


class ReportAndComparatorTests(unittest.TestCase):
    def test_render_and_write_html_report(self) -> None:
        html = render_comparison_report(
            "Report",
            Path("original.mp4"),
            Path("enhanced.mp4"),
            [ReportMetric("VMAF", "95")],
        )

        self.assertIn("<video", html)
        self.assertIn("VMAF", html)
        self.assertIn('type="range"', html)

        with tempfile.TemporaryDirectory() as temp_dir:
            output = write_comparison_report(
                Path(temp_dir) / "report.html",
                "Report",
                Path("original.mp4"),
                Path("enhanced.mp4"),
                [],
            )
            self.assertTrue(output.exists())

    def test_report_includes_execution_metadata(self) -> None:
        html = render_comparison_report(
            "Report",
            Path("original.mp4"),
            Path("enhanced.mp4"),
            [],
            metadata=ReportMetadata(fps=24.5, hardware_provider="CPUExecutionProvider"),
        )

        self.assertIn("FPS", html)
        self.assertIn("CPUExecutionProvider", html)

    def test_comparator_state_normalizes_split_and_labels(self) -> None:
        state = ComparatorState(Path("a.mp4"), Path("b.mp4"), split_position=2)

        self.assertEqual(state.normalized_split(), 1.0)
        self.assertEqual(state.label(), "a.mp4 vs b.mp4")


class WebAndRenderFarmTests(unittest.TestCase):
    def test_webui_status_exposes_local_url(self) -> None:
        status = dashboard_status(WebUIConfig(port=9000))

        self.assertEqual(status["url"], "http://127.0.0.1:9000")

    def test_dashboard_state_tracks_progress_payload(self) -> None:
        state = DashboardState()

        state.update(status="running", progress=42, message="streaming")

        self.assertEqual(state.snapshot()["progress"], 42)
        self.assertEqual(state.snapshot()["message"], "streaming")

    def test_render_farm_shards_frames_across_nodes(self) -> None:
        shards = shard_frames(
            10,
            [RenderNode("a", "127.0.0.1", 8001), RenderNode("b", "127.0.0.2", 8001)],
        )

        self.assertEqual(len(shards), 2)
        self.assertEqual(shards[0].start_frame, 0)
        self.assertEqual(shards[-1].end_frame, 10)

    def test_render_farm_coordinator_dispatches_shards(self) -> None:
        class FakeResponse:
            status = 200
            reason = "OK"

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def read(self):
                return b"done"

        with mock.patch("pipeline.render_farm.request.urlopen", return_value=FakeResponse()):
            results = RenderFarmCoordinator([RenderNode("a", "127.0.0.1", 8001)]).dispatch(
                4,
                {"input": "in.mp4"},
            )

        self.assertTrue(results[0].success)
        self.assertEqual(results[0].message, "done")


class ProtectionAndGovernorsTests(unittest.TestCase):
    def test_model_encryption_round_trips(self) -> None:
        encrypted = encrypt_bytes(b"model", "secret")

        self.assertNotEqual(encrypted, b"model")
        self.assertEqual(decrypt_bytes(encrypted, "secret"), b"model")

    def test_power_and_thermal_governors(self) -> None:
        self.assertTrue(should_pause_for_battery(BatteryState(percent=10, plugged_in=False)))
        self.assertFalse(should_pause_for_battery(BatteryState(percent=10, plugged_in=True)))
        self.assertGreater(throttle_delay_seconds(ThermalState(temperature_c=90)), 0)


class SubtitleArtifactNotificationTests(unittest.TestCase):
    def test_subtitle_job_and_artifact_detector(self) -> None:
        job = build_subtitle_job(Path("in.mp4"), Path("out.srt"), target_language="id")
        artifact = detect_artifact(bytes([0] * 12))

        self.assertEqual(job.target_language, "id")
        self.assertTrue(artifact.black_frame)

    def test_write_srt_outputs_timestamped_cues(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = write_srt(
                Path(temp_dir) / "out.srt",
                [SubtitleCue(1, 0, 2.5, "Halo")],
            )

            self.assertIn("00:00:02,500", output.read_text(encoding="utf-8"))

    def test_notification_command_for_linux(self) -> None:
        command = notification_command(Notification("Done", "Render complete"), system="Linux")

        self.assertEqual(command, ["notify-send", "Done", "Render complete"])


class SceneInterpolationPackagingTests(unittest.TestCase):
    def test_scene_model_selection_and_interpolation(self) -> None:
        scene = classify_scene(brightness=0.1, motion=0.1)
        plan = plan_interpolation(24, 60)

        self.assertEqual(select_model_for_scene(scene), "swinir")
        self.assertEqual(plan.model_name, "rife")
        self.assertGreaterEqual(plan.factor, 2)

    def test_interpolation_can_use_rife_runner(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "out.mp4"

            def fake_rife(_input: Path, output_path: Path, _plan):
                output_path.write_bytes(b"video")
                return output_path

            result = run_interpolation(
                Path("in.mp4"),
                output,
                plan_interpolation(24, 48),
                rife_runner=fake_rife,
            )

            self.assertEqual(result, output)
            self.assertEqual(output.read_bytes(), b"video")

    def test_pyinstaller_command_targets_onefile_build(self) -> None:
        command = pyinstaller_command()

        self.assertIn("--onefile", command)
        self.assertIn("app/cli.py", command)

    def test_platform_installer_command_targets_native_package(self) -> None:
        command = platform_installer_command(Path("dist/app"), platform="linux")

        self.assertIn("dpkg-deb", command)
        self.assertIn("silukman-video-enhancer.deb", command)


if __name__ == "__main__":
    unittest.main()
