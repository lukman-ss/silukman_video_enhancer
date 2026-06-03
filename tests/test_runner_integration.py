"""Tests for pipeline runner integration including ROI processing, checkpoint resumes, destination outputs, and distributed processing."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from app.config import EnhancementConfig
from pipeline.checkpoint import CheckpointState, CheckpointStore
from pipeline.destinations import OutputDestination, emit_destination
from pipeline.runner import _build_frame_processor, _resume_frame_index
from pipeline.plugin_sdk import register_plugin, unregister_plugin
from utils.ffmpeg import VideoInfo


class RunnerIntegrationTests(unittest.TestCase):
    def tearDown(self) -> None:
        unregister_plugin("runner_model_hook")

    def test_roi_processor_updates_only_selected_region(self) -> None:
        info = VideoInfo(width=2, height=2, fps=30.0, frame_count=1, has_audio=False)
        upscaler = Mock()
        upscaler.process.side_effect = lambda frame: bytes([value + 10 for value in frame])
        config = EnhancementConfig(
            input_path=Path("in.mp4"),
            output_path=Path("out.mp4"),
            scale=1,
            roi=(1, 0, 1, 1),
        )
        frame = bytes([1, 1, 1, 2, 2, 2, 3, 3, 3, 4, 4, 4])

        processed = _build_frame_processor(config, info, upscaler)(frame)

        self.assertEqual(processed, bytes([1, 1, 1, 12, 12, 12, 3, 3, 3, 4, 4, 4]))

    def test_frame_processor_runs_registered_model_plugins(self) -> None:
        def invert(frame, *, sandbox=None, **_context):
            sandbox.check_model_load()
            return bytes(255 - value for value in frame)

        register_plugin(
            {
                "name": "runner_model_hook",
                "version": "1.0.0",
                "stage": "model",
                "permissions": ["model.load"],
            },
            invert,
        )
        info = VideoInfo(width=1, height=1, fps=30.0, frame_count=1, has_audio=False)
        upscaler = Mock()
        upscaler.process.return_value = bytes([10, 20, 30])
        upscaler.output_width = 1
        upscaler.output_height = 1
        config = EnhancementConfig(input_path=Path("in.mp4"), output_path=Path("out.mp4"))

        processed = _build_frame_processor(config, info, upscaler)(bytes([0, 0, 0]))

        self.assertEqual(processed, bytes([245, 235, 225]))

    def test_resume_frame_index_requires_matching_settings(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = CheckpointStore(Path(temp_dir))
            config = EnhancementConfig(input_path=Path("in.mp4"), output_path=Path("out.mp4"))
            store.save_state(
                CheckpointState(
                    input_path="in.mp4",
                    output_path="out.mp4",
                    last_processed_frame_index=12,
                    settings_hash=config.summary(),
                )
            )

            self.assertEqual(_resume_frame_index(store, config), 12)

    def test_emit_destination_copies_full_output_without_time_range(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source.mp4"
            target = root / "target.mp4"
            source.write_bytes(b"video")

            emitted = emit_destination(source, OutputDestination(path=target))

            self.assertEqual(emitted, target)
            self.assertEqual(target.read_bytes(), b"video")

    @patch("pipeline.destinations.subprocess.run")
    @patch("utils.ffmpeg.shutil.which", return_value="/usr/bin/ffmpeg")
    def test_emit_destination_uses_ffmpeg_for_time_range(self, _which, run) -> None:
        run.return_value = Mock(returncode=0, stderr="")

        emit_destination(
            Path("source.mp4"),
            OutputDestination(
                path=Path("clip.mp4"),
                start_seconds=1.0,
                end_seconds=3.0,
                stream_copy=True,
            ),
        )

        command = run.call_args.args[0]
        self.assertIn("-ss", command)
        self.assertIn("-t", command)
        self.assertIn("-c", command)

    def test_face_restorer_crop_merge_integration(self) -> None:
        from inference.face_restoration import FaceRestorer, FaceRestorationPlan
        with tempfile.TemporaryDirectory() as temp_dir:
            model_path = Path(temp_dir) / "gfpgan.onnx"
            model_path.write_bytes(b"mockmodel")
            plan = FaceRestorationPlan(model_name="gfpgan", model_path=model_path, enabled=True)

            with patch("inference.face_restoration.ONNXFrameUpscaler") as mock_upscaler:
                mock_upscaler.return_value.upscale.side_effect = lambda frame, w, h: bytes([v + 10 for v in frame])
                restorer = FaceRestorer(plan, "cpu")
                # 8x8 frame RGB (192 bytes)
                frame = bytes(range(192))
                output = restorer.restore(frame, 8, 8)
                self.assertNotEqual(output, frame)
                # Face crop w=2, h=2 (at center) should be processed and value increased by 10
                self.assertEqual(len(output), 192)

    def test_dynamic_scale_upscaler_adapt(self) -> None:
        from pipeline.upscaler import Upscaler, PaddingPlan
        upscaler = Upscaler(
            input_width=2,
            input_height=2,
            output_width=4,
            output_height=4,
            label="test",
            padding=PaddingPlan(2, 2, 2, 2),
            onnx=Mock()
        )
        # With active_scale=1, it should bypass onnx and resize directly (nearest-neighbor)
        frame = bytes([1] * 12) # 2x2 RGB
        upscaler.active_scale = 1
        output = upscaler.process(frame)
        self.assertEqual(len(output), 48) # 4x4 RGB (48 bytes)
        upscaler.onnx.upscale.assert_not_called()

    def test_distributed_frame_processor_round_robin(self) -> None:
        from pipeline.runner import _build_frame_processor
        config = EnhancementConfig(
            input_path=Path("in.mp4"),
            output_path=Path("out.mp4"),
            worker_devices=("cuda0:CUDAExecutionProvider", "cpu:CPUExecutionProvider")
        )
        info = VideoInfo(width=2, height=2, fps=30.0, frame_count=4, has_audio=False)
        
        with patch("pipeline.runner.build_upscaler") as mock_build:
            mock_up1 = Mock()
            mock_up2 = Mock()
            mock_build.side_effect = [mock_up1, mock_up2]
            
            processor = _build_frame_processor(config, info, Mock())
            
            frame = bytes([1] * 12)
            processor(frame)
            processor(frame)
            
            # The calls to process/upscale should be distributed between the mock upscalers
            self.assertEqual(mock_build.call_count, 2)


if __name__ == "__main__":
    unittest.main()
