"""Tests for FFmpeg command building, video probing, progress monitoring, and pipeline runner integration."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from app.config import EnhancementConfig
from pipeline.telemetry_collector import TelemetryCollector
from pipeline.runner import run_enhancement
from utils.ffmpeg import probe_video, reader_command, writer_command
from app.progress import CliProgressMonitor


class FFmpegCommandTests(unittest.TestCase):
    @patch("utils.ffmpeg.shutil.which", return_value="/usr/bin/ffmpeg")
    def test_reader_command_streams_rgb_frames_to_stdout(self, _which: Mock) -> None:
        command = reader_command(Path("input.mp4"))

        self.assertIn("-f", command)
        self.assertIn("rawvideo", command)
        self.assertIn("rgb24", command)
        self.assertEqual(command[-1], "-")

    @patch("utils.ffmpeg.shutil.which", return_value="/usr/bin/ffmpeg")
    def test_writer_command_accepts_raw_frames_and_scales_output(self, _which: Mock) -> None:
        command = writer_command(Path("out.mp4"), 320, 180, 640, 360, 30.0, 18)

        self.assertIn("-s:v", command)
        self.assertIn("320x180", command)
        self.assertIn("-vf", command)
        self.assertIn("scale=640:360:flags=lanczos", command)
        self.assertEqual(command[-1], "out.mp4")

    @patch("utils.ffmpeg.shutil.which", return_value="/usr/bin/ffmpeg")
    def test_writer_command_streams_audio_and_metadata_inputs(self, _which: Mock) -> None:
        command = writer_command(
            Path("out.mp4"),
            320,
            180,
            320,
            180,
            30.0,
            18,
            audio_input_path=Path("input.mp4"),
            metadata_input_path=Path("input.mp4"),
        )

        self.assertIn("-c:v", command)
        self.assertIn("libx264", command)
        self.assertIn("-c:a", command)
        self.assertIn("1:a:0?", command)
        self.assertIn("-map_metadata", command)


class ProbeTests(unittest.TestCase):
    @patch("utils.ffmpeg.shutil.which", return_value="/usr/bin/ffprobe")
    @patch("utils.ffmpeg.subprocess.run")
    def test_probe_video_reads_dimensions_fps_frames_and_audio(
        self, run: Mock, _which: Mock
    ) -> None:
        run.return_value = Mock(
            stdout=json.dumps(
                {
                    "streams": [
                        {
                            "codec_type": "video",
                            "width": 1280,
                            "height": 720,
                            "avg_frame_rate": "30000/1001",
                            "nb_frames": "42",
                        },
                        {"codec_type": "audio"},
                    ]
                }
            )
        )

        info = probe_video(Path("input.mp4"))

        self.assertEqual(info.width, 1280)
        self.assertEqual(info.height, 720)
        self.assertAlmostEqual(info.fps, 29.970, places=2)
        self.assertEqual(info.frame_count, 42)
        self.assertTrue(info.has_audio)


class ProgressTests(unittest.TestCase):
    def test_cli_progress_monitor_renders_from_queue(self) -> None:
        stream = io.StringIO()

        with CliProgressMonitor(stream=stream, interval=0.001) as progress:
            progress.update(1, 4, "streaming frames")
            progress.update(4, 4, "completed")

        output = stream.getvalue()
        self.assertIn("streaming frames", output)
        self.assertIn("completed", output)


class RunnerIntegrationTests(unittest.TestCase):
    @patch("pipeline.runner._stream_frames")
    @patch("pipeline.runner.scan_spatial_complexity", return_value=1.0)
    @patch("pipeline.runner.probe_video")
    def test_run_enhancement_streams_audio_directly_to_writer(
        self, probe: Mock, _scan: Mock, stream_frames: Mock
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "input.mp4"
            output_path = Path(temp_dir) / "out.mp4"
            input_path.write_bytes(b"fake")
            probe.return_value = Mock(
                width=320,
                height=180,
                fps=30.0,
                frame_count=10,
                has_audio=True,
            )
            events = []

            result = run_enhancement(
                EnhancementConfig(
                    input_path=input_path,
                    output_path=output_path,
                    scale=1,
                ),
                lambda current, total, message: events.append(
                    (current, total, message)
                ),
            )

        self.assertEqual(result, output_path)
        stream_frames.assert_called_once()
        self.assertEqual(stream_frames.call_args.kwargs["audio_source"], input_path)
        self.assertEqual(stream_frames.call_args.kwargs["metadata_source"], input_path)
        self.assertIn((10, 10, "completed"), events)

    @patch("pipeline.runner._stream_frames")
    @patch("pipeline.runner.scan_spatial_complexity", return_value=1.0)
    @patch("pipeline.runner.probe_video")
    def test_run_enhancement_records_runtime_telemetry(
        self, probe: Mock, _scan: Mock, stream_frames: Mock
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_path = root / "input.mp4"
            output_path = root / "out.mp4"
            input_path.write_bytes(b"fake")

            def fake_stream(*_args, **_kwargs):
                output_path.write_bytes(b"enhanced")

            stream_frames.side_effect = fake_stream
            probe.return_value = Mock(
                width=320,
                height=180,
                fps=30.0,
                frame_count=10,
                has_audio=False,
            )
            telemetry = TelemetryCollector(root / "telemetry.ndjson")

            run_enhancement(
                EnhancementConfig(input_path=input_path, output_path=output_path, scale=1),
                telemetry=telemetry,
            )

            entries = telemetry.all_entries()
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0].job_id, "render:out.mp4")
            self.assertGreater(entries[0].fps, 0)


if __name__ == "__main__":
    unittest.main()
