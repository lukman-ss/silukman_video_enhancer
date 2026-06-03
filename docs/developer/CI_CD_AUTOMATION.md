# CI/CD Automated Pipelines

This document outlines the Continuous Integration and Continuous Deployment (CI/CD) workflows used for testing, building installers, and generating container images.

---

## 1. Overview & Purpose

To ensure code quality and build reliability, the project relies on GitHub Actions pipelines for test validation and installer packaging. The automation pipeline executes:
1.  **Regression Testing**: Runs the complete unit test suite across Windows, macOS, and Linux runners for Python 3.9, 3.10, and 3.11.
2.  **Version Tagging**: Reads `[project].version` from `pyproject.toml`, creates a `vX.Y.Z` tag on `main` version bumps, and lets the tag trigger release builds.
3.  **Compilation & Packaging**: Triggers PyInstaller builds to produce offline installers for Windows, macOS, and Linux.
4.  **Packaged Smoke Tests**: Runs packaged CLI `--help` and `enhance ... --dry-run` checks before artifact upload.
5.  **Code Signing**: Signs Windows executables with Authenticode and macOS executables with hardened-runtime Developer ID signatures when release secrets are configured.
6.  **Native Distribution Artifacts**: Produces Windows one-file executables, a notarized macOS DMG, and Linux `.deb` and AppImage artifacts, then publishes them to a draft GitHub Release.
7.  **Dependency Caching**: Caches pip wheels, `.venv`, and PyInstaller build directories to reduce CI runtime.

---

## 2. Automated Pipeline Workflow

```text
Commit Push / Pull Request / Tag Release
       │
       ▼
 ┌───────────────┐
 │ Run Unit Tests│ ──► (python -m unittest on Linux, Windows, macOS for Python 3.9-3.11)
 └───────┬───────┘
         │
         ▼
 ┌───────────────┐
 │ Version Tag   │ ──► (pyproject.toml version bumps create vX.Y.Z)
 └───────┬───────┘
         │
         ▼
 ┌───────────────┐
 │ Package Build │ ──► (PyInstaller one-file CLI and desktop executables)
 └───────┬───────┘
         │
         ▼
 ┌───────────────┐
 │ Smoke Test    │ ──► (--help and --dry-run on packaged CLI)
 └───────┬───────┘
         │
         ▼
 ┌───────────────┐
 │ Sign & Verify │ ──► (signtool, codesign, notarytool, spctl)
 └───────┬───────┘
         │
         ▼
 ┌───────────────┐
 │ Upload Artifacts │ ──► (.exe, .dmg, .deb, AppImage)
 └───────┬───────┘
         │
         ▼
 ┌───────────────┐
 │ Draft Release │ ──► (release notes from CHANGELOG.md)
 └───────────────┘
```

---

## 3. Runner Architecture

Due to the deep learning dependencies, the CI/CD execution pipeline uses specific runners:
*   **CPU Runners**: Standard GitHub Actions or GitLab runners execute baseline formatting and non-accelerated tests.
*   **GPU Runners**: Dedicated self-hosted runners equipped with GPUs execute CUDA/ONNX smoke tests to ensure execution providers are correctly integrated.
*   **Release Runners**: `windows-latest`, `macos-latest`, and `ubuntu-latest` build platform-native artifacts with bundled FFmpeg, PySide6, and ONNX Runtime assets.

---

## 4. Signing Secrets

Tagged release builds fail early if required signing credentials are missing.

Windows secrets:
*   `WINDOWS_SIGNING_CERTIFICATE_BASE64`
*   `WINDOWS_SIGNING_PASSWORD`

macOS secrets:
*   `MACOS_SIGNING_CERTIFICATE_BASE64`
*   `MACOS_SIGNING_PASSWORD`
*   `MACOS_DEVELOPER_ID_APPLICATION`
*   `MACOS_NOTARY_APPLE_ID`
*   `MACOS_NOTARY_PASSWORD`
*   `MACOS_NOTARY_TEAM_ID`

---

## 5. Verification

Automation specifications, release planners, and package outputs are covered by the unit testing framework:

```bash
python -m unittest tests.test_phase9_ci_workflows
```
Tests verify that CI matrices, release jobs, package artifacts, signing validation, notarization, and signing documentation remain wired into the workflows.
