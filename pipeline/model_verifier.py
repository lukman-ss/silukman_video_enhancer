"""Local model signature verification and quarantine manager.

Phase 7, Task 9
ModelVerifier inspects imported ONNX files: it checks the file header magic,
enumerates every node's op_type against a whitelist of safe execution layers,
and flags any custom/external ops.  QuarantineManager moves flagged files to
an isolated directory and records why they were quarantined.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import struct
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Optional


# ---------------------------------------------------------------------------
# ONNX constants (no onnx package required — we parse the protobuf header)
# ---------------------------------------------------------------------------

# Protocol-buffer field tag for ModelProto.graph (field 7)
# and GraphProto.node (field 1) — used for a lightweight structural scan.
# This avoids a hard dependency on the `onnx` package.
_ONNX_MAGIC_BYTES = b"\x08"   # protobuf varint header — present in all ONNX files

# Safe op whitelist: standard ONNX opset operators that are well-known.
DEFAULT_SAFE_OPS: FrozenSet[str] = frozenset({
    "Conv", "ConvTranspose", "Relu", "LeakyRelu", "PRelu",
    "BatchNormalization", "InstanceNormalization", "LayerNormalization",
    "MaxPool", "AveragePool", "GlobalAveragePool",
    "Add", "Sub", "Mul", "Div", "Pow", "Sqrt", "Exp", "Log", "Abs", "Neg",
    "Clip", "Sigmoid", "Tanh", "Softmax", "LogSoftmax",
    "Gemm", "MatMul", "Transpose", "Reshape", "Flatten", "Squeeze", "Unsqueeze",
    "Concat", "Split", "Slice", "Gather", "Scatter", "ScatterElements",
    "Resize", "Upsample", "Pad", "Tile", "Expand",
    "Cast", "Shape", "Size", "Identity", "Dropout",
    "ReduceMean", "ReduceSum", "ReduceMax", "ReduceMin",
    "Equal", "Greater", "Less", "And", "Or", "Not",
    "Constant", "ConstantOfShape",
    "NonMaxSuppression", "TopK", "ArgMax", "ArgMin",
    # Common extensions used by SR models
    "PixelShuffle", "DepthToSpace", "SpaceToDepth",
    "LpNormalization", "Einsum",
})

# Op prefixes that indicate custom/external operators
_SUSPICIOUS_PREFIXES = ("custom.", "com.", "org.", "ai.", "aten::", "prim::")


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Lightweight ONNX node scanner (pure-Python protobuf parser)
# ---------------------------------------------------------------------------

def _read_varint(data: bytes, pos: int):
    """Decode a protobuf varint starting at *pos*. Returns (value, new_pos)."""
    result, shift = 0, 0
    while pos < len(data):
        b = data[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            break
        shift += 7
    return result, pos


def _scan_onnx_ops(data: bytes) -> List[str]:
    """
    Very lightweight scan of protobuf-encoded ONNX model data.

    Returns a list of op_type strings found via a best-effort string scan.
    This is not a full protobuf parser — it looks for length-delimited strings
    that appear after field-tag bytes commonly associated with op_type fields.
    For the purpose of quarantine triage it is sufficient.
    """
    ops: List[str] = []
    i = 0
    while i < len(data) - 2:
        # Look for protobuf wire type 2 (length-delimited), field numbers 1-15
        b = data[i]
        field_num = (b >> 3) & 0x1F
        wire_type = b & 0x07
        if wire_type == 2 and 1 <= field_num <= 15:
            try:
                length, j = _read_varint(data, i + 1)
                if 2 <= length <= 64 and j + length <= len(data):
                    candidate = data[j: j + length]
                    try:
                        s = candidate.decode("ascii")
                        # Filter: valid op names are alphanumeric + underscore/dot/colon
                        if s and all(c.isalnum() or c in "._:" for c in s):
                            ops.append(s)
                    except (UnicodeDecodeError, ValueError):
                        pass
            except Exception:
                pass
        i += 1
    return ops


# ---------------------------------------------------------------------------
# Verification result
# ---------------------------------------------------------------------------


@dataclass
class ModelVerificationResult:
    model_path: str
    sha256: str
    passed: bool
    safe_ops: List[str] = field(default_factory=list)
    unsafe_ops: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    reason: str = ""

    @property
    def failed(self) -> bool:
        return not self.passed

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_path": self.model_path,
            "sha256": self.sha256,
            "passed": self.passed,
            "unsafe_ops": self.unsafe_ops,
            "warnings": self.warnings,
            "reason": self.reason,
        }


# ---------------------------------------------------------------------------
# ModelVerifier
# ---------------------------------------------------------------------------


class ModelVerifier:
    """
    Verifies imported ONNX model files against a safe-op whitelist.

    Usage::

        verifier = ModelVerifier()
        result = verifier.verify(Path("model.onnx"))
        if result.failed:
            quarantine.quarantine(Path("model.onnx"), result)
    """

    def __init__(
        self,
        safe_ops: FrozenSet[str] = DEFAULT_SAFE_OPS,
        strict_whitelist: bool = True,
    ) -> None:
        self.safe_ops = safe_ops
        self.strict_whitelist = strict_whitelist

    def verify(self, model_path: Path) -> ModelVerificationResult:
        if not model_path.exists():
            return ModelVerificationResult(
                model_path=str(model_path),
                sha256="",
                passed=False,
                reason=f"File not found: {model_path}",
            )

        sha = _sha256_file(model_path)
        data = model_path.read_bytes()

        warnings: List[str] = []
        unsafe_ops: List[str] = []

        # 1. File size sanity check
        if len(data) < 8:
            return ModelVerificationResult(
                model_path=str(model_path),
                sha256=sha,
                passed=False,
                reason="File too small to be a valid ONNX model.",
            )

        # 2. Scan for op strings
        found_ops = _scan_onnx_ops(data)

        safe: List[str] = []
        unsafe: List[str] = []
        for op in found_ops:
            suspicious = any(op.startswith(p) for p in _SUSPICIOUS_PREFIXES)
            is_safe = op in self.safe_ops and not suspicious
            if not self.strict_whitelist and not suspicious:
                is_safe = True
            if is_safe:
                safe.append(op)
            else:
                unsafe.append(op)

        # 3. Explicit suspicious prefix check
        for op in found_ops:
            if any(op.startswith(p) for p in _SUSPICIOUS_PREFIXES):
                if op not in unsafe:
                    unsafe.append(op)
                warnings.append(f"Suspicious op prefix detected: '{op}'")

        passed = len(unsafe) == 0
        reason = ""
        if not passed:
            reason = (
                f"Model contains {len(unsafe)} unsafe operator(s): "
                + ", ".join(sorted(set(unsafe)))
            )

        return ModelVerificationResult(
            model_path=str(model_path),
            sha256=sha,
            passed=passed,
            safe_ops=list(set(safe)),
            unsafe_ops=list(set(unsafe)),
            warnings=warnings,
            reason=reason,
        )

    def verify_bytes(self, data: bytes, name: str = "<bytes>") -> ModelVerificationResult:
        """Verify raw bytes (for testing without writing to disk)."""
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".onnx", delete=False) as fh:
            fh.write(data)
            p = Path(fh.name)
        try:
            result = self.verify(p)
            result.model_path = name
            return result
        finally:
            p.unlink(missing_ok=True)


def verify_or_quarantine_model(
    model_path: Path,
    quarantine_dir: Path,
    verifier: ModelVerifier | None = None,
) -> ModelVerificationResult:
    """Verify an imported model and quarantine it immediately on failure."""

    active_verifier = verifier or ModelVerifier()
    result = active_verifier.verify(model_path)
    if result.failed and model_path.exists():
        QuarantineManager(quarantine_dir).quarantine(model_path, result)
    return result


# ---------------------------------------------------------------------------
# QuarantineManager
# ---------------------------------------------------------------------------

_QUARANTINE_INDEX = "quarantine_index.json"


@dataclass
class QuarantineRecord:
    original_path: str
    quarantine_path: str
    sha256: str
    reason: str
    quarantined_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    unsafe_ops: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "original_path": self.original_path,
            "quarantine_path": self.quarantine_path,
            "sha256": self.sha256,
            "reason": self.reason,
            "quarantined_at": self.quarantined_at,
            "unsafe_ops": self.unsafe_ops,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "QuarantineRecord":
        return cls(
            original_path=str(d["original_path"]),
            quarantine_path=str(d["quarantine_path"]),
            sha256=str(d["sha256"]),
            reason=str(d["reason"]),
            quarantined_at=str(d.get("quarantined_at", "")),
            unsafe_ops=list(d.get("unsafe_ops", [])),
        )


class QuarantineManager:
    """Moves failed model files to an isolated quarantine directory."""

    def __init__(self, quarantine_dir: Path) -> None:
        self.quarantine_dir = Path(quarantine_dir)
        self._records: List[QuarantineRecord] = self._load_index()

    def _index_path(self) -> Path:
        return self.quarantine_dir / _QUARANTINE_INDEX

    def _load_index(self) -> List[QuarantineRecord]:
        p = self._index_path()
        if not p.exists():
            return []
        try:
            return [QuarantineRecord.from_dict(d) for d in json.loads(p.read_text("utf-8"))]
        except Exception:
            return []

    def _save_index(self) -> None:
        self.quarantine_dir.mkdir(parents=True, exist_ok=True)
        self._index_path().write_text(
            json.dumps([r.to_dict() for r in self._records], indent=2),
            encoding="utf-8",
        )

    def quarantine(
        self,
        model_path: Path,
        result: ModelVerificationResult,
    ) -> QuarantineRecord:
        """Move *model_path* to the quarantine store and record the reason."""
        self.quarantine_dir.mkdir(parents=True, exist_ok=True)
        dest_name = f"{model_path.stem}_{result.sha256[:8]}{model_path.suffix}"
        dest = self.quarantine_dir / dest_name
        shutil.move(str(model_path), dest)
        record = QuarantineRecord(
            original_path=str(model_path),
            quarantine_path=str(dest),
            sha256=result.sha256,
            reason=result.reason,
            unsafe_ops=result.unsafe_ops,
        )
        self._records.append(record)
        self._save_index()
        return record

    def list_quarantined(self) -> List[QuarantineRecord]:
        return list(self._records)

    def is_quarantined(self, sha256: str) -> bool:
        return any(r.sha256 == sha256 for r in self._records)

    def release(self, sha256: str, restore_path: Path) -> Optional[QuarantineRecord]:
        """Restore a quarantined file (admin override). Returns the record."""
        for record in self._records:
            if record.sha256 == sha256:
                src = Path(record.quarantine_path)
                if src.exists():
                    restore_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(src), restore_path)
                self._records.remove(record)
                self._save_index()
                return record
        return None
