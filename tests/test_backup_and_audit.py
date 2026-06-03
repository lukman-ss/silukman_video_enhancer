"""Tests for config backup/migration and audit logging/verification."""

from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path

from pipeline.config_backup import (
    APP_VERSION,
    BackupManifest,
    ConfigBackup,
    MigrationChain,
    MigrationRule,
    SECTION_PLUGINS,
    SECTION_PRESETS,
    SECTION_SERVER,
    backup_config_directory,
    is_compatible,
    restore_config_directory,
)
from pipeline.audit_log import (
    ALL_EVENT_TYPES,
    EVENT_API_REQUEST,
    EVENT_JOB_COMPLETED,
    EVENT_JOB_FAILED,
    EVENT_JOB_QUEUED,
    EVENT_JOB_STARTED,
    EVENT_PERMISSION_DENIED,
    EVENT_PERMISSION_GRANTED,
    EVENT_PLUGIN_ACTION,
    AuditEntry,
    AuditLog,
    _sanitise,
)


# ===========================================================================
# Task 5: Config Backup / Restore / Migration
# ===========================================================================


class TestIsCompatible(unittest.TestCase):
    def test_same_major(self):
        self.assertTrue(is_compatible("1.0.0", "1.2.3"))

    def test_different_major(self):
        self.assertFalse(is_compatible("2.0.0", "1.0.0"))

    def test_zero_major(self):
        self.assertTrue(is_compatible("0.5.0", "0.9.1"))


class TestBackupManifest(unittest.TestCase):
    def test_roundtrip(self):
        m = BackupManifest(sections=["presets", "plugins"], notes="test")
        m2 = BackupManifest.from_dict(m.to_dict())
        self.assertEqual(m2.sections, ["presets", "plugins"])
        self.assertEqual(m2.notes, "test")
        self.assertEqual(m2.app_version, APP_VERSION)

    def test_defaults(self):
        m = BackupManifest()
        self.assertEqual(m.app_version, APP_VERSION)
        self.assertIsInstance(m.created_at, str)


class TestConfigBackup(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _backup_path(self, name="backup.zip") -> Path:
        return self.tmp / name

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def test_save_creates_zip(self):
        cb = ConfigBackup()
        cb.add_section(SECTION_PRESETS, {"4k": {"scale": 4}})
        path = cb.save(self._backup_path())
        self.assertTrue(path.exists())
        self.assertGreater(path.stat().st_size, 0)

    def test_save_contains_manifest(self):
        import zipfile
        cb = ConfigBackup()
        cb.add_section(SECTION_PRESETS, {})
        path = cb.save(self._backup_path())
        with zipfile.ZipFile(path) as zf:
            self.assertIn("backup_manifest.json", zf.namelist())

    def test_save_contains_section_files(self):
        import zipfile
        cb = ConfigBackup()
        cb.add_section(SECTION_PRESETS, {"a": 1})
        cb.add_section(SECTION_PLUGINS, {"b": 2})
        path = cb.save(self._backup_path())
        with zipfile.ZipFile(path) as zf:
            self.assertIn("presets.json", zf.namelist())
            self.assertIn("plugins.json", zf.namelist())

    def test_chained_add_section(self):
        cb = (
            ConfigBackup()
            .add_section(SECTION_PRESETS, {"x": 1})
            .add_section(SECTION_SERVER, {"port": 8080})
        )
        path = cb.save(self._backup_path())
        sections = ConfigBackup.list_sections(path)
        self.assertIn(SECTION_PRESETS, sections)
        self.assertIn(SECTION_SERVER, sections)

    # ------------------------------------------------------------------
    # Restore
    # ------------------------------------------------------------------

    def test_restore_sections(self):
        cb = ConfigBackup()
        cb.add_section(SECTION_PRESETS, {"scale_4k": {"scale": 4}})
        cb.add_section(SECTION_PLUGINS, {"my_plugin": {"active": True}})
        path = cb.save(self._backup_path())

        sections, manifest = ConfigBackup.restore(path)
        self.assertIn(SECTION_PRESETS, sections)
        self.assertEqual(sections[SECTION_PRESETS]["scale_4k"]["scale"], 4)
        self.assertIn(SECTION_PLUGINS, sections)

    def test_restore_manifest_metadata(self):
        cb = ConfigBackup(notes="nightly backup")
        cb.add_section(SECTION_PRESETS, {})
        path = cb.save(self._backup_path())
        _, manifest = ConfigBackup.restore(path)
        self.assertEqual(manifest.notes, "nightly backup")
        self.assertEqual(manifest.app_version, APP_VERSION)

    def test_restore_incompatible_version_raises(self):
        import zipfile
        # Manually craft a backup with major version 99
        bad_manifest = BackupManifest(sections=["presets"])
        bad_manifest.app_version = "99.0.0"
        path = self._backup_path("bad.zip")
        with zipfile.ZipFile(path, "w") as zf:
            zf.writestr("backup_manifest.json", json.dumps(bad_manifest.to_dict()))
            zf.writestr("presets.json", "{}")
        with self.assertRaises(ValueError):
            ConfigBackup.restore(path)

    def test_list_sections(self):
        cb = ConfigBackup()
        cb.add_section("alpha", {})
        cb.add_section("beta", {})
        path = cb.save(self._backup_path())
        sections = ConfigBackup.list_sections(path)
        self.assertIn("alpha", sections)
        self.assertIn("beta", sections)

    # ------------------------------------------------------------------
    # Migration
    # ------------------------------------------------------------------

    def test_migration_chain_transforms_data(self):
        chain = MigrationChain()
        rule = MigrationRule(
            from_version="1.0.0",
            to_version="1.1.0",
            transform=lambda d: {**d, "migrated": True},
        )
        chain.add_rule(rule)

        cb = ConfigBackup()
        cb.add_section(SECTION_PRESETS, {"scale": 2})
        path = cb.save(self._backup_path())

        sections, _ = ConfigBackup.restore(path, migration_chain=chain)
        self.assertTrue(sections[SECTION_PRESETS].get("migrated"))

    def test_migration_rule_not_applied_for_wrong_version(self):
        chain = MigrationChain()
        rule = MigrationRule(
            from_version="0.5.0",
            to_version="0.6.0",
            transform=lambda d: {**d, "should_not_appear": True},
        )
        chain.add_rule(rule)

        cb = ConfigBackup()
        cb.add_section(SECTION_PRESETS, {"scale": 2})
        path = cb.save(self._backup_path())

        sections, _ = ConfigBackup.restore(path, migration_chain=chain)
        self.assertNotIn("should_not_appear", sections[SECTION_PRESETS])

    def test_migration_rule_applies_check(self):
        rule = MigrationRule("1.0.0", "1.1.0", lambda d: d)
        self.assertTrue(rule.applies("1.0.0"))
        self.assertFalse(rule.applies("1.1.0"))

    def test_backup_and_restore_config_directory(self):
        source = self.tmp / "config"
        target = self.tmp / "restored"
        source.mkdir()
        (source / "presets.json").write_text(
            json.dumps({"cinema": {"scale": 4}}),
            encoding="utf-8",
        )
        (source / "plugins.json").write_text(
            json.dumps({"plug": {"enabled": True}}),
            encoding="utf-8",
        )

        backup_path = backup_config_directory(source, self._backup_path("dir.zip"))
        manifest = restore_config_directory(backup_path, target)

        self.assertIn(SECTION_PRESETS, manifest.sections)
        restored_presets = json.loads((target / "presets.json").read_text("utf-8"))
        restored_plugins = json.loads((target / "plugins.json").read_text("utf-8"))
        self.assertEqual(restored_presets["cinema"]["scale"], 4)
        self.assertTrue(restored_plugins["plug"]["enabled"])


# ===========================================================================
# Task 6: Audit Log
# ===========================================================================


class TestSanitise(unittest.TestCase):
    def test_removes_sensitive_keys(self):
        d = {"endpoint": "/jobs", "input_path": "/secret/video.mp4", "token": "abc"}
        clean = _sanitise(d)
        self.assertIn("endpoint", clean)
        self.assertNotIn("input_path", clean)
        self.assertNotIn("token", clean)

    def test_keeps_non_sensitive(self):
        d = {"status": 200, "method": "GET"}
        clean = _sanitise(d)
        self.assertEqual(clean, d)


class TestAuditEntry(unittest.TestCase):
    def test_valid_entry(self):
        e = AuditEntry(event_type=EVENT_API_REQUEST, actor="api")
        self.assertEqual(e.event_type, EVENT_API_REQUEST)
        self.assertIsInstance(e.timestamp, str)

    def test_invalid_event_type_raises(self):
        with self.assertRaises(ValueError):
            AuditEntry(event_type="fake.event", actor="api")

    def test_sensitive_detail_stripped(self):
        e = AuditEntry(
            event_type=EVENT_API_REQUEST,
            actor="api",
            detail={"endpoint": "/jobs", "password": "hunter2"},
        )
        self.assertNotIn("password", e.detail)
        self.assertIn("endpoint", e.detail)

    def test_to_dict_job_id(self):
        e = AuditEntry(EVENT_JOB_QUEUED, "scheduler", job_id="j001")
        d = e.to_dict()
        self.assertEqual(d["job_id"], "j001")

    def test_to_dict_no_optional_keys_when_none(self):
        e = AuditEntry(EVENT_API_REQUEST, "api")
        d = e.to_dict()
        self.assertNotIn("job_id", d)
        self.assertNotIn("plugin_id", d)

    def test_to_json_line_is_single_line(self):
        e = AuditEntry(EVENT_API_REQUEST, "api")
        line = e.to_json_line()
        self.assertNotIn("\n", line)

    def test_roundtrip(self):
        e = AuditEntry(
            event_type=EVENT_PLUGIN_ACTION,
            actor="plugin:my_plugin",
            plugin_id="my_plugin",
            detail={"action": "filter"},
        )
        e2 = AuditEntry.from_dict(e.to_dict())
        self.assertEqual(e2.event_type, e.event_type)
        self.assertEqual(e2.actor, e.actor)
        self.assertEqual(e2.plugin_id, e.plugin_id)


class TestAuditLog(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.log = AuditLog(Path(self._tmp.name) / "audit.ndjson")

    def tearDown(self):
        self._tmp.cleanup()

    def test_record_creates_file(self):
        self.log.record(EVENT_API_REQUEST, "api")
        self.assertTrue(self.log.path.exists())

    def test_tail_returns_entries(self):
        self.log.record(EVENT_API_REQUEST, "api")
        self.log.record(EVENT_JOB_QUEUED, "scheduler", job_id="j1")
        entries = self.log.tail(10)
        self.assertEqual(len(entries), 2)

    def test_tail_limits_count(self):
        for i in range(10):
            self.log.record(EVENT_API_REQUEST, "api")
        self.assertEqual(len(self.log.tail(3)), 3)

    def test_tail_empty_log(self):
        self.assertEqual(self.log.tail(), [])

    def test_all_entries(self):
        self.log.record(EVENT_JOB_STARTED, "scheduler", job_id="j1")
        self.log.record(EVENT_JOB_COMPLETED, "scheduler", job_id="j1")
        self.assertEqual(len(self.log.all_entries()), 2)

    def test_filter_by_event_type(self):
        self.log.record(EVENT_API_REQUEST, "api")
        self.log.record(EVENT_JOB_QUEUED, "scheduler", job_id="j1")
        api_entries = self.log.filter(event_type=EVENT_API_REQUEST)
        self.assertEqual(len(api_entries), 1)

    def test_filter_by_actor(self):
        self.log.record(EVENT_API_REQUEST, "api")
        self.log.record(EVENT_PLUGIN_ACTION, "plugin:foo", plugin_id="foo")
        result = self.log.filter(actor="plugin:foo")
        self.assertEqual(len(result), 1)

    def test_filter_by_job_id(self):
        self.log.record(EVENT_JOB_STARTED, "scheduler", job_id="j42")
        self.log.record(EVENT_JOB_STARTED, "scheduler", job_id="j99")
        result = self.log.filter(job_id="j42")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].job_id, "j42")

    def test_filter_by_plugin_id(self):
        self.log.record(EVENT_PLUGIN_ACTION, "plugin:a", plugin_id="a")
        self.log.record(EVENT_PLUGIN_ACTION, "plugin:b", plugin_id="b")
        result = self.log.filter(plugin_id="b")
        self.assertEqual(len(result), 1)

    def test_clear(self):
        self.log.record(EVENT_API_REQUEST, "api")
        self.log.clear()
        self.assertEqual(self.log.all_entries(), [])

    def test_log_api_helper(self):
        e = self.log.log_api("/jobs", method="POST", status=202)
        self.assertEqual(e.event_type, EVENT_API_REQUEST)
        self.assertEqual(e.detail["endpoint"], "/jobs")
        self.assertEqual(e.detail["status"], 202)

    def test_log_plugin_helper(self):
        e = self.log.log_plugin("my_plugin", "denoise")
        self.assertEqual(e.event_type, EVENT_PLUGIN_ACTION)
        self.assertEqual(e.plugin_id, "my_plugin")

    def test_log_job_queued(self):
        e = self.log.log_job(EVENT_JOB_QUEUED, "j1")
        self.assertEqual(e.job_id, "j1")

    def test_log_job_failed(self):
        e = self.log.log_job(EVENT_JOB_FAILED, "j2")
        self.assertEqual(e.event_type, EVENT_JOB_FAILED)

    def test_log_permission_granted(self):
        e = self.log.log_permission(True, "my_plugin", "file.read")
        self.assertEqual(e.event_type, EVENT_PERMISSION_GRANTED)
        self.assertEqual(e.detail["permission"], "file.read")

    def test_log_permission_denied(self):
        e = self.log.log_permission(False, "evil_plugin", "network")
        self.assertEqual(e.event_type, EVENT_PERMISSION_DENIED)

    def test_sensitive_detail_not_persisted(self):
        self.log.record(
            EVENT_API_REQUEST,
            "api",
            detail={"endpoint": "/upload", "file_path": "/secret.mp4"},
        )
        entries = self.log.all_entries()
        self.assertNotIn("file_path", entries[0].detail)

    def test_thread_safety(self):
        """Multiple threads appending simultaneously should not corrupt the log."""
        errors = []

        def _write():
            try:
                for _ in range(20):
                    self.log.record(EVENT_API_REQUEST, "api")
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=_write) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [], f"Thread errors: {errors}")
        self.assertEqual(len(self.log.all_entries()), 100)

    def test_subdirectory_created_automatically(self):
        nested_log = AuditLog(
            Path(self._tmp.name) / "subdir" / "nested" / "audit.ndjson"
        )
        nested_log.record(EVENT_API_REQUEST, "api")
        self.assertTrue(nested_log.path.exists())


if __name__ == "__main__":
    unittest.main()
