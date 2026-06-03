# Build and Packaging Guide

This document describes how to compile the application from source code and bundle it for offline redistribution.

---

## Build Requirements

To pack this application for standalone installations, you will need:

*   Python 3.9+
*   `pip` & `virtualenv`
*   PyInstaller
*   PySide6 / Qt runtime libraries for desktop builds
*   FFmpeg binaries (targeted for the specific host platform)

---

## Development Setup

For local developer installations:
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

---

## Packaging Process

Because the app is intended to run offline without external Python dependencies, we plan to package both the CLI and Python desktop UI using PyInstaller:

```bash
pyinstaller --clean --onefile --add-binary "bin/ffmpeg:bin" main.py
```

### Included Binaries:
*   **FFmpeg**: Bundled directly within the build package to remove the need for system-wide FFmpeg installations by the user.
*   **PySide6 / Qt Runtime**: Bundled for the desktop UI build.
*   **ONNX Runtime Shared Libraries**: Engine binaries compiled for GPU execution.
*   *Note: Model `.onnx` files are excluded from the core executable payload to keep installer download sizes reasonable. They will download dynamically during first-run initialization or can be imported manually.*

---

## Release Asset Naming

Tagged release artifacts must use the following names:

*   `silukman-video-enhancer-vX.Y.Z-windows-x64.exe`
*   `silukman-video-enhancer-desktop-vX.Y.Z-windows-x64.exe`
*   `silukman-video-enhancer-vX.Y.Z-macos-arm64.dmg`
*   `silukman-video-enhancer-vX.Y.Z-linux-x86_64.deb`
*   `silukman-video-enhancer-vX.Y.Z-linux-x86_64.AppImage`

The GitHub Actions release workflow derives `vX.Y.Z` from the pushed tag or from `[project].version` in `pyproject.toml` during manual dry runs.

---

## GitHub Release and Package Publication

Phase 10 release automation publishes:

* Draft GitHub Releases with notes extracted from `CHANGELOG.md`.
* Installer artifacts from the Windows, macOS, and Linux release jobs.
* Python source and wheel distributions as workflow artifacts, tagged release assets, and published to PyPI through the package publish workflow.
