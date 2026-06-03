"""Tests for preset entries, compatibility matrices, update verifier, and model rollback manager."""

from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from pipeline.preset_matrix import (
    VALID_CODECS,
    VALID_COLOR_FORMATS,
    VALID_PACKAGE_TARGETS,
    VALID_PLATFORMS,
    VALID_PROVIDERS,
    PresetCompatibilityMatrix,
    PresetEntry,
    build_default_matrix,
    current_platform_key,
    validate_current_environment,
    write_matrix_report,
)
from pipeline.update_manager import (
    ModelRollbackManager,
    UpdatePackageManifest,
    UpdateVerifier,
    _sha256_bytes,
)


# ===========================================================================
# Task 7: Preset Compatibility Matrix
# ===========================================================================


def _make_entry(name="h264_cpu", **kw) -> PresetEntry:
    defaults = dict(
        codec="h264",
        color_format="yuv420p",
        execution_providers={"cpu"},
        platforms={"linux", "macos", "windows"},
        package_targets={"wheel"},
    )
    defaults.update(kw)
    return PresetEntry(name=name, **defaults)


class TestPresetEntry(unittest.TestCase):
    def test_valid_creation(self):
        e = _make_entry()
        self.assertEqual(e.codec, "h264")

    def test_invalid_codec_raises(self):
        with self.assertRaises(ValueError):
            _make_entry(codec="mp4v")

    def test_invalid_color_format_raises(self):
        with self.assertRaises(ValueError):
            _make_entry(color_format="nv12")

    def test_invalid_provider_raises(self):
        with self.assertRaises(ValueError):
            _make_entry(execution_providers={"phantom_gpu"})

    def test_invalid_platform_raises(self):
        with self.assertRaises(ValueError):
            _make_entry(platforms={"bsd"})

    def test_invalid_package_target_raises(self):
        with self.assertRaises(ValueError):
            _make_entry(package_targets={"snap"})

    def test_supports_true(self):
        e = _make_entry(platforms={"linux"}, execution_providers={"cuda"})
        self.assertTrue(e.supports("linux", "cuda"))

    def test_supports_false_platform(self):
        e = _make_entry(platforms={"linux"}, execution_providers={"cuda"})
        self.assertFalse(e.supports("windows", "cuda"))

    def test_supports_false_provider(self):
        e = _make_entry(platforms={"linux"}, execution_providers={"cpu"})
        self.assertFalse(e.supports("linux", "cuda"))

    def test_to_dict(self):
        e = _make_entry()
        d = e.to_dict()
        self.assertEqual(d["codec"], "h264")
        self.assertIn("cpu", d["execution_providers"])


class TestPresetCompatibilityMatrix(unittest.TestCase):
    def setUp(self):
        self.m = PresetCompatibilityMatrix()

    def test_register_and_get(self):
        self.m.register(_make_entry())
        self.assertIn("h264_cpu", self.m)

    def test_duplicate_raises(self):
        self.m.register(_make_entry())
        with self.assertRaises(ValueError):
            self.m.register(_make_entry())

    def test_unregister(self):
        self.m.register(_make_entry())
        self.m.unregister("h264_cpu")
        self.assertNotIn("h264_cpu", self.m)

    def test_len(self):
        self.assertEqual(len(self.m), 0)
        self.m.register(_make_entry())
        self.assertEqual(len(self.m), 1)

    def test_list_all(self):
        self.m.register(_make_entry("a"))
        self.m.register(_make_entry("b"))
        self.assertEqual(len(self.m.list_all()), 2)

    def test_compatible_presets(self):
        self.m.register(_make_entry("linux_only", platforms={"linux"}, execution_providers={"cpu"}))
        self.m.register(_make_entry("win_only", platforms={"windows"}, execution_providers={"cpu"}))
        compat = self.m.compatible_presets("linux", "cpu")
        names = [p.name for p in compat]
        self.assertIn("linux_only", names)
        self.assertNotIn("win_only", names)

    def test_incompatible_presets(self):
        self.m.register(_make_entry("cpu_all", execution_providers={"cpu"}))
        self.m.register(_make_entry("cuda_linux", platforms={"linux"}, execution_providers={"cuda"}))
        incompat = self.m.incompatible_presets("macos", "cpu")
        names = [p.name for p in incompat]
        self.assertIn("cuda_linux", names)

    def test_validate_one_compatible(self):
        self.m.register(_make_entry())
        r = self.m.validate_one("h264_cpu", "linux", "cpu")
        self.assertTrue(r.compatible)
        self.assertEqual(r.reason, "")

    def test_validate_one_incompatible_platform(self):
        self.m.register(_make_entry(platforms={"linux"}))
        r = self.m.validate_one("h264_cpu", "windows", "cpu")
        self.assertFalse(r.compatible)
        self.assertIn("platform", r.reason)

    def test_validate_one_incompatible_provider(self):
        self.m.register(_make_entry(execution_providers={"cpu"}))
        r = self.m.validate_one("h264_cpu", "linux", "cuda")
        self.assertFalse(r.compatible)
        self.assertIn("provider", r.reason)

    def test_validate_all_returns_matrix(self):
        self.m.register(_make_entry())
        results = self.m.validate_all(platforms=["linux", "macos"], providers=["cpu", "cuda"])
        # 1 preset × 2 platforms × 2 providers = 4 results
        self.assertEqual(len(results), 4)

    def test_validate_all_empty_matrix(self):
        self.assertEqual(self.m.validate_all(), [])

    def test_validate_all_filter_platforms(self):
        self.m.register(_make_entry())
        results = self.m.validate_all(platforms=["linux"], providers=["cpu"])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].platform, "linux")


class TestBuildDefaultMatrix(unittest.TestCase):
    def setUp(self):
        self.m = build_default_matrix()

    def test_has_presets(self):
        self.assertGreater(len(self.m), 0)

    def test_h264_cpu_universal(self):
        e = self.m.get("h264_cpu_universal")
        self.assertTrue(e.supports("linux", "cpu"))
        self.assertTrue(e.supports("macos", "cpu"))
        self.assertTrue(e.supports("windows", "cpu"))

    def test_prores_coreml_macos_only(self):
        e = self.m.get("prores_coreml_macos")
        self.assertTrue(e.supports("macos", "coreml"))
        self.assertFalse(e.supports("linux", "coreml"))

    def test_h265_cuda_linux_only(self):
        e = self.m.get("h265_cuda_linux")
        self.assertTrue(e.supports("linux", "cuda"))
        self.assertFalse(e.supports("windows", "cuda"))

    def test_validate_all_runs(self):
        results = self.m.validate_all(
            platforms=["linux", "macos", "windows"],
            providers=["cpu", "cuda", "coreml"],
        )
        self.assertGreater(len(results), 0)
        compatible = [r for r in results if r.compatible]
        self.assertGreater(len(compatible), 0)

    def test_current_platform_key_maps_darwin(self):
        self.assertEqual(current_platform_key("Darwin"), "macos")

    def test_validate_current_environment(self):
        results = validate_current_environment(provider="cpu", system="Linux")
        self.assertGreater(len(results), 0)
        self.assertTrue(all(result.platform == "linux" for result in results))

    def test_write_matrix_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_matrix_report(Path(tmp) / "matrix.json", self.m)
            self.assertTrue(path.exists())
            self.assertIn("h264_cpu_universal", path.read_text("utf-8"))


# ===========================================================================
# Task 8: Update Verifier & Model Rollback Manager
# ===========================================================================


def _make_manifest(data: bytes, target: str = "model") -> UpdatePackageManifest:
    return UpdatePackageManifest(
        package_name="test_pkg",
        version="1.0.0",
        sha256=_sha256_bytes(data),
        target=target,
    )


class TestUpdatePackageManifest(unittest.TestCase):
    def test_roundtrip(self):
        m = UpdatePackageManifest("pkg", "1.0", "abc123", "app", "test")
        m2 = UpdatePackageManifest.from_dict(m.to_dict())
        self.assertEqual(m2.sha256, "abc123")
        self.assertEqual(m2.target, "app")

    def test_from_json_file(self):
        import json
        m = UpdatePackageManifest("pkg", "2.0", "def456", "model")
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as fh:
            json.dump(m.to_dict(), fh)
            p = Path(fh.name)
        try:
            m2 = UpdatePackageManifest.from_json_file(p)
            self.assertEqual(m2.version, "2.0")
        finally:
            p.unlink(missing_ok=True)


class TestUpdateVerifier(unittest.TestCase):
    def setUp(self):
        self.verifier = UpdateVerifier()

    def test_verify_bytes_pass(self):
        data = b"valid_package_data"
        m = _make_manifest(data)
        r = self.verifier.verify_bytes(m, data)
        self.assertTrue(r.passed)
        self.assertFalse(r.failed)

    def test_verify_bytes_fail(self):
        data = b"valid_package_data"
        m = _make_manifest(b"other_data")
        r = self.verifier.verify_bytes(m, data)
        self.assertFalse(r.passed)
        self.assertIn("mismatch", r.reason)

    def test_verify_file_pass(self):
        data = b"some_package_bytes"
        m = _make_manifest(data)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as fh:
            fh.write(data)
            p = Path(fh.name)
        try:
            r = self.verifier.verify(m, p)
            self.assertTrue(r.passed)
        finally:
            p.unlink(missing_ok=True)

    def test_verify_file_fail_wrong_content(self):
        m = _make_manifest(b"expected_content")
        with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as fh:
            fh.write(b"tampered_content")
            p = Path(fh.name)
        try:
            r = self.verifier.verify(m, p)
            self.assertFalse(r.passed)
        finally:
            p.unlink(missing_ok=True)

    def test_verify_file_missing(self):
        m = _make_manifest(b"x")
        r = self.verifier.verify(m, Path("/nonexistent/package.zip"))
        self.assertFalse(r.passed)
        self.assertIn("not found", r.reason)

    def test_result_metadata(self):
        data = b"pkg"
        m = _make_manifest(data)
        r = self.verifier.verify_bytes(m, data)
        self.assertEqual(r.package_name, "test_pkg")
        self.assertEqual(r.version, "1.0.0")
        self.assertEqual(r.expected_sha256, r.actual_sha256)

    def test_signed_manifest_passes_with_secret(self):
        data = b"signed_package"
        m = self.verifier.sign_manifest(_make_manifest(b""), data, "secret")
        r = self.verifier.verify_bytes(m, data, secret_key="secret")
        self.assertTrue(r.passed)
        self.assertTrue(r.signature_checked)

    def test_signed_manifest_fails_with_wrong_secret(self):
        data = b"signed_package"
        m = self.verifier.sign_manifest(_make_manifest(b""), data, "secret")
        r = self.verifier.verify_bytes(m, data, secret_key="wrong")
        self.assertFalse(r.passed)
        self.assertIn("signature", r.reason)


class TestModelRollbackManager(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.store = Path(self._tmp.name) / "rollback_store"
        self.mgr = ModelRollbackManager(self.store)

    def tearDown(self):
        self._tmp.cleanup()

    def test_snapshot_bytes_creates_file(self):
        snap = self.mgr.snapshot_bytes("realesr", "1.0.0", b"\x00" * 64)
        self.assertTrue((self.store / snap.snapshot_path).exists())

    def test_snapshot_bytes_records_sha256(self):
        data = b"model_weights_v1"
        snap = self.mgr.snapshot_bytes("realesr", "1.0.0", data)
        self.assertEqual(snap.sha256, _sha256_bytes(data))

    def test_history_ordered(self):
        self.mgr.snapshot_bytes("realesr", "0.9.0", b"v09")
        self.mgr.snapshot_bytes("realesr", "1.0.0", b"v10")
        h = self.mgr.history("realesr")
        self.assertEqual(len(h), 2)
        self.assertEqual(h[0].version, "0.9.0")
        self.assertEqual(h[1].version, "1.0.0")

    def test_latest(self):
        self.mgr.snapshot_bytes("realesr", "0.9.0", b"v09")
        self.mgr.snapshot_bytes("realesr", "1.0.0", b"v10")
        self.assertEqual(self.mgr.latest("realesr").version, "1.0.0")

    def test_previous(self):
        self.mgr.snapshot_bytes("realesr", "0.9.0", b"v09")
        self.mgr.snapshot_bytes("realesr", "1.0.0", b"v10")
        self.assertEqual(self.mgr.previous("realesr").version, "0.9.0")

    def test_previous_none_when_single_snapshot(self):
        self.mgr.snapshot_bytes("realesr", "1.0.0", b"v10")
        self.assertIsNone(self.mgr.previous("realesr"))

    def test_all_model_names(self):
        self.mgr.snapshot_bytes("realesr", "1.0.0", b"a")
        self.mgr.snapshot_bytes("gfpgan", "2.0.0", b"b")
        names = self.mgr.all_model_names()
        self.assertIn("realesr", names)
        self.assertIn("gfpgan", names)

    def test_rollback_bytes_restores_previous(self):
        self.mgr.snapshot_bytes("realesr", "0.9.0", b"old_weights")
        self.mgr.snapshot_bytes("realesr", "1.0.0", b"new_weights")
        restored = self.mgr.rollback_bytes("realesr")
        self.assertEqual(restored, b"old_weights")

    def test_rollback_no_previous_raises(self):
        self.mgr.snapshot_bytes("realesr", "1.0.0", b"only")
        with self.assertRaises(RuntimeError):
            self.mgr.rollback_bytes("realesr")

    def test_rollback_to_file(self):
        self.mgr.snapshot_bytes("realesr", "0.9.0", b"stable")
        self.mgr.snapshot_bytes("realesr", "1.0.0", b"unstable")
        target = self.store / "active_model.onnx"
        snap = self.mgr.rollback("realesr", target)
        self.assertTrue(target.exists())
        self.assertEqual(target.read_bytes(), b"stable")
        self.assertEqual(snap.version, "0.9.0")

    def test_index_persisted_and_reloaded(self):
        self.mgr.snapshot_bytes("realesr", "1.0.0", b"weights")
        # Reload from disk
        mgr2 = ModelRollbackManager(self.store)
        self.assertEqual(len(mgr2.history("realesr")), 1)

    def test_prune_keeps_recent(self):
        for i in range(5):
            self.mgr.snapshot_bytes("realesr", f"1.{i}.0", f"v{i}".encode())
        removed = self.mgr.prune("realesr", keep=2)
        self.assertEqual(removed, 3)
        self.assertEqual(len(self.mgr.history("realesr")), 2)

    def test_prune_no_op_when_under_limit(self):
        self.mgr.snapshot_bytes("realesr", "1.0.0", b"a")
        removed = self.mgr.prune("realesr", keep=5)
        self.assertEqual(removed, 0)

    def test_snapshot_from_real_file(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".onnx") as fh:
            fh.write(b"\xAB" * 128)
            p = Path(fh.name)
        try:
            snap = self.mgr.snapshot("realesr", "1.0.0", p)
            self.assertEqual(len(snap.sha256), 64)
            self.assertTrue((self.store / snap.snapshot_path).exists())
        finally:
            p.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
