# Python Desktop UI Workflow Design

This document details the planned Python desktop GUI workflow for `silukman_video_enhancer`.

---

## Desktop Stack Decision [Planned]

The desktop application will use a Python-first stack:

*   **UI Toolkit**: PySide6 / Qt.
*   **Application Runtime**: Python 3.9+.
*   **Worker Model**: Qt worker threads or `QThreadPool` for non-blocking video jobs.
*   **Pipeline Integration**: Direct calls into the Python pipeline and inference modules.
*   **Packaging Target**: PyInstaller-based offline installers for Windows, macOS, and Linux.

This keeps the CLI, processing pipeline, inference engine, and desktop UI in one implementation language.

---

## UI Concept & Layout [Future]

The desktop application is designed as a single-window interface with a simple, modern aesthetic:

1.  **Media Selection Panel**: Drag-and-drop landing zone for input videos.
2.  **Settings Sidebar**: Configuration options (Upscaling target, Denoise slider, Output directory, Hardware selector).
3.  **Visual Preview Area**: A side-by-side or slider-split video player showing a cropped preview of the enhancement results (Original vs. Restored) on the current frame.
4.  **Progress Bar & Logs**: Displaying encoding speeds (FPS), estimated completion time, and console logs.

---

## Desktop Implementation Rules [Planned]

*   Long-running FFmpeg and ONNX jobs must run outside the main UI thread.
*   The UI must subscribe to progress events instead of polling blocking subprocesses.
*   Enhancement settings must map to the same configuration model used by the CLI.
*   The first desktop MVP should prioritize file selection, output settings, hardware selection, progress reporting, and job completion notification.
*   Real-time full-video playback during enhancement remains out of scope for the early desktop release.

---

## User Interaction Flow [Future]

```
[Launch App] ──> [Drag & Drop Video] ──> [Select Enhancement Profile] ──> [Inspect Frame Preview] ──> [Click "Start Enhancement"] ──> [Track Progress & Export]
```

*   **Offline Operation**: The UI does not require internet access. If a model file is missing, the UI should prompt the user to download it manually or download it through the app with a one-time connection.
*   **Preview Rendering**: Instead of rendering the whole video, clicking the preview area renders only a $256 \times 256$ crop around the cursor position to save GPU processing time.
