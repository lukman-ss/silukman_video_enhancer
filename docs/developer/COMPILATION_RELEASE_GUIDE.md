# Compilation, Release & QA Automation

This document explains the packaging pipelines, native installer builds, container profiles, and automated QA smoke testing in `silukman_video_enhancer`.

---

## 1. Overview & Purpose

To package a Python-based PySide6 and ONNX application for distribution to end-users without requiring Python installation, the project incorporates:
*   PyInstaller offline compilation.
*   Platform-specific installer generation (.exe, .dmg, .deb).
*   Headless container profile generator.
*   Production QA automated smoke testing.

These tools are implemented in the `tools/` directory.

---

## 2. PyInstaller Offline Compiler

The compilation wrapper (`tools/pyinstaller_spec.py`) configures and executes PyInstaller:
*   **Asset Bundling**: Bundles native FFmpeg binaries, PySide6 Qt libraries, and ONNX Runtime execution provider DLLs.
*   **Specification Planner**: Configures binary dependencies, path mappings, and icon resources to output a single-file executable.

---

## 3. Platform Installer Workflows

Native installer helpers plan and execute compilation commands:
*   **Windows**: Packages compiled executables into `.exe` installers.
*   **macOS**: Wraps executables in a `.app` bundle and generates native `.dmg` disk images.
*   **Linux**: Generates Debian packages (`.deb`) for standard distribution.

---

## 4. Containerized Headless Profile

For headless deployment in server or render node clusters, `tools/container_profile.py` generates container files:
*   **FFmpeg-ready**: Configures a Debian/Ubuntu-based image with FFmpeg.
*   **ONNX Runtime Setup**: Installs CPU/CUDA libraries.
*   **Expose Port**: Configures the REST API daemon to run on container launch.

---

## 5. QA Smoke Testing

To guarantee packaged build stability, `tools/qa_smoke.py` automates verification:
*   **Dry-Run**: Launches the generated executable with the `--help` and `--dry-run` CLI flags.
*   **Status Code Validation**: Verifies that the exit code is 0 and parses stdout to ensure all core modules are loaded correctly.

---

## 6. Verification

The compilation arguments, installer plans, container file generators, and QA smoke checks are verified in:

```bash
python3 -m unittest tests.test_phase3_completion
python3 -m unittest tests.test_phase4_completion
```
