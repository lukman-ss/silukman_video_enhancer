# Model Registry, Discovery & Security

This document details how deep learning models are registered, verified, hot-swapped, and protected in `silukman_video_enhancer`.

---

## 1. Overview & Purpose

To ensure reliable, safe execution of AI models locally, the application incorporates a decoupled registry and verification system. This handles:
*   Standard pre-registered model execution.
*   Secure verification via SHA256 hashes.
*   Dynamic drop-in scanning for user/community models.
*   Intellectual property copy-protection via model file encryption.

---

## 2. Model Registry & Verification

The core registry (`models/registry.py`) maintains a database of officially supported models. Each model contains metadata indicating its URL (for online reference), size, resolution scale, and expected SHA256 checksum:

```python
model_entry = {
    "name": "realesrgan-x2",
    "scale": 2,
    "sha256": "8f3c71a...",
    "filename": "realesrgan_x2.onnx"
}
```

When a job is initialized, the registry checks the local model cache. Before parsing the file:
1.  **Verify**: The engine calculates the SHA256 checksum of the target `.onnx` file.
2.  **Assert**: If the checksum does not match the registry value, the runner rejects the model as corrupted or tampered with.

---

## 3. Custom Model Discovery & Hot-Swapping

To support community models, the discovery subsystem (`models/discovery.py`) scans user cache folders for drop-in `.onnx` assets:
*   **Auto-Scan**: Scans target directories (e.g. `~/.cache/silukman/models/`) on startup.
*   **Dynamic Registration**: Discovered models are matched with sidecar JSON configuration files defining scale and channels, and dynamically merged into the active model registry without editing code.

---

## 4. Model Bytes Encryption

To protect custom-trained model IP, the engine supports **Offline Model Encryption** (`models/encryption.py`):
*   Models are encrypted on disk using AES or custom-key byte shifts.
*   During pipeline execution, models are decrypted directly into memory bytes rather than being written to temporary disk files, preventing unauthorized cloning.

---

## 5. Verification

The registry verification, discovery scanning, and model decryption helpers are verified in:

```bash
python3 -m unittest tests.test_phase1_completion
python3 -m unittest tests.test_phase3_completion
```
