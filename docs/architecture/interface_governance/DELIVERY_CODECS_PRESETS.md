# Delivery Codecs & Presets Reference

This document provides a technical reference for delivery codecs, compression parameters, and FFmpeg export options available in `silukman_video_enhancer`.

---

## 1. Overview & Purpose

Selecting the correct output codec is essential for archiving, delivery, or editing. 

To support diverse professional workflows, the application provides built-in **Delivery Presets** generating optimized FFmpeg parameters for:
*   Standard consumer delivery (AV1, HEVC).
*   High-fidelity video editing intermediates (ProRes, DNxHR).
*   Lossless archival preservation (FFV1).

---

## 2. Codec Specifications & Arguments

The preset planner builds corresponding FFmpeg command arguments:

### A. AV1 (AOMedia Video 1)
*   **Purpose**: Ultra-efficient next-generation delivery with low file size.
*   **Arguments**:
    ```bash
    -c:v libsvtav1 -pix_fmt yuv420p10le -crf 24
    ```

### B. HEVC 10-bit (H.265)
*   **Purpose**: High-efficiency delivery with wide hardware player compatibility.
*   **Arguments**:
    ```bash
    -c:v libx265 -pix_fmt yuv420p10le -crf 20
    ```

### C. Apple ProRes (ProRes 422 HQ)
*   **Purpose**: High-fidelity intermediate codec for editing on macOS (Final Cut Pro, Premiere).
*   **Arguments**:
    ```bash
    -c:v prores_ks -profile:v 3 -vendor apl0 -pix_fmt yuv422p10le
    ```

### D. Avid DNxHR (DNxHR HQ)
*   **Purpose**: Post-production intermediate codec for Windows/Linux editing.
*   **Arguments**:
    ```bash
    -c:v dnxhd -profile:v dnxhr_hq -pix_fmt yuv422p10le
    ```

### E. Archival FFV1
*   **Purpose**: Mathematically lossless archiving for long-term historical preservation.
*   **Arguments**:
    ```bash
    -c:v ffv1 -level 3 -pix_fmt yuv420p
    ```

---

## 3. Configuration & CLI Presets

Presets can be invoked using named profiles:
*   `--preset`: Select from `av1`, `hevc_10bit`, `prores`, `dnxhr`, or `ffv1`.

---

## 4. Verification

Preset configuration parsing and FFmpeg command generation are verified in:

```bash
python3 -m unittest tests.test_phase5_completion
```
Unit tests cover preset-to-argument conversions and check format parameters.
