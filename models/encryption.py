"""Offline model encryption helpers."""

from __future__ import annotations

import hashlib
from pathlib import Path


def derive_key(secret: str) -> bytes:
    return hashlib.sha256(secret.encode("utf-8")).digest()


def encrypt_bytes(payload: bytes, secret: str) -> bytes:
    key = derive_key(secret)
    return bytes(value ^ key[index % len(key)] for index, value in enumerate(payload))


def decrypt_bytes(payload: bytes, secret: str) -> bytes:
    return encrypt_bytes(payload, secret)


def encrypt_model_file(input_path: Path, output_path: Path, secret: str) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(encrypt_bytes(input_path.read_bytes(), secret))
    return output_path
