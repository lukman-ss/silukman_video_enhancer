"""Tests for model verification/quarantining and telemetry collection/exporting."""

from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path

from pipeline.model_verifier import (
    DEFAULT_SAFE_OPS,
    ModelVerificationResult,
    ModelVerifier,
    QuarantineManager,
    QuarantineRecord,
    verify_or_quarantine_model,
    _scan_onnx_ops,
    _sha256_file,
)
from pipeline.telemetry_collector import (
    TelemetryCollector,
    TelemetryEntry,
    TelemetryExporter,
    _derive_key,
    _xor_encrypt,
    _sanitise,
)


# ===========================================================================
# Task 9: Model Verifier & Quarantine Manager
# ===========================================================================


def _write_tmp(data: bytes, suffix: str = ".onnx") -> Path:
    fh = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    fh.write(data)
    fh.close()
    return Path(fh.name)


def _safe_onnx_bytes() -> bytes:
    """Minimal fake ONNX blob that won't trip any suspicious prefix checks."""
    # Embed known-safe op names as proto-style strings with field tag \x0a (field 1, LDelim)
    ops = ["Conv", "Relu", "BatchNormalization", "Reshape"]
    parts = [b"\x08\x07"]  # protobuf varint header
    for op in ops:
        enc = op.encode("ascii")
        parts.append(b"\x0a" + bytes([len(enc)]) + enc)
    return b"".join(parts)


class TestScanOnnxOps(unittest.TestCase):
    def test_finds_known_ops(self):
        data = _safe_onnx_bytes()
        ops = _scan_onnx_ops(data)
        # At least some ops should be found
        found = set(ops) & {"Conv", "Relu", "BatchNormalization", "Reshape"}
        self.assertGreater(len(found), 0)

    def test_empty_bytes(self):
        self.assertEqual(_scan_onnx_ops(b""), [])

    def test_short_bytes(self):
        self.assertEqual(_scan_onnx_ops(b"\x00\x01"), [])


class TestModelVerifier(unittest.TestCase):
    def setUp(self):
        self.verifier = ModelVerifier()

    def test_missing_file_fails(self):
        result = self.verifier.verify(Path("/nonexistent/model.onnx"))
        self.assertFalse(result.passed)
        self.assertIn("not found", result.reason)

    def test_tiny_file_fails(self):
        p = _write_tmp(b"\x00")
        try:
            result = self.verifier.verify(p)
            self.assertFalse(result.passed)
            self.assertIn("small", result.reason)
        finally:
            p.unlink(missing_ok=True)

    def test_safe_model_passes(self):
        p = _write_tmp(_safe_onnx_bytes())
        try:
            result = self.verifier.verify(p)
            # No suspicious prefixes → should pass
            self.assertTrue(result.passed)
            self.assertEqual(result.unsafe_ops, [])
        finally:
            p.unlink(missing_ok=True)

    def test_suspicious_op_fails(self):
        # Embed a custom. prefixed op
        bad_op = b"custom.evil_kernel"
        data = _safe_onnx_bytes() + b"\x0a" + bytes([len(bad_op)]) + bad_op
        p = _write_tmp(data)
        try:
            result = self.verifier.verify(p)
            self.assertFalse(result.passed)
            self.assertTrue(len(result.unsafe_ops) > 0)
            self.assertIn("unsafe", result.reason)
        finally:
            p.unlink(missing_ok=True)

    def test_unknown_op_fails_in_strict_mode(self):
        op = b"NotAWhitelistedOp"
        data = b"\x08\x07" + b"\x0a" + bytes([len(op)]) + op
        result = self.verifier.verify_bytes(data, name="unknown.onnx")
        self.assertFalse(result.passed)
        self.assertIn("NotAWhitelistedOp", result.unsafe_ops)

    def test_sha256_populated(self):
        p = _write_tmp(_safe_onnx_bytes())
        try:
            result = self.verifier.verify(p)
            self.assertEqual(len(result.sha256), 64)
        finally:
            p.unlink(missing_ok=True)

    def test_verify_bytes_safe(self):
        result = self.verifier.verify_bytes(_safe_onnx_bytes(), name="fake.onnx")
        self.assertEqual(result.model_path, "fake.onnx")

    def test_result_to_dict(self):
        result = ModelVerificationResult(
            model_path="/m.onnx", sha256="abc", passed=True,
        )
        d = result.to_dict()
        self.assertIn("model_path", d)
        self.assertIn("passed", d)

    def test_failed_property(self):
        r = ModelVerificationResult(model_path="x", sha256="", passed=False)
        self.assertTrue(r.failed)


class TestQuarantineManager(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.qdir = Path(self._tmp.name) / "quarantine"
        self.qm = QuarantineManager(self.qdir)

    def tearDown(self):
        self._tmp.cleanup()

    def _fake_result(self, sha="deadbeef00" * 6 + "dddd"):
        return ModelVerificationResult(
            model_path="/models/evil.onnx",
            sha256=sha[:64],
            passed=False,
            unsafe_ops=["custom.evil"],
            reason="Unsafe op detected.",
        )

    def test_quarantine_moves_file(self):
        model = Path(self._tmp.name) / "evil.onnx"
        model.write_bytes(_safe_onnx_bytes())
        result = self._fake_result(sha="a" * 64)
        result.sha256 = "a" * 64
        record = self.qm.quarantine(model, result)
        self.assertFalse(model.exists())
        self.assertTrue(Path(record.quarantine_path).exists())

    def test_is_quarantined(self):
        model = Path(self._tmp.name) / "evil2.onnx"
        model.write_bytes(_safe_onnx_bytes())
        result = self._fake_result(sha="b" * 64)
        result.sha256 = "b" * 64
        self.qm.quarantine(model, result)
        self.assertTrue(self.qm.is_quarantined("b" * 64))
        self.assertFalse(self.qm.is_quarantined("c" * 64))

    def test_list_quarantined(self):
        model = Path(self._tmp.name) / "evil3.onnx"
        model.write_bytes(b"\x00" * 16)
        result = self._fake_result(sha="c" * 64)
        result.sha256 = "c" * 64
        self.qm.quarantine(model, result)
        records = self.qm.list_quarantined()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].sha256, "c" * 64)

    def test_release_restores_file(self):
        model = Path(self._tmp.name) / "evil4.onnx"
        model.write_bytes(b"\xff" * 16)
        result = self._fake_result(sha="d" * 64)
        result.sha256 = "d" * 64
        self.qm.quarantine(model, result)
        restore = Path(self._tmp.name) / "restored.onnx"
        rec = self.qm.release("d" * 64, restore)
        self.assertIsNotNone(rec)
        self.assertTrue(restore.exists())
        self.assertFalse(self.qm.is_quarantined("d" * 64))

    def test_index_persisted(self):
        model = Path(self._tmp.name) / "evil5.onnx"
        model.write_bytes(b"\xAB" * 16)
        result = self._fake_result(sha="e" * 64)
        result.sha256 = "e" * 64
        self.qm.quarantine(model, result)
        qm2 = QuarantineManager(self.qdir)
        self.assertTrue(qm2.is_quarantined("e" * 64))

    def test_record_roundtrip(self):
        rec = QuarantineRecord(
            original_path="/m.onnx",
            quarantine_path="/q/m.onnx",
            sha256="f" * 64,
            reason="bad op",
            unsafe_ops=["custom.x"],
        )
        rec2 = QuarantineRecord.from_dict(rec.to_dict())
        self.assertEqual(rec2.sha256, rec.sha256)
        self.assertEqual(rec2.unsafe_ops, ["custom.x"])

    def test_verify_or_quarantine_model_moves_failed_import(self):
        model = Path(self._tmp.name) / "bad.onnx"
        bad_op = b"custom.bad"
        model.write_bytes(b"\x08\x07" + b"\x0a" + bytes([len(bad_op)]) + bad_op)

        result = verify_or_quarantine_model(model, self.qdir)

        self.assertFalse(result.passed)
        self.assertFalse(model.exists())
        self.assertEqual(len(self.qm.list_quarantined()), 0)
        self.assertEqual(len(QuarantineManager(self.qdir).list_quarantined()), 1)


# ===========================================================================
# Task 10: Telemetry Collector & Exporter
# ===========================================================================


class TestXorEncrypt(unittest.TestCase):
    def test_roundtrip(self):
        key = _derive_key("test_passphrase")
        data = b"hello telemetry world"
        enc = _xor_encrypt(data, key)
        dec = _xor_encrypt(enc, key)  # XOR is its own inverse
        self.assertEqual(dec, data)

    def test_encrypted_differs_from_plain(self):
        key = _derive_key("pass")
        data = b"plaintext"
        self.assertNotEqual(_xor_encrypt(data, key), data)


class TestSanitise(unittest.TestCase):
    def test_strips_private_keys(self):
        d = {"fps": 24.0, "input_path": "/secret/video.mp4", "provider": "cuda"}
        clean = _sanitise(d)
        self.assertIn("fps", clean)
        self.assertNotIn("input_path", clean)


class TestTelemetryEntry(unittest.TestCase):
    def test_to_dict_minimal(self):
        e = TelemetryEntry(job_id="j1", provider="cpu")
        d = e.to_dict()
        self.assertEqual(d["job_id"], "j1")
        self.assertNotIn("error", d)
        self.assertNotIn("gpu_temp_c", d)

    def test_to_dict_full(self):
        e = TelemetryEntry(
            job_id="j2", provider="cuda", fps=30.0,
            gpu_temp_c=75.0, memory_mb=4096.0,
            quality={"psnr": 34.5},
            error="oom",
        )
        d = e.to_dict()
        self.assertEqual(d["fps"], 30.0)
        self.assertEqual(d["gpu_temp_c"], 75.0)
        self.assertEqual(d["quality"]["psnr"], 34.5)
        self.assertEqual(d["error"], "oom")

    def test_roundtrip(self):
        e = TelemetryEntry(job_id="j3", provider="coreml", fps=15.5, cpu_temp_c=60.0)
        e2 = TelemetryEntry.from_dict(e.to_dict())
        self.assertEqual(e2.fps, 15.5)
        self.assertEqual(e2.cpu_temp_c, 60.0)

    def test_json_line_single_line(self):
        e = TelemetryEntry(job_id="j4", provider="cpu")
        self.assertNotIn("\n", e.to_json_line())


class TestTelemetryCollector(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tc = TelemetryCollector(Path(self._tmp.name) / "telemetry.ndjson")

    def tearDown(self):
        self._tmp.cleanup()

    def test_record_creates_file(self):
        self.tc.record("j1", provider="cpu", fps=24.0)
        self.assertTrue(self.tc.path.exists())

    def test_all_entries(self):
        self.tc.record("j1", provider="cpu", fps=10.0)
        self.tc.record("j2", provider="cuda", fps=20.0)
        entries = self.tc.all_entries()
        self.assertEqual(len(entries), 2)

    def test_tail_limits(self):
        for i in range(10):
            self.tc.record(f"j{i}", provider="cpu")
        self.assertEqual(len(self.tc.tail(3)), 3)

    def test_for_job(self):
        self.tc.record("j1", provider="cpu")
        self.tc.record("j2", provider="cpu")
        result = self.tc.for_job("j1")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].job_id, "j1")

    def test_errors(self):
        self.tc.record("j1", provider="cpu")
        self.tc.record("j2", provider="cpu", error="timeout")
        errs = self.tc.errors()
        self.assertEqual(len(errs), 1)
        self.assertEqual(errs[0].job_id, "j2")

    def test_summary_empty(self):
        s = self.tc.summary()
        self.assertEqual(s["total_jobs"], 0)

    def test_summary_aggregates(self):
        self.tc.record("j1", provider="cuda", fps=20.0, gpu_temp_c=70.0)
        self.tc.record("j2", provider="cuda", fps=30.0, gpu_temp_c=80.0)
        self.tc.record("j3", provider="cpu", fps=10.0, error="oom")
        s = self.tc.summary()
        self.assertEqual(s["total_jobs"], 3)
        self.assertEqual(s["error_count"], 1)
        self.assertAlmostEqual(s["avg_fps"], 20.0)
        self.assertAlmostEqual(s["avg_gpu_temp_c"], 75.0)
        self.assertEqual(s["providers"]["cuda"], 2)
        self.assertEqual(s["providers"]["cpu"], 1)

    def test_clear(self):
        self.tc.record("j1", provider="cpu")
        self.tc.clear()
        self.assertEqual(self.tc.all_entries(), [])

    def test_private_keys_stripped_in_extra(self):
        self.tc.record("j1", provider="cpu", input_path="/secret.mp4", fps=5.0)
        entries = self.tc.all_entries()
        self.assertNotIn("input_path", entries[0].extra)

    def test_thread_safety(self):
        errors = []

        def _write():
            try:
                for i in range(20):
                    self.tc.record(f"j_{i}", provider="cpu", fps=float(i))
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=_write) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])
        self.assertEqual(len(self.tc.all_entries()), 100)

    def test_subdirectory_auto_created(self):
        tc = TelemetryCollector(
            Path(self._tmp.name) / "nested" / "deep" / "telemetry.ndjson"
        )
        tc.record("j1", provider="cpu")
        self.assertTrue(tc.path.exists())


class TestTelemetryExporter(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tc = TelemetryCollector(Path(self._tmp.name) / "t.ndjson")
        self.tc.record("j1", provider="cuda", fps=25.0, gpu_temp_c=72.0)
        self.tc.record("j2", provider="cpu", fps=5.0, error="oom")
        self.exporter = TelemetryExporter(self.tc)

    def tearDown(self):
        self._tmp.cleanup()

    def test_export_returns_string(self):
        bundle = self.exporter.export("secret_pass")
        self.assertIsInstance(bundle, str)
        self.assertGreater(len(bundle), 0)

    def test_decrypt_roundtrip(self):
        bundle = self.exporter.export("my_pass")
        payload = TelemetryExporter.decrypt(bundle, "my_pass")
        self.assertIn("entries", payload)
        self.assertIn("summary", payload)
        self.assertEqual(len(payload["entries"]), 2)

    def test_wrong_passphrase_corrupts_data(self):
        bundle = self.exporter.export("correct_pass")
        with self.assertRaises(Exception):
            TelemetryExporter.decrypt(bundle, "wrong_pass")

    def test_exclude_errors(self):
        bundle = self.exporter.export("pass", include_errors=False)
        payload = TelemetryExporter.decrypt(bundle, "pass")
        for e in payload["entries"]:
            self.assertIsNone(e.get("error"))

    def test_notes_in_bundle(self):
        bundle = self.exporter.export("pass", notes="diagnostic run v1")
        payload = TelemetryExporter.decrypt(bundle, "pass")
        self.assertEqual(payload["notes"], "diagnostic run v1")

    def test_export_to_file(self):
        out = Path(self._tmp.name) / "bundle.enc"
        self.exporter.export_to_file(out, "pass123")
        self.assertTrue(out.exists())
        payload = TelemetryExporter.decrypt(out.read_text("ascii"), "pass123")
        self.assertIn("entries", payload)

    def test_summary_in_bundle(self):
        bundle = self.exporter.export("p")
        payload = TelemetryExporter.decrypt(bundle, "p")
        self.assertEqual(payload["summary"]["total_jobs"], 2)


if __name__ == "__main__":
    unittest.main()
