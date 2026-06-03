"""Tests for Phase 8 desktop batch queue helpers and workers."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.config import EnhancementConfig
from app.workers import BatchCancelToken, BatchCancelledError, run_batch_jobs
from ui.desktop_queue import (
    DesktopEtaTracker,
    DesktopQueueModel,
    default_batch_output_path,
    supported_video_paths,
    with_output_format,
)
from ui.desktop_state import DesktopSettings, DesktopSettingsStore


class DesktopQueueModelTests(unittest.TestCase):
    def test_supported_video_paths_filters_and_preserves_order(self) -> None:
        paths = [
            Path("a.mp4"),
            Path("notes.txt"),
            Path("b.MOV"),
            Path("c.webm"),
        ]

        supported = supported_video_paths(paths)

        self.assertEqual(supported, [Path("a.mp4"), Path("b.MOV"), Path("c.webm")])

    def test_add_files_accumulates_multiple_unique_videos(self) -> None:
        model = DesktopQueueModel()

        added = model.add_files([Path("a.mp4"), Path("b.mkv"), Path("a.mp4")])

        self.assertEqual(len(added), 2)
        self.assertEqual(len(model), 2)
        self.assertEqual(model.items()[0].status, "Pending")

    def test_default_batch_output_path_uses_same_directory(self) -> None:
        path = default_batch_output_path(Path("/tmp/source.mov"))

        self.assertEqual(path, Path("/tmp/source_enhanced.mp4"))

    def test_default_batch_output_path_accepts_container_format(self) -> None:
        path = default_batch_output_path(Path("/tmp/source.mov"), ".mkv")

        self.assertEqual(path, Path("/tmp/source_enhanced.mkv"))

    def test_with_output_format_normalizes_supported_extension(self) -> None:
        self.assertEqual(with_output_format(Path("/tmp/source_enhanced.mp4"), "mov"), Path("/tmp/source_enhanced.mov"))

    def test_with_output_format_rejects_unsupported_extension(self) -> None:
        with self.assertRaises(ValueError):
            with_output_format(Path("/tmp/source_enhanced.mp4"), ".avi")

    def test_configs_from_base_creates_per_file_outputs(self) -> None:
        model = DesktopQueueModel()
        model.add_files([Path("a.mp4"), Path("b.mp4")])
        base = EnhancementConfig(
            input_path=Path("placeholder.mp4"),
            output_path=Path("unused.mp4"),
            model="swinir",
            scale=4,
            device="cpu",
            crf=20,
        )

        configs = model.configs_from_base(base)

        self.assertEqual(len(configs), 2)
        self.assertEqual(configs[0].input_path, Path("a.mp4"))
        self.assertEqual(configs[0].output_path, Path("a_enhanced.mp4"))
        self.assertEqual(configs[1].output_path, Path("b_enhanced.mp4"))
        self.assertTrue(all(config.batch for config in configs))
        self.assertEqual(configs[0].model, "swinir")

    def test_update_status_progress_and_message(self) -> None:
        model = DesktopQueueModel()
        model.add_files([Path("a.mp4")])

        item = model.update(0, status="Processing", progress=125, message="working")

        self.assertEqual(item.status, "Processing")
        self.assertEqual(item.progress, 100)
        self.assertEqual(item.message, "working")

    def test_remove_many_removes_selected_rows_without_reordering_remaining(self) -> None:
        model = DesktopQueueModel()
        model.add_files([Path("a.mp4"), Path("b.mp4"), Path("c.mp4")])

        removed = model.remove_many([2, 0])

        self.assertEqual([item.input_path for item in removed], [Path("a.mp4"), Path("c.mp4")])
        self.assertEqual([item.input_path for item in model.items()], [Path("b.mp4")])

    def test_move_reorders_queue_items(self) -> None:
        model = DesktopQueueModel()
        model.add_files([Path("a.mp4"), Path("b.mp4"), Path("c.mp4")])

        moved = model.move(2, 0)

        self.assertEqual(moved.input_path, Path("c.mp4"))
        self.assertEqual([item.input_path for item in model.items()], [Path("c.mp4"), Path("a.mp4"), Path("b.mp4")])

    def test_reorder_by_input_paths_keeps_unmentioned_items_at_end(self) -> None:
        model = DesktopQueueModel()
        model.add_files([Path("a.mp4"), Path("b.mp4"), Path("c.mp4")])

        model.reorder_by_input_paths([Path("b.mp4"), Path("a.mp4")])

        self.assertEqual([item.input_path for item in model.items()], [Path("b.mp4"), Path("a.mp4"), Path("c.mp4")])

    def test_set_output_format_updates_queue_paths_and_configs(self) -> None:
        model = DesktopQueueModel()
        model.add_files([Path("a.mp4"), Path("b.mp4")])
        base = EnhancementConfig(input_path=Path("unused.mp4"), output_path=Path("unused.mp4"))

        model.set_all_output_format(".mov")
        configs = model.configs_from_base(base)

        self.assertEqual([item.output_format for item in model.items()], [".mov", ".mov"])
        self.assertEqual([item.output_path for item in model.items()], [Path("a_enhanced.mov"), Path("b_enhanced.mov")])
        self.assertEqual([config.output_path for config in configs], [Path("a_enhanced.mov"), Path("b_enhanced.mov")])

    def test_retry_failed_resets_error_rows_only(self) -> None:
        model = DesktopQueueModel()
        model.add_files([Path("a.mp4"), Path("b.mp4")])
        model.update(0, status="Error", progress=45, message="failed")
        model.update(1, status="Done", progress=100, message="ok")

        retried = model.retry_failed()

        self.assertEqual([item.input_path for item in retried], [Path("a.mp4")])
        self.assertEqual(model.items()[0].status, "Pending")
        self.assertEqual(model.items()[0].progress, 0)
        self.assertEqual(model.items()[1].status, "Done")

    def test_eta_tracker_formats_remaining_time(self) -> None:
        tracker = DesktopEtaTracker()
        tracker.reset(now=0.0)

        self.assertEqual(tracker.label(50, now=10.0), "ETA 00:10")
        self.assertEqual(tracker.label(100, now=20.0), "ETA 00:00")
        fresh = DesktopEtaTracker()
        self.assertEqual(fresh.label(0, now=0.0), "ETA calculating...")


class BatchWorkerTests(unittest.TestCase):
    def test_run_batch_jobs_processes_configs_sequentially(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            configs = [
                EnhancementConfig(root / "a.mp4", root / "a_out.mp4"),
                EnhancementConfig(root / "b.mp4", root / "b_out.mp4"),
            ]
            for config in configs:
                config.input_path.write_bytes(b"video")
            events = []

            with patch("app.workers.run_desktop_job") as run_job:
                run_job.side_effect = [configs[0].output_path, configs[1].output_path]
                outputs = run_batch_jobs(configs, lambda *event: events.append(event))

            self.assertEqual(outputs, [configs[0].output_path, configs[1].output_path])
            self.assertEqual(run_job.call_count, 2)
            self.assertTrue(any(event[3].startswith("[1/2] Done") for event in events))
            self.assertTrue(any(event[3].startswith("[2/2] Done") for event in events))

    def test_run_batch_jobs_honors_cancel_token_before_next_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            configs = [
                EnhancementConfig(root / "a.mp4", root / "a_out.mp4"),
                EnhancementConfig(root / "b.mp4", root / "b_out.mp4"),
            ]
            for config in configs:
                config.input_path.write_bytes(b"video")
            token = BatchCancelToken()
            events = []

            def fake_run(config, emit, **_kwargs):
                token.cancel()
                return config.output_path

            with patch("app.workers.run_desktop_job", side_effect=fake_run) as run_job:
                outputs = run_batch_jobs(
                    configs,
                    lambda *event: events.append(event),
                    stop_flag=token.is_cancelled,
                )

            self.assertEqual(outputs, [configs[0].output_path])
            self.assertEqual(run_job.call_count, 1)
            self.assertTrue(any("Cancelled" in event[3] for event in events))

    def test_run_batch_jobs_cancels_current_job_via_progress_callback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = EnhancementConfig(root / "a.mp4", root / "a_out.mp4")
            config.input_path.write_bytes(b"video")
            token = BatchCancelToken()
            events = []

            def fake_run(_config, emit, should_cancel=None):
                token.cancel()
                emit(1, "halfway")
                if should_cancel is not None and should_cancel():
                    raise BatchCancelledError("cancelled")
                return _config.output_path

            with patch("app.workers.run_desktop_job", side_effect=fake_run):
                outputs = run_batch_jobs(
                    [config],
                    lambda *event: events.append(event),
                    stop_flag=token.is_cancelled,
                )

            self.assertEqual(outputs, [])
            self.assertTrue(any("Cancelled" in event[3] for event in events))


class DesktopSettingsStoreTests(unittest.TestCase):
    def test_settings_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = DesktopSettingsStore(Path(tmp) / "settings.json")
            settings = DesktopSettings(
                model="swinir",
                scale=4,
                device="cpu",
                crf=20,
                denoise=True,
                color_correct=True,
            )

            store.save(settings)
            loaded = store.load()

            self.assertEqual(loaded.model, "swinir")
            self.assertEqual(loaded.scale, 4)
            self.assertTrue(loaded.denoise)

    def test_recent_files_are_unique_and_limited(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = DesktopSettingsStore(Path(tmp) / "settings.json", max_recent=3)

            settings = store.remember_files([
                Path("a.mp4"),
                Path("b.mp4"),
                Path("a.mp4"),
                Path("c.mp4"),
                Path("d.mp4"),
            ])

            self.assertEqual(settings.recent_files, ["a.mp4", "b.mp4", "c.mp4"])

            settings = store.remember_files([Path("d.mp4")])
            self.assertEqual(settings.recent_files, ["d.mp4", "a.mp4", "b.mp4"])


if __name__ == "__main__":
    unittest.main()
