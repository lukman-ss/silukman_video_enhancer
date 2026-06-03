# API Contract & Schema Reference

This document defines the REST API endpoints, JSON request/response schemas, and real-time event specifications for the headless service mode in `silukman_video_enhancer`.

---

## 1. Authentication

When the service profile requires authentication, clients must include the API token in the request headers:

```http
Authorization: Bearer <your_access_token>
```

---

## 2. Job Endpoints

### GET `/api/jobs`
Lists all queued, running, completed, and failed enhancement jobs.
*   **Response (200 OK)**:
    ```json
    [
      {
        "id": "job_01",
        "status": "running",
        "progress": 45.2,
        "input_path": "/path/to/input.mp4",
        "output_path": "/path/to/output.mp4"
      }
    ]
    ```

### POST `/api/jobs`
Submits a new video enhancement job to the local queue.
*   **Request Body**:
    ```json
    {
      "input_path": "/path/to/input.mp4",
      "output_path": "/path/to/output.mp4",
      "model": "realesrgan",
      "scale": 2,
      "denoise": true
    }
    ```
*   **Response (201 Created)**:
    ```json
    {
      "id": "job_02",
      "status": "queued",
      "message": "job submitted successfully"
    }
    ```

### GET `/api/jobs/{id}`
Inspects a specific job's state and telemetry.
*   **Response (200 OK)**:
    ```json
    {
      "id": "job_02",
      "status": "completed",
      "progress": 100.0,
      "metrics": {
        "psnr": "38.2",
        "ssim": "0.98"
      }
    }
    ```

---

## 3. Real-time Log Streaming (SSE)

Clients can subscribe to live status updates and logs via Server-Sent Events (SSE).

### GET `/api/jobs/{id}/events`
Establishes a persistent SSE connection.
*   **Event Formats**:
    *   `progress`: Emitted on frame process completions.
        ```json
        { "frame": 120, "total": 240, "fps": 15.4 }
        ```
    *   `log`: Contains FFmpeg stdout/stderr or internal warning outputs.
        ```json
        { "level": "info", "message": "frame padding completed" }
        ```

---

## 4. Diagnostics & Health

### GET `/api/health`
Checks service operational state.
*   **Response (200 OK)**:
    ```json
    {
      "status": "ready"
    }
    ```

### GET `/api/diagnostics`
Provides detailed metrics on system resources, hardware provider loading, and queue telemetry.
*   **Response (200 OK)**:
    ```json
    {
      "active_jobs": 1,
      "ffmpeg_available": true,
      "model_cache_ready": true,
      "hardware_providers": ["CUDAExecutionProvider"]
    }
    ```
