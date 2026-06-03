# Model Packaging & First-Run Setup

This document details the layout format of model bundles and the offline import/first-run setup workflows in `silukman_video_enhancer`.

---

## 1. Overview & Purpose

To maintain the application's strict offline capability, users must be able to import AI models without internet connections. 

The model packaging helper (`models/package.py`) and setup utility (`models/setup.py`) manage the offline import, installation, and deployment of model bundles.

---

## 2. Model Package Format

Model bundles are packaged in a versioned local format. A standard model package (e.g., `model-realesrgan-x2.pkg`) contains:
*   **Model Binary**: The raw, optimized `.onnx` model file.
*   **Sidecar Manifest**: A JSON metadata file defining:
    *   Scale factor (e.g. 2, 4).
    *   Minimum application version requirement.
    *   SHA256 signature to guarantee bundle integrity.
    *   Execution provider restrictions.

---

## 3. Offline Import & First-Run Workflow

When the desktop GUI or CLI is launched for the first time:

```text
Application Launch
       │
       ▼ [Check Cache]
Are models present in local cache?
  ├──► YES ──► Continue Launch
  └──► NO  ──► Launch Setup Utility
                 │
                 ▼
       Choose Import Option:
        * Select local .pkg file
        * Verify SHA256 signature
        * Unpack and register in Cache Folder
```

1.  **Registry Scan**: The setup manager checks the local cache.
2.  **User Import**: If missing, the user is prompted to supply a local package or directory path.
3.  **SHA256 Check & Unpack**: The system validates the signature, copies the files to the cache folder, and registers the imported metadata dynamically.

---

## 4. Verification

The setup utility, offline model setup checks, and package manifest importing are covered by unit tests:

```bash
python3 -m unittest tests.test_phase4_completion
python3 -m unittest tests.test_phase5_completion
```
Tests ensure that the manifest checks reject outdated bundles and that directory operations function correctly on multiple platforms.
