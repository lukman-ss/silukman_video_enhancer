"""Local observability telemetry for render services."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class TelemetryRecord:
    job_id: str
    fps: float
    provider: str
    temperature_c: float | None = None
    memory_mb: float | None = None
    error: str = ""
    quality_score: float | None = None


class TelemetryStore:
    def __init__(self) -> None:
        self._records: list[TelemetryRecord] = []

    def append(self, record: TelemetryRecord) -> None:
        self._records.append(record)

    def list(self) -> list[TelemetryRecord]:
        return list(self._records)

    def dashboard_payload(self) -> dict:
        records = [asdict(record) for record in self._records]
        avg_fps = (
            sum(record.fps for record in self._records) / len(self._records)
            if self._records
            else 0.0
        )
        errors = [record.error for record in self._records if record.error]
        return {"records": records, "average_fps": avg_fps, "errors": errors}
