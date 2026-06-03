"""Tests for workflow scheduling, cron validation, job queues, and artifact manifests."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from app.config import EnhancementConfig
from app.jobs import JobQueue
from pipeline.workflow_profiles import (
    WorkflowScheduler,
    LocalJobQueue,
    QueuedJob,
    RecipeStore,
    ScheduleSpec,
    WorkflowProfile,
    cron_matches,
    enhancement_config_from_profile,
    validate_cron,
)
from pipeline.artifact_manifest import (
    ArtifactManifest,
    MediaFingerprint,
    ModelRecord,
    _sha256_bytes,
    write_render_manifest,
)


# ===========================================================================
# Task 3: Workflow Profiles
# ===========================================================================


class TestValidateCron(unittest.TestCase):
    def test_valid_expressions(self):
        self.assertTrue(validate_cron("0 2 * * *"))
        self.assertTrue(validate_cron("*/5 * * * *"))
        self.assertTrue(validate_cron("30 8 1 * 1"))

    def test_invalid_expressions(self):
        self.assertFalse(validate_cron(""))
        self.assertFalse(validate_cron("0 2 * *"))        # only 4 fields
        self.assertFalse(validate_cron("0 2 * * * *"))    # 6 fields

    def test_cron_matches_datetime(self):
        when = datetime(2026, 6, 3, 2, 0)
        self.assertTrue(cron_matches("0 2 * * *", when))
        self.assertTrue(cron_matches("*/5 * * * *", when))
        self.assertFalse(cron_matches("1 2 * * *", when))


class TestScheduleSpec(unittest.TestCase):
    def test_valid_cron(self):
        s = ScheduleSpec(cron="0 3 * * *", label="nightly")
        self.assertTrue(s.enabled)
        self.assertEqual(s.label, "nightly")

    def test_invalid_cron_raises(self):
        with self.assertRaises(ValueError):
            ScheduleSpec(cron="bad cron expr here")

    def test_roundtrip(self):
        s = ScheduleSpec(cron="0 3 * * *", enabled=False, label="test")
        s2 = ScheduleSpec.from_dict(s.to_dict())
        self.assertEqual(s2.cron, s.cron)
        self.assertFalse(s2.enabled)
        self.assertEqual(s2.label, "test")


class TestWorkflowProfile(unittest.TestCase):
    def _make(self, **kw) -> WorkflowProfile:
        defaults = dict(
            name="denoise_hd",
            params={"scale": 2, "model": "realesr"},
            launch_modes=["cli", "webui"],
        )
        defaults.update(kw)
        return WorkflowProfile(**defaults)

    def test_basic_creation(self):
        p = self._make()
        self.assertEqual(p.name, "denoise_hd")
        self.assertFalse(p.is_scheduled)

    def test_empty_name_raises(self):
        with self.assertRaises(ValueError):
            WorkflowProfile(name="")

    def test_invalid_launch_mode_raises(self):
        with self.assertRaises(ValueError):
            WorkflowProfile(name="x", launch_modes=["telegram"])

    def test_can_launch_from(self):
        p = self._make()
        self.assertTrue(p.can_launch_from("cli"))
        self.assertFalse(p.can_launch_from("desktop"))

    def test_is_scheduled_when_schedule_set(self):
        p = self._make(schedule=ScheduleSpec(cron="0 1 * * *"))
        self.assertTrue(p.is_scheduled)

    def test_is_not_scheduled_when_disabled(self):
        p = self._make(schedule=ScheduleSpec(cron="0 1 * * *", enabled=False))
        self.assertFalse(p.is_scheduled)

    def test_to_dict_contains_params(self):
        p = self._make()
        d = p.to_dict()
        self.assertEqual(d["params"]["scale"], 2)

    def test_to_dict_no_schedule_key_when_none(self):
        p = self._make()
        self.assertNotIn("schedule", p.to_dict())

    def test_to_dict_with_schedule(self):
        p = self._make(schedule=ScheduleSpec(cron="0 1 * * *"))
        d = p.to_dict()
        self.assertIn("schedule", d)
        self.assertEqual(d["schedule"]["cron"], "0 1 * * *")

    def test_json_roundtrip(self):
        p = self._make(
            schedule=ScheduleSpec(cron="30 6 * * 1"),
            tags=["hd", "night"],
        )
        p2 = WorkflowProfile.from_json(p.to_json())
        self.assertEqual(p2.name, p.name)
        self.assertEqual(p2.params, p.params)
        self.assertEqual(p2.tags, p.tags)
        self.assertTrue(p2.is_scheduled)

    def test_from_dict_no_schedule(self):
        p = WorkflowProfile.from_dict({"name": "simple", "params": {"scale": 1}})
        self.assertIsNone(p.schedule)


class TestRecipeStore(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.store = RecipeStore(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def _profile(self, name="test_recipe") -> WorkflowProfile:
        return WorkflowProfile(name=name, params={"scale": 2})

    def test_save_and_load(self):
        p = self._profile()
        self.store.save(p)
        loaded = self.store.load("test_recipe")
        self.assertEqual(loaded.name, "test_recipe")

    def test_contains(self):
        self.assertNotIn("test_recipe", self.store)
        self.store.save(self._profile())
        self.assertIn("test_recipe", self.store)

    def test_delete(self):
        self.store.save(self._profile())
        self.store.delete("test_recipe")
        self.assertNotIn("test_recipe", self.store)

    def test_load_missing_raises(self):
        with self.assertRaises(FileNotFoundError):
            self.store.load("ghost")

    def test_list_all(self):
        self.store.save(self._profile("a"))
        self.store.save(self._profile("b"))
        names = [p.name for p in self.store.list_all()]
        self.assertIn("a", names)
        self.assertIn("b", names)

    def test_list_empty_dir(self):
        empty_store = RecipeStore(Path(self._tmp.name) / "nonexistent")
        self.assertEqual(empty_store.list_all(), [])

    def test_list_scheduled(self):
        self.store.save(self._profile("no_sched"))
        scheduled = self._profile("nightly")
        scheduled.schedule = ScheduleSpec(cron="0 2 * * *")
        self.store.save(scheduled)
        scheduled_names = [p.name for p in self.store.list_scheduled()]
        self.assertIn("nightly", scheduled_names)
        self.assertNotIn("no_sched", scheduled_names)

    def test_special_chars_in_name_sanitised(self):
        p = WorkflowProfile(name="my recipe! v2", params={})
        path = self.store.save(p)
        self.assertTrue(path.exists())
        loaded = self.store.load("my recipe! v2")
        self.assertEqual(loaded.name, "my recipe! v2")


class TestLocalJobQueue(unittest.TestCase):
    def setUp(self):
        self.q = LocalJobQueue()

    def test_enqueue(self):
        job = self.q.enqueue("recipe_a", "cli")
        self.assertEqual(job.profile_name, "recipe_a")
        self.assertEqual(job.status, "queued")

    def test_pending(self):
        self.q.enqueue("a")
        self.q.enqueue("b")
        self.assertEqual(len(self.q.pending()), 2)

    def test_mark_running(self):
        job = self.q.enqueue("x")
        self.q.mark_running(job)
        self.assertEqual(job.status, "running")
        self.assertEqual(len(self.q.pending()), 0)

    def test_mark_done(self):
        job = self.q.enqueue("x")
        self.q.mark_done(job, result="output.mp4")
        self.assertEqual(job.status, "done")
        self.assertEqual(job.result, "output.mp4")

    def test_mark_failed(self):
        job = self.q.enqueue("x")
        self.q.mark_failed(job, error="timeout")
        self.assertEqual(job.status, "failed")

    def test_all_jobs(self):
        self.q.enqueue("a")
        self.q.enqueue("b")
        self.assertEqual(len(self.q.all_jobs()), 2)

    def test_clear(self):
        self.q.enqueue("a")
        self.q.clear()
        self.assertEqual(len(self.q), 0)

    def test_len(self):
        self.assertEqual(len(self.q), 0)
        self.q.enqueue("a")
        self.assertEqual(len(self.q), 1)


class TestWorkflowScheduler(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.store = RecipeStore(Path(self._tmp.name))
        self.scheduler = WorkflowScheduler(self.store)

    def tearDown(self):
        self._tmp.cleanup()

    def _scheduled_profile(self, name="nightly") -> WorkflowProfile:
        return WorkflowProfile(
            name=name,
            params={
                "input_path": "input.mp4",
                "output_path": "output.mp4",
                "scale": 2,
                "model": "realesrgan",
            },
            launch_modes=["cli"],
            schedule=ScheduleSpec(cron="0 2 * * *"),
        )

    def test_enhancement_config_from_profile(self):
        config = enhancement_config_from_profile(self._scheduled_profile())
        self.assertEqual(config.input_path, Path("input.mp4"))
        self.assertEqual(config.output_path, Path("output.mp4"))
        self.assertEqual(config.scale, 2)

    def test_due_profiles_filters_by_cron(self):
        self.store.save(self._scheduled_profile())
        due = self.scheduler.due_profiles(datetime(2026, 6, 3, 2, 0))
        not_due = self.scheduler.due_profiles(datetime(2026, 6, 3, 2, 1))
        self.assertEqual([profile.name for profile in due], ["nightly"])
        self.assertEqual(not_due, [])

    def test_enqueue_due_local_once_per_minute(self):
        self.store.save(self._scheduled_profile())
        queue = LocalJobQueue()
        when = datetime(2026, 6, 3, 2, 0)

        first = self.scheduler.enqueue_due_local(queue, when)
        second = self.scheduler.enqueue_due_local(queue, when)

        self.assertEqual(len(first), 1)
        self.assertEqual(len(second), 0)
        self.assertEqual(len(queue), 1)

    def test_submit_due_jobs_to_shared_queue(self):
        self.store.save(self._scheduled_profile())
        queue = JobQueue()

        submitted = self.scheduler.submit_due_jobs(queue, datetime(2026, 6, 3, 2, 0))

        self.assertEqual(len(submitted), 1)
        self.assertEqual(submitted[0].config.output_path, Path("output.mp4"))


# ===========================================================================
# Task 4: Artifact Manifest
# ===========================================================================


class TestMediaFingerprint(unittest.TestCase):
    def test_stub_roundtrip(self):
        fp = MediaFingerprint(path="/tmp/src.mp4", sha256="abc123", size_bytes=1024)
        fp2 = MediaFingerprint.from_dict(fp.to_dict())
        self.assertEqual(fp2.sha256, "abc123")
        self.assertEqual(fp2.size_bytes, 1024)

    def test_from_real_file(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as fh:
            fh.write(b"fakevideocontent")
            tmp = Path(fh.name)
        try:
            fp = MediaFingerprint.from_file(tmp)
            self.assertEqual(len(fp.sha256), 64)
            self.assertGreater(fp.size_bytes, 0)
        finally:
            tmp.unlink(missing_ok=True)


class TestModelRecord(unittest.TestCase):
    def test_stub_roundtrip(self):
        mr = ModelRecord(name="realesr", path="/models/r.onnx", sha256="def456")
        mr2 = ModelRecord.from_dict(mr.to_dict())
        self.assertEqual(mr2.name, "realesr")
        self.assertEqual(mr2.sha256, "def456")

    def test_from_real_file(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".onnx") as fh:
            fh.write(b"\x00" * 128)
            tmp = Path(fh.name)
        try:
            mr = ModelRecord.from_file("test_model", tmp)
            self.assertEqual(len(mr.sha256), 64)
        finally:
            tmp.unlink(missing_ok=True)


class TestArtifactManifest(unittest.TestCase):
    def _make(self) -> ArtifactManifest:
        m = ArtifactManifest(job_id="job_001")
        m.settings = {"scale": 4, "model": "realesr", "crf": 18}
        m.metrics = {"psnr": 34.2, "ssim": 0.97}
        m.add_model_stub("realesr", sha256="aaaa1111", path="/models/r.onnx")
        m.set_source_stub("/input/src.mp4", sha256="bbbb2222", size_bytes=5000000)
        m.set_output_stub("/output/out.mp4", sha256="cccc3333", size_bytes=12000000)
        return m

    def test_basic_fields(self):
        m = self._make()
        self.assertEqual(m.job_id, "job_001")
        self.assertEqual(m.settings["scale"], 4)
        self.assertEqual(m.metrics["psnr"], 34.2)

    def test_model_records(self):
        m = self._make()
        self.assertEqual(len(m.models), 1)
        self.assertEqual(m.models[0].name, "realesr")

    def test_source_fingerprint(self):
        m = self._make()
        self.assertIsNotNone(m.source)
        self.assertEqual(m.source.sha256, "bbbb2222")

    def test_output_fingerprint(self):
        m = self._make()
        self.assertIsNotNone(m.output)
        self.assertEqual(m.output.sha256, "cccc3333")

    def test_to_dict_has_all_keys(self):
        m = self._make()
        d = m.to_dict()
        for key in ("job_id", "created_at", "settings", "models", "metrics", "source", "output"):
            self.assertIn(key, d)

    def test_json_roundtrip(self):
        m = self._make()
        m2 = ArtifactManifest.from_json(m.to_json())
        self.assertEqual(m2.job_id, m.job_id)
        self.assertEqual(m2.settings, m.settings)
        self.assertEqual(m2.metrics, m.metrics)
        self.assertEqual(len(m2.models), 1)
        self.assertEqual(m2.source.sha256, "bbbb2222")
        self.assertEqual(m2.output.sha256, "cccc3333")

    def test_no_source_output_in_dict(self):
        m = ArtifactManifest(job_id="bare")
        d = m.to_dict()
        self.assertNotIn("source", d)
        self.assertNotIn("output", d)

    def test_manifest_digest_is_hex64(self):
        m = self._make()
        digest = m.manifest_digest()
        self.assertEqual(len(digest), 64)
        self.assertTrue(all(c in "0123456789abcdef" for c in digest))

    def test_manifest_digest_changes_with_content(self):
        m1 = self._make()
        m2 = self._make()
        m2.metrics["psnr"] = 99.0
        self.assertNotEqual(m1.manifest_digest(), m2.manifest_digest())

    def test_save_next_to(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "render.mp4"
            out.touch()
            m = self._make()
            manifest_path = m.save_next_to(out)
            self.assertTrue(manifest_path.exists())
            self.assertTrue(manifest_path.name.endswith(".manifest.json"))
            loaded = ArtifactManifest.load_from(manifest_path)
            self.assertEqual(loaded.job_id, "job_001")

    def test_save_to(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "subdir" / "manifest.json"
            m = self._make()
            m.save_to(target)
            self.assertTrue(target.exists())

    def test_add_model_from_real_file(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".onnx") as fh:
            fh.write(b"\x01" * 64)
            tmp = Path(fh.name)
        try:
            m = ArtifactManifest(job_id="j2")
            m.add_model_from_file("mymodel", tmp)
            self.assertEqual(len(m.models), 1)
            self.assertEqual(len(m.models[0].sha256), 64)
        finally:
            tmp.unlink(missing_ok=True)

    def test_chained_builders(self):
        m = (
            ArtifactManifest(job_id="chain")
            .add_model_stub("m1", "aaa")
            .add_model_stub("m2", "bbb")
            .set_source_stub("/src.mp4", "ccc")
            .set_output_stub("/out.mp4", "ddd")
        )
        self.assertEqual(len(m.models), 2)
        self.assertEqual(m.source.sha256, "ccc")

    def test_write_render_manifest_creates_sidecar_for_completed_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "input.mp4"
            output = root / "output.mp4"
            source.write_bytes(b"source")
            output.write_bytes(b"output")

            path = write_render_manifest(
                EnhancementConfig(
                    input_path=source,
                    output_path=output,
                    scale=2,
                ),
                job_id="job-render",
                metrics={"psnr": 40.0},
            )
            loaded = ArtifactManifest.load_from(path)

            self.assertTrue(path.exists())
            self.assertEqual(loaded.job_id, "job-render")
            self.assertEqual(loaded.metrics["psnr"], 40.0)
            self.assertIsNotNone(loaded.source)
            self.assertIsNotNone(loaded.output)


if __name__ == "__main__":
    unittest.main()
