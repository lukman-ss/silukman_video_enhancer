# Developer Setup & Contribution Guide

This document provides instructions for developers setting up their local workspace, installing native dependencies, running tests, and contributing to `silukman_video_enhancer`.

---

## 1. Prerequisites

Before setting up the environment, ensure you have the following installed on your machine:
*   **Python**: Version 3.9 or higher.
*   **FFmpeg**: Static binaries compiled with support for key filters (`lut3d`, `afftdn`, `signalstats`, `concat`). If not present in the system `PATH`, the application will automatically download static binaries to the local `bin/` directory.
*   **Git**: For version control.

---

## 2. Environment Setup

1.  **Clone the Repository**:
    ```bash
    git clone https://github.com/username/silukman_video_enhancer.git
    cd silukman_video_enhancer
    ```

2.  **Create a Virtual Environment**:
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate  # On Windows use: .venv\Scripts\activate
    ```

3.  **Install Dependencies**:
    Upgrade `pip` first (required to support modern PEP 517 editable installations via `pyproject.toml`), then install requirements. Use the `--no-compile` flag to avoid syntax compilation errors with `PySide6` package template files:
    ```bash
    pip install --upgrade pip
    pip install --no-compile -r requirements.txt -e ".[onnx,dev]"
    ```

---

## 3. Configuring Hardware Accelerators

To enable hardware-accelerated ONNX Runtime execution providers:
*   **NVIDIA CUDA**: Ensure CUDA Toolkit 11.x/12.x and cuDNN are installed, then install:
    ```bash
    pip install onnxruntime-gpu
    ```
*   **Intel OpenVINO**: Install the OpenVINO execution provider package.
*   **Apple Silicon**: CoreML support is enabled natively by default on macOS installations.

---

## 4. Running Verification Tests

The project uses Python's standard `unittest` framework. Ensure all tests pass before submitting changes:

```bash
# Run all tests
python3 -m unittest

# Run with verbose output
python3 -m unittest -v
```

---

## 5. Coding Standards & Linting

We enforce strict formatting rules. Run `ruff` to scan for style violations:

```bash
# Run the linter
ruff check .

# Automatically fix style violations
ruff check --fix .
```
All pull requests must pass the linting checks and the complete unit test suite.
