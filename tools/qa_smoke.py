"""Smoke-test helpers for packaged release artifacts."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SmokeTestResult:
    name: str
    passed: bool
    output: str


def run_packaged_cli_smoke(
    executable: Path,
    fixture_video: Path | None = None,
    timeout_seconds: float = 30.0,
) -> list[SmokeTestResult]:
    """Launch a packaged CLI and optionally run a tiny dry-run fixture."""

    if not executable.exists():
        raise ValueError(f"Packaged executable does not exist: {executable}")
    results = [_run_command("help", [str(executable), "--help"], timeout_seconds)]
    if fixture_video is not None:
        results.append(
            _run_command(
                "fixture-dry-run",
                [
                    str(executable),
                    "enhance",
                    "-i",
                    str(fixture_video),
                    "-o",
                    str(fixture_video.with_name("smoke-output.mp4")),
                    "--dry-run",
                ],
                timeout_seconds,
            )
        )
    return results


def summarize_smoke_results(results: list[SmokeTestResult]) -> bool:
    return all(result.passed for result in results)


def _run_command(name: str, command: list[str], timeout_seconds: float) -> SmokeTestResult:
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )
    output = "\n".join(part for part in [result.stdout, result.stderr] if part)
    return SmokeTestResult(name=name, passed=result.returncode == 0, output=output)
