"""Tests for plugin manifest validation, plugin registry, and sandboxed execution policies."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pipeline.plugin_sdk import (
    PluginManifest,
    PluginRegistry,
    VALID_STAGES,
    call_plugin,
    get_plugin,
    list_plugins,
    register_plugin,
    unregister_plugin,
    _default_registry,
)
from pipeline.plugin_sandbox import (
    ALL_PERMISSIONS,
    PermissionDeniedError,
    PluginSandbox,
    SandboxPolicy,
    SandboxedRegistry,
)
from pipeline.plugin_runtime import call_stage_plugins, collect_ffmpeg_filters
from pipeline.audit_log import AuditLog, EVENT_PERMISSION_DENIED, EVENT_PLUGIN_ACTION


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sample_manifest(**overrides) -> dict:
    base = {
        "name": "test_plugin",
        "version": "1.0.0",
        "stage": "model",
        "description": "A test plugin",
        "permissions": ["file.read", "model.load"],
    }
    base.update(overrides)
    return base


def _noop_handler(*args, **kwargs):
    return "ok"


def _permcheck_handler(*args, sandbox=None, **kwargs):
    """Handler that checks file.read permission before doing work."""
    sandbox.check_file_read()
    return "file_read_ok"


# ---------------------------------------------------------------------------
# Task 1: Plugin SDK Tests
# ---------------------------------------------------------------------------


class TestPluginManifest(unittest.TestCase):

    def test_from_dict_valid(self):
        m = PluginManifest.from_dict(_sample_manifest())
        self.assertEqual(m.name, "test_plugin")
        self.assertEqual(m.version, "1.0.0")
        self.assertEqual(m.stage, "model")
        self.assertIn("file.read", m.permissions)

    def test_missing_required_key_raises(self):
        bad = {"name": "x", "version": "1"}  # missing 'stage'
        with self.assertRaises(ValueError) as ctx:
            PluginManifest.from_dict(bad)
        self.assertIn("stage", str(ctx.exception))

    def test_invalid_stage_raises(self):
        with self.assertRaises(ValueError) as ctx:
            PluginManifest.from_dict(_sample_manifest(stage="unknown_stage"))
        self.assertIn("unknown_stage", str(ctx.exception))

    def test_all_valid_stages_accepted(self):
        for stage in VALID_STAGES:
            m = PluginManifest.from_dict(_sample_manifest(name=f"p_{stage}", stage=stage))
            self.assertEqual(m.stage, stage)

    def test_to_dict_roundtrip(self):
        data = _sample_manifest()
        m = PluginManifest.from_dict(data)
        d = m.to_dict()
        self.assertEqual(d["name"], data["name"])
        self.assertEqual(d["version"], data["version"])
        self.assertEqual(d["stage"], data["stage"])

    def test_from_json_file(self):
        data = _sample_manifest(name="file_plugin")
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as fh:
            json.dump(data, fh)
            tmp_path = Path(fh.name)
        try:
            m = PluginManifest.from_json_file(tmp_path)
            self.assertEqual(m.name, "file_plugin")
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_extra_metadata_stored(self):
        data = _sample_manifest(custom_key="hello")
        m = PluginManifest.from_dict(data)
        self.assertEqual(m.metadata.get("custom_key"), "hello")


class TestPluginRegistry(unittest.TestCase):

    def setUp(self):
        self.registry = PluginRegistry()

    def test_register_and_get(self):
        manifest = PluginManifest.from_dict(_sample_manifest())
        self.registry.register(manifest, _noop_handler)
        got = self.registry.get("test_plugin")
        self.assertEqual(got.name, "test_plugin")

    def test_register_dict_manifest(self):
        self.registry.register(_sample_manifest(name="dict_plugin"), _noop_handler)
        self.assertIn("dict_plugin", self.registry)

    def test_duplicate_registration_raises(self):
        self.registry.register(_sample_manifest(), _noop_handler)
        with self.assertRaises(ValueError):
            self.registry.register(_sample_manifest(), _noop_handler)

    def test_unregister(self):
        self.registry.register(_sample_manifest(), _noop_handler)
        self.registry.unregister("test_plugin")
        self.assertNotIn("test_plugin", self.registry)

    def test_list_all(self):
        self.registry.register(_sample_manifest(name="a", stage="model"), _noop_handler)
        self.registry.register(_sample_manifest(name="b", stage="ffmpeg_filter"), _noop_handler)
        self.assertEqual(len(self.registry.list_all()), 2)

    def test_list_by_stage(self):
        self.registry.register(_sample_manifest(name="a", stage="model"), _noop_handler)
        self.registry.register(_sample_manifest(name="b", stage="ffmpeg_filter"), _noop_handler)
        model_plugins = self.registry.list_by_stage("model")
        self.assertEqual(len(model_plugins), 1)
        self.assertEqual(model_plugins[0].name, "a")

    def test_call_handler(self):
        self.registry.register(_sample_manifest(), _noop_handler)
        result = self.registry.call("test_plugin")
        self.assertEqual(result, "ok")

    def test_call_without_handler_raises(self):
        self.registry.register(_sample_manifest())
        with self.assertRaises(RuntimeError):
            self.registry.call("test_plugin")

    def test_get_missing_raises(self):
        with self.assertRaises(KeyError):
            self.registry.get("nonexistent")

    def test_register_from_file(self):
        data = _sample_manifest(name="file_reg_plugin")
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as fh:
            json.dump(data, fh)
            tmp_path = Path(fh.name)
        try:
            m = self.registry.register_from_file(tmp_path, _noop_handler)
            self.assertEqual(m.name, "file_reg_plugin")
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_len(self):
        self.assertEqual(len(self.registry), 0)
        self.registry.register(_sample_manifest())
        self.assertEqual(len(self.registry), 1)


class TestModuleLevelHelpers(unittest.TestCase):
    """Test the default global registry convenience functions."""

    def setUp(self):
        # Clean slate: unregister any leftover 'global_plugin' from previous runs.
        unregister_plugin("global_plugin")

    def tearDown(self):
        unregister_plugin("global_plugin")

    def test_register_and_get_global(self):
        register_plugin(_sample_manifest(name="global_plugin"), _noop_handler)
        p = get_plugin("global_plugin")
        self.assertEqual(p.name, "global_plugin")

    def test_list_plugins_global(self):
        register_plugin(_sample_manifest(name="global_plugin", stage="export_hook"), _noop_handler)
        hooks = list_plugins(stage="export_hook")
        names = [p.name for p in hooks]
        self.assertIn("global_plugin", names)

    def test_call_plugin_global(self):
        register_plugin(_sample_manifest(name="global_plugin"), _noop_handler)
        result = call_plugin("global_plugin")
        self.assertEqual(result, "ok")


# ---------------------------------------------------------------------------
# Task 2: Plugin Sandbox Tests
# ---------------------------------------------------------------------------


class TestSandboxPolicy(unittest.TestCase):

    def test_effective_permissions_granted(self):
        policy = SandboxPolicy()
        granted = policy.effective_permissions(["file.read", "model.load"])
        self.assertIn("file.read", granted)
        self.assertIn("model.load", granted)

    def test_network_blocked_by_default(self):
        policy = SandboxPolicy()
        # 'network' is silently stripped even if declared
        granted = policy.effective_permissions(["network", "file.read"])
        self.assertNotIn("network", granted)
        self.assertIn("file.read", granted)

    def test_host_policy_denies_unlisted_permission(self):
        policy = SandboxPolicy(allowed_permissions={"file.read"})
        with self.assertRaises(PermissionDeniedError):
            policy.effective_permissions(["file.read", "file.write"])

    def test_unknown_permission_raises(self):
        policy = SandboxPolicy()
        with self.assertRaises(PermissionDeniedError):
            policy.effective_permissions(["totally.fake"])

    def test_network_allowed_when_policy_permits(self):
        policy = SandboxPolicy(
            allowed_permissions=ALL_PERMISSIONS,
            block_network=False,
        )
        granted = policy.effective_permissions(["network"])
        self.assertIn("network", granted)


class TestPluginSandbox(unittest.TestCase):

    def _make_manifest(self, permissions=None) -> PluginManifest:
        return PluginManifest.from_dict(
            _sample_manifest(permissions=permissions or ["file.read", "model.load"])
        )

    def test_has_permission_true(self):
        sb = PluginSandbox(self._make_manifest())
        self.assertTrue(sb.has_permission("file.read"))

    def test_has_permission_false(self):
        sb = PluginSandbox(self._make_manifest(permissions=["file.read"]))
        self.assertFalse(sb.has_permission("file.write"))

    def test_require_passes(self):
        sb = PluginSandbox(self._make_manifest())
        sb.require("file.read")  # should not raise

    def test_require_raises(self):
        sb = PluginSandbox(self._make_manifest(permissions=["file.read"]))
        with self.assertRaises(PermissionDeniedError):
            sb.require("file.write")

    def test_check_file_read(self):
        sb = PluginSandbox(self._make_manifest(permissions=["file.read"]))
        sb.check_file_read()  # no raise

    def test_check_file_write_raises_when_not_declared(self):
        sb = PluginSandbox(self._make_manifest(permissions=["file.read"]))
        with self.assertRaises(PermissionDeniedError):
            sb.check_file_write()

    def test_check_model_load(self):
        sb = PluginSandbox(self._make_manifest(permissions=["model.load"]))
        sb.check_model_load()

    def test_check_ffmpeg_filter(self):
        sb = PluginSandbox(self._make_manifest(permissions=["ffmpeg.filter"]))
        sb.check_ffmpeg_filter()

    def test_check_network_blocked_by_default(self):
        # policy.block_network=True strips 'network' even if declared
        sb = PluginSandbox(self._make_manifest(permissions=["file.read"]))
        with self.assertRaises(PermissionDeniedError):
            sb.check_network()

    def test_call_invokes_handler(self):
        manifest = self._make_manifest(permissions=["file.read"])
        sb = PluginSandbox(manifest)
        result = sb.call(_permcheck_handler)
        self.assertEqual(result, "file_read_ok")

    def test_call_handler_permission_denied(self):
        # Plugin declares no permissions → handler's require('file.read') raises.
        manifest = PluginManifest.from_dict(
            _sample_manifest(name="no_perm_plugin", permissions=[])
        )
        sb = PluginSandbox(manifest)
        # _permcheck_handler calls sandbox.check_file_read() internally.
        with self.assertRaises(PermissionDeniedError):
            sb.call(_permcheck_handler)

    def test_granted_permissions_is_frozenset(self):
        sb = PluginSandbox(self._make_manifest())
        gp = sb.granted_permissions
        self.assertIsInstance(gp, frozenset)

    def test_network_denied_when_policy_blocks(self):
        policy = SandboxPolicy(
            allowed_permissions=ALL_PERMISSIONS,
            block_network=True,  # still blocked
        )
        manifest = PluginManifest.from_dict(
            _sample_manifest(permissions=["file.read"])
        )
        sb = PluginSandbox(manifest, policy)
        with self.assertRaises(PermissionDeniedError):
            sb.check_network()


class TestSandboxedRegistry(unittest.TestCase):

    def setUp(self):
        self.registry = PluginRegistry()
        self.registry.register(
            _sample_manifest(permissions=["file.read", "model.load"]),
            _permcheck_handler,
        )
        self.sandboxed = SandboxedRegistry(self.registry)

    def test_sandboxed_call_success(self):
        result = self.sandboxed.call("test_plugin")
        self.assertEqual(result, "file_read_ok")

    def test_granted_permissions_query(self):
        granted = self.sandboxed.granted_permissions("test_plugin")
        self.assertIn("file.read", granted)

    def test_sandbox_for_returns_sandbox(self):
        sb = self.sandboxed.sandbox_for("test_plugin")
        self.assertIsInstance(sb, PluginSandbox)

    def test_sandboxed_call_denied_raises(self):
        # Register a plugin that needs file.write but policy doesn't allow it
        restricted_policy = SandboxPolicy(allowed_permissions={"file.read"})
        registry2 = PluginRegistry()

        def needs_write(*args, sandbox=None, **kwargs):
            sandbox.check_file_write()
            return "write_ok"

        registry2.register(
            _sample_manifest(name="restricted", permissions=["file.read"]),
            needs_write,
        )
        sr = SandboxedRegistry(registry2, restricted_policy)
        with self.assertRaises(PermissionDeniedError):
            sr.call("restricted")


class TestPluginRuntimeIntegration(unittest.TestCase):
    def tearDown(self):
        unregister_plugin("runtime_model")
        unregister_plugin("runtime_filter")
        unregister_plugin("runtime_denied")

    def test_model_stage_plugins_are_piped_through_sandbox(self):
        def add_one(frame, *, sandbox=None, **_context):
            sandbox.check_model_load()
            return bytes(value + 1 for value in frame)

        register_plugin(
            _sample_manifest(
                name="runtime_model",
                stage="model",
                permissions=["model.load"],
            ),
            add_one,
        )

        self.assertEqual(call_stage_plugins("model", bytes([1, 2])), bytes([2, 3]))

    def test_ffmpeg_filter_plugins_are_collected_through_sandbox(self):
        def filter_hook(*, sandbox=None, **_context):
            sandbox.check_ffmpeg_filter()
            return "hflip"

        register_plugin(
            _sample_manifest(
                name="runtime_filter",
                stage="ffmpeg_filter",
                permissions=["ffmpeg.filter"],
            ),
            filter_hook,
        )

        self.assertEqual(collect_ffmpeg_filters(), ("hflip",))

    def test_runtime_denies_undeclared_permissions(self):
        def needs_write(frame, *, sandbox=None, **_context):
            sandbox.check_file_write()
            return frame

        register_plugin(
            _sample_manifest(
                name="runtime_denied",
                stage="model",
                permissions=["model.load"],
            ),
            needs_write,
        )

        with self.assertRaises(PermissionDeniedError):
            call_stage_plugins("model", b"abc")

    def test_runtime_writes_plugin_audit_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit = AuditLog(Path(tmp) / "audit.ndjson")

            def add_one(frame, *, sandbox=None, **_context):
                sandbox.check_model_load()
                return bytes(value + 1 for value in frame)

            register_plugin(
                _sample_manifest(
                    name="runtime_model",
                    stage="model",
                    permissions=["model.load"],
                ),
                add_one,
            )

            call_stage_plugins("model", bytes([1]), audit_log=audit)

            entries = audit.all_entries()
            self.assertEqual(entries[0].event_type, EVENT_PLUGIN_ACTION)
            self.assertEqual(entries[0].plugin_id, "runtime_model")

    def test_runtime_writes_permission_denied_audit_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit = AuditLog(Path(tmp) / "audit.ndjson")

            def needs_write(frame, *, sandbox=None, **_context):
                sandbox.check_file_write()
                return frame

            register_plugin(
                _sample_manifest(
                    name="runtime_denied",
                    stage="model",
                    permissions=["model.load"],
                ),
                needs_write,
            )

            with self.assertRaises(PermissionDeniedError):
                call_stage_plugins("model", b"abc", audit_log=audit)

            entries = audit.all_entries()
            self.assertEqual(entries[0].event_type, EVENT_PERMISSION_DENIED)
            self.assertEqual(entries[0].plugin_id, "runtime_denied")


if __name__ == "__main__":
    unittest.main()
