# Containerized Headless Deployment (Docker & Podman)

This document provides instructions for containerizing, configuring, and deploying `silukman_video_enhancer` headless REST services and render nodes using Docker or Podman.

---

## 1. Overview & Purpose

For server environments, headless rendering workstations, or cluster-based LAN render farms, running applications inside isolated containers ensures predictable execution, consistent FFmpeg runtimes, and straightforward scaling.

The compilation tools generate a pre-configured `Containerfile` or `Dockerfile` optimized for local execution.

---

## 2. Base Container Image & Dependencies

The generated container configuration utilizes a multi-stage or optimized GPU base image:
*   **Base Image**: Ubuntu or Debian-based images containing matching Python 3.9+ environments.
*   **FFmpeg Setup**: Installs static static builds with all necessary audio-video filters.
*   **Execution Providers**: Bundles required libraries (such as CUDA Toolkit/cuDNN components if GPU acceleration is required).

---

## 3. Building the Container Image

Build the container locally using Docker or Podman:

```bash
# Using Docker
docker build -t silukman-service -f tools/Containerfile .

# Using Podman
podman build -t silukman-service -f tools/Containerfile .
```

---

## 4. Running the Container with GPU Acceleration

To expose local hardware accelerators (NVIDIA GPUs) inside the container:

### NVIDIA GPU Passthrough (Docker)
Ensure the **NVIDIA Container Toolkit** is installed on the host machine, then run:
```bash
docker run -d \
  --name silukman-node \
  --gpus all \
  -p 8000:8000 \
  -v ~/.cache/silukman/models:/root/.cache/silukman/models \
  silukman-service
```

### Podman GPU Passthrough
```bash
podman run -d \
  --name silukman-node \
  --device nvidia.com/gpu=all \
  -p 8000:8000 \
  -v ~/.cache/silukman/models:/root/.cache/silukman/models \
  silukman-service
```

---

## 5. Verification

The generated container recipe file and port mappings are verified in:

```bash
python3 -m unittest tests.test_phase6_completion
```
Tests check that the container configuration utility outputs valid Dockerfile/Containerfile syntaxes.
