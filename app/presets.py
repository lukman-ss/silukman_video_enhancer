"""Encrypted local preset sync helpers."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from app.config import EnhancementConfig
from models.encryption import decrypt_bytes, encrypt_bytes


def export_encrypted_preset(
    config: EnhancementConfig,
    output_path: Path,
    secret: str,
) -> Path:
    """Write an encrypted enhancement preset for local sync or backup."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        key: str(value) if isinstance(value, Path) else value
        for key, value in asdict(config).items()
    }
    output_path.write_bytes(encrypt_bytes(json.dumps(payload, sort_keys=True).encode("utf-8"), secret))
    return output_path


def import_encrypted_preset(input_path: Path, secret: str) -> EnhancementConfig:
    """Read an encrypted enhancement preset and restore shared config."""

    payload = json.loads(decrypt_bytes(input_path.read_bytes(), secret).decode("utf-8"))
    return _config_from_payload(payload)


def sync_encrypted_preset(source_path: Path, sync_dir: Path) -> Path:
    """Copy an encrypted preset into a local sync folder."""

    if not source_path.exists():
        raise ValueError(f"Preset does not exist: {source_path}")
    sync_dir.mkdir(parents=True, exist_ok=True)
    destination = sync_dir / source_path.name
    destination.write_bytes(source_path.read_bytes())
    return destination


def _config_from_payload(payload: dict[str, Any]) -> EnhancementConfig:
    return EnhancementConfig(
        input_path=Path(payload["input_path"]),
        output_path=Path(payload["output_path"]),
        model=payload.get("model", "realesrgan"),
        scale=int(payload.get("scale", 2)),
        device=payload.get("device", "auto"),
        crf=int(payload.get("crf", 18)),
        denoise=bool(payload.get("denoise", False)),
        color_correct=bool(payload.get("color_correct", False)),
        audio_restore=bool(payload.get("audio_restore", False)),
        preserve_metadata=bool(payload.get("preserve_metadata", True)),
        quiet=bool(payload.get("quiet", False)),
        benchmark=bool(payload.get("benchmark", False)),
        batch=bool(payload.get("batch", False)),
        model_chain=tuple(payload.get("model_chain", ())),
        roi=tuple(payload["roi"]) if payload.get("roi") else None,
        fp16=bool(payload.get("fp16", False)),
        destinations=tuple(payload.get("destinations", ())),
        face_model=payload.get("face_model"),
        dynamic_scale=bool(payload.get("dynamic_scale", False)),
        async_workers=int(payload.get("async_workers", 1)),
        checkpoint_dir=Path(payload["checkpoint_dir"]) if payload.get("checkpoint_dir") else None,
        worker_devices=tuple(payload.get("worker_devices", ())),
        restoration_ops=tuple(payload.get("restoration_ops", ())),
        target_fps=float(payload["target_fps"]) if payload.get("target_fps") else None,
    )
