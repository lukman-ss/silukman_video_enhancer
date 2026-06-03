# Documentation Guide & Overview

Welcome to the documentation folder for `silukman_video_enhancer`. This directory contains the technical design, roadmap, workflows, and specifications that guide the development of this local-first video enhancer, organized into clean categories.

---

## 1. Document Index & Metadata

Below is the directory map detailing the target audience, priority, and purpose of each document in this folder:

| File | Purpose | Priority | Target Audience |
| :--- | :--- | :--- | :--- |
| **Product Documentation** | | | |
| [PROJECT_OVERVIEW.md](product/PROJECT_OVERVIEW.md) | Visi produk, tujuan utama, dan target pengguna. | **P1 (High)** | Users, Contributors |
| [ROADMAP.md](product/ROADMAP.md) | Garis waktu rilis dan target jangka pendek/panjang. | **P1 (High)** | All |
| [IMPLEMENTATION_STATUS.md](product/IMPLEMENTATION_STATUS.md) | Phase-level implementation state and current completion boundary. | **P1 (High)** | Developers, Maintainers |
| [IMPLEMENTATION_CHECKLIST.md](product/IMPLEMENTATION_CHECKLIST.md) | Checklist of completed and pending development tasks. | **P1 (High)** | Developers, Maintainers |
| [IDEAS_AND_RESEARCH.md](product/IDEAS_AND_RESEARCH.md) | Kumpulan ide inovatif dan riset pengoptimalan masa depan. | **P3 (Low)** | All |
| [GLOSSARY.md](product/GLOSSARY.md) | Glossary of terms, AI definitions, and metric abbreviations. | **P3 (Low)** | All |
| **Architecture Documentation** | | | |
| [ARCHITECTURE.md](architecture/ARCHITECTURE.md) | Desain modular sistem dan interaksi komponen. | **P1 (High)** | Developers, Maintainers |
| *Core Video Pipeline* | | | |
| [VIDEO_PIPELINE.md](architecture/pipeline/VIDEO_PIPELINE.md) | Detail teknis pemrosesan frame demi frame dan audio. | **P1 (High)** | Developers |
| [CHECKPOINT_RESUME_SYSTEM.md](architecture/pipeline/CHECKPOINT_RESUME_SYSTEM.md) | ZSTD/LZ4 frame cache and pipeline pause/resume checkpoint system. | **P2 (Medium)** | Developers, Maintainers |
| [AUDIO_RESTORATION_PIPELINE.md](architecture/pipeline/AUDIO_RESTORATION_PIPELINE.md) | FFT noise reduction and stream muxing steps. | **P2 (Medium)** | Developers, Maintainers |
| [METADATA_CHAPTER_PRESERVATION.md](architecture/pipeline/METADATA_CHAPTER_PRESERVATION.md) | Copying and mapping chapters and subtitle attachments. | **P2 (Medium)** | Developers, Maintainers |
| [VRAM_LIMIT_DETECTION.md](architecture/pipeline/VRAM_LIMIT_DETECTION.md) | GPU memory detection, tiling grid, and feathered blending. | **P2 (Medium)** | Developers, Maintainers |
| [TEMPORAL_SCENE_CUT.md](architecture/pipeline/TEMPORAL_SCENE_CUT.md) | Scene transition check boundaries and duplicate skipping. | **P2 (Medium)** | Developers, Maintainers |
| *AI & Model Toolchain* | | | |
| [MODELS_AND_INFERENCE.md](architecture/models/MODELS_AND_INFERENCE.md) | Model AI yang didukung dan runtime execution provider. | **P1 (High)** | Developers, Contributors |
| [ADVANCED_MEDIA_RUNTIME.md](architecture/models/ADVANCED_MEDIA_RUNTIME.md) | Phase 5 runtime, HDR/color, delivery preset, encoder, tiling, and model toolchain details. | **P2 (Medium)** | Developers, Maintainers |
| [NPU_ACCELERATION.md](architecture/models/NPU_ACCELERATION.md) | Intel OpenVINO and Qualcomm QNN NPU optimizations and fallbacks. | **P2 (Medium)** | Developers, Maintainers |
| [FACE_RESTORATION_CHAINING.md](architecture/models/FACE_RESTORATION_CHAINING.md) | Face restoration crop/blend and sequential multi-model chaining. | **P2 (Medium)** | Developers, Maintainers |
| [RIFE_FRAME_INTERPOLATION.md](architecture/models/RIFE_FRAME_INTERPOLATION.md) | RIFE temporal frame interpolation and slow-motion. | **P2 (Medium)** | Users, Developers |
| [SUBTITLE_OCR_TRANSLATION.md](architecture/models/SUBTITLE_OCR_TRANSLATION.md) | Subtitle OCR frame extraction and offline translation adapter. | **P2 (Medium)** | Users, Developers |
| [MODEL_SECURITY_REGISTRY.md](architecture/models/MODEL_SECURITY_REGISTRY.md) | Model registration, SHA256 verification, and discovery. | **P2 (Medium)** | Developers, Maintainers |
| [MODEL_OPTIMIZATION_VALIDATION.md](architecture/models/MODEL_OPTIMIZATION_VALIDATION.md) | Model validation structure, FP16/INT8, and distillation. | **P2 (Medium)** | Developers, Maintainers |
| [MODEL_PACKAGING_SETUP.md](architecture/models/MODEL_PACKAGING_SETUP.md) | Offline model packaging formats and setup guides. | **P2 (Medium)** | Users, Developers |
| [CUSTOM_MODEL_GUIDE.md](architecture/models/CUSTOM_MODEL_GUIDE.md) | Guide for PyTorch-to-ONNX conversions and metadata sidecars. | **P2 (Medium)** | Developers, Contributors |
| *Headless API & Networking* | | | |
| [HEADLESS_API_OPERATIONS.md](architecture/api_network/HEADLESS_API_OPERATIONS.md) | Phase 6 REST API, durable queue, worker, discovery, diagnostics, and container operations. | **P2 (Medium)** | Developers, Maintainers |
| [LAN_RENDER_FARM.md](architecture/api_network/LAN_RENDER_FARM.md) | Local area network rendering node protocol and sharding. | **P2 (Medium)** | Developers, Maintainers |
| [API_CONTRACT_REFERENCE.md](architecture/api_network/API_CONTRACT_REFERENCE.md) | REST API endpoints and JSON response schemas. | **P2 (Medium)** | Developers, Maintainers |
| [NETWORK_SECURITY_API.md](architecture/api_network/NETWORK_SECURITY_API.md) | Allowed hosts whitelist, rate limiting, and LAN isolation rules. | **P2 (Medium)** | Developers, Maintainers |
| *Interface & Governance* | | | |
| [DESKTOP_UI_COMPONENTS.md](architecture/interface_governance/DESKTOP_UI_COMPONENTS.md) | PySide6 Qt GUI widgets, worker threads, and split slider. | **P3 (Low)** | Users, Developers |
| [WEBUI_DASHBOARD.md](architecture/interface_governance/WEBUI_DASHBOARD.md) | FastAPI/Gradio Local WebUI server configuration and endpoints. | **P2 (Medium)** | Users, Developers |
| [ECOSYSTEM_GOVERNANCE_LIFECYCLE.md](architecture/interface_governance/ECOSYSTEM_GOVERNANCE_LIFECYCLE.md) | Phase 7 plugin governance, sandboxing, updates, security, and offline maintenance. | **P2 (Medium)** | Developers, Maintainers |
| [DELIVERY_CODECS_PRESETS.md](architecture/interface_governance/DELIVERY_CODECS_PRESETS.md) | FFmpeg codec parameters for AV1, HEVC, ProRes, and DNxHR. | **P2 (Medium)** | Users, Developers |
| **Developer Documentation** | | | |
| [BUILD_AND_PACKAGING.md](developer/BUILD_AND_PACKAGING.md) | Custom offline compiler for desktop/CLI setups. | **P2 (Medium)** | Developers, Maintainers |
| [VERIFICATION_GUIDE.md](developer/VERIFICATION_GUIDE.md) | Rules for marking features complete and keeping docs synchronized. | **P1 (High)** | Developers, Maintainers |
| [QUALITY_METRICS.md](developer/QUALITY_METRICS.md) | Metrik evaluasi kualitas hasil video (VMAF, PSNR, SSIM). | **P3 (Low)** | Developers, Maintainers |
| [DATASET_BENCHMARKING.md](developer/DATASET_BENCHMARKING.md) | Quality regression testing against matched datasets. | **P3 (Low)** | Developers, Maintainers |
| [COMPILATION_RELEASE_GUIDE.md](developer/COMPILATION_RELEASE_GUIDE.md) | Compiler specification, containers, and QA smoke checks. | **P2 (Medium)** | Developers, Maintainers |
| [DEVELOPER_SETUP.md](developer/DEVELOPER_SETUP.md) | Contributor setup, virtual environment, and packages. | **P2 (Medium)** | Developers, Contributors |
| [CI_CD_AUTOMATION.md](developer/CI_CD_AUTOMATION.md) | Continuous Integration pipeline and automated cross-platform QA. | **P3 (Low)** | Developers, Maintainers |
| **User Documentation** | | | |
| [CLI_WORKFLOW.md](user/CLI_WORKFLOW.md) | Panduan lengkap argumen CLI dan contoh penggunaan. | **P2 (Medium)** | Users, Developers |
| [UI_WORKFLOW.md](user/UI_WORKFLOW.md) | Rancangan interaksi pengguna melalui desktop GUI. | **P3 (Low)** | Users, Developers |
| [TROUBLESHOOTING.md](user/TROUBLESHOOTING.md) | Panduan penyelesaian masalah driver GPU dan error runtime. | **P2 (Medium)** | Users, Contributors |
| [LOCAL_PRESETS_SYNC.md](user/LOCAL_PRESETS_SYNC.md) | Local-first encrypted preset sync and backup options. | **P3 (Low)** | Users, Developers |
| [HARDWARE_THERMAL_GOVERNOR.md](user/HARDWARE_THERMAL_GOVERNOR.md) | Dynamic resource governor, battery manager, and thermal throttling. | **P2 (Medium)** | Users, Developers |
| [PERFORMANCE_GUIDELINE.md](user/PERFORMANCE_GUIDELINE.md) | Hardware profiling settings and optimization profiles. | **P2 (Medium)** | Users, Developers |
| [DOCKER_PODMAN_DEPLOYMENT.md](user/DOCKER_PODMAN_DEPLOYMENT.md) | Headless Containerfile configurations and Docker deployment. | **P2 (Medium)** | Users, Developers |

---

## 2. Documentation Categories

To maintain structure, documents are categorized into:

1.  **Product Documentation**: Core product definitions (under `product/`).
2.  **Architecture Documentation**: System design specs, split into subcategories (under `architecture/` - `pipeline/`, `models/`, `api_network/`, `interface_governance/`).
3.  **Developer Documentation**: Setup, verification, and compilation (under `developer/`).
4.  **User Documentation**: How to run the application (under `user/`).

---

## 3. Style Guide & Writing Standards

*   **Language**: All documentation must be written in **English** to ensure global open-source accessibility.
*   **Format**: Use Standard GitHub Flavored Markdown (GFM) headings (`#` for H1, `##` for H2). Ensure exactly one H1 per file.
*   **Feature Status Badges**: Use status markers to indicate feature maturity:
    *   `[Planned]`: Features under design with no implementation.
    *   `[MVP]`: Minimum viable features mandatory for first release.
    *   `[Experimental]`: Implemented features undergoing tests or optimization.
    *   `[Future]`: Long-term features outside the current development cycle.

---

## 4. Early-Stage Scope Boundaries (Out-of-Scope)

To maintain focus and avoid scope creep during the early phases of development, the following domains are strictly **out of scope**:
1.  **Real-Time Processing**: No real-time preview playback during enhancement or stream processing. Only file-to-file processing is supported.
2.  **Mobile Support**: No Android or iOS compilation targets.
3.  **Cloud-Based Computing**: The system must run entirely local-first. No online API processing.
4.  **Video Timeline Editing**: No cutting, merging, or multi-track audio-video editing timeline.
