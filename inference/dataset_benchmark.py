"""Benchmark dataset runner for quality regression checks."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterable

from app.report import ReportMetric, collect_quality_metrics
from pipeline.artifacts import ArtifactReport, detect_artifact


MetricCollector = Callable[[Path, Path], list[ReportMetric]]
ArtifactCollector = Callable[[Path], ArtifactReport]


@dataclass(frozen=True)
class BenchmarkPair:
    name: str
    original_path: Path
    enhanced_path: Path


@dataclass(frozen=True)
class BenchmarkCaseResult:
    name: str
    metrics: dict[str, str]
    artifact_score: float
    passed: bool
    failure_reason: str = ""


@dataclass(frozen=True)
class BenchmarkSummary:
    cases: tuple[BenchmarkCaseResult, ...]

    @property
    def passed(self) -> bool:
        return all(case.passed for case in self.cases)


def discover_benchmark_pairs(dataset_dir: Path) -> list[BenchmarkPair]:
    """Discover original/enhanced video pairs from a dataset directory."""

    pairs = []
    for original in sorted((dataset_dir / "original").glob("*")):
        if not original.is_file():
            continue
        enhanced = dataset_dir / "enhanced" / original.name
        if enhanced.exists():
            pairs.append(BenchmarkPair(original.stem, original, enhanced))
    return pairs


def run_dataset_benchmark(
    pairs: Iterable[BenchmarkPair],
    metric_collector: MetricCollector = collect_quality_metrics,
    artifact_collector: ArtifactCollector | None = None,
    baselines: dict[str, dict[str, float]] | None = None,
) -> BenchmarkSummary:
    """Run quality metrics across a dataset and compare optional baselines."""

    results = []
    for pair in pairs:
        metric_rows = metric_collector(pair.original_path, pair.enhanced_path)
        metrics = {metric.name: metric.value for metric in metric_rows}
        artifact = (
            artifact_collector(pair.enhanced_path)
            if artifact_collector is not None
            else detect_artifact(pair.enhanced_path.read_bytes()[:4096])
        )
        passed, reason = _compare_baseline(pair.name, metrics, baselines or {})
        if artifact.corrupted:
            passed = False
            reason = reason or "artifact detector flagged output"
        results.append(
            BenchmarkCaseResult(
                name=pair.name,
                metrics=metrics,
                artifact_score=artifact.score,
                passed=passed,
                failure_reason=reason,
            )
        )
    return BenchmarkSummary(cases=tuple(results))


def write_benchmark_summary(summary: BenchmarkSummary, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(
            {
                "passed": summary.passed,
                "cases": [
                    {
                        **asdict(case),
                    }
                    for case in summary.cases
                ],
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return output_path


def _compare_baseline(
    name: str,
    metrics: dict[str, str],
    baselines: dict[str, dict[str, float]],
) -> tuple[bool, str]:
    expected = baselines.get(name, {})
    for metric_name, minimum in expected.items():
        try:
            value = float(metrics.get(metric_name, "nan"))
        except ValueError:
            return False, f"{metric_name} is not numeric"
        if value < minimum:
            return False, f"{metric_name} {value:.3f} below baseline {minimum:.3f}"
    return True, ""
