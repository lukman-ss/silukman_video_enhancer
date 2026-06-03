"""Local LAN render farm planning."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List
from urllib import request

from utils.ffmpeg import require_binary


@dataclass(frozen=True)
class RenderNode:
    name: str
    host: str
    port: int

    @property
    def endpoint(self) -> str:
        return f"{self.host}:{self.port}"


@dataclass(frozen=True)
class RenderShard:
    node: RenderNode
    start_frame: int
    end_frame: int


@dataclass(frozen=True)
class RenderShardResult:
    shard: RenderShard
    success: bool
    message: str


@dataclass(frozen=True)
class TranscodeSegment:
    node: RenderNode
    start_seconds: float
    end_seconds: float
    output_path: Path


@dataclass(frozen=True)
class AdaptiveMergePlan:
    segments: tuple[TranscodeSegment, ...]
    merge_mode: str


def shard_frames(total_frames: int, nodes: Iterable[RenderNode]) -> List[RenderShard]:
    node_list = list(nodes)
    if total_frames <= 0 or not node_list:
        return []
    chunk = (total_frames + len(node_list) - 1) // len(node_list)
    shards = []
    for index, node in enumerate(node_list):
        start = index * chunk
        end = min(total_frames, start + chunk)
        if start < end:
            shards.append(RenderShard(node=node, start_frame=start, end_frame=end))
    return shards


class RenderFarmCoordinator:
    """Dispatch frame shards to LAN render nodes over a small HTTP contract."""

    def __init__(self, nodes: Iterable[RenderNode], timeout_seconds: float = 30.0) -> None:
        self.nodes = list(nodes)
        self.timeout_seconds = timeout_seconds

    def dispatch(self, total_frames: int, job_payload: dict) -> list[RenderShardResult]:
        results = []
        for shard in shard_frames(total_frames, self.nodes):
            results.append(self._dispatch_shard(shard, job_payload))
        return results

    def dispatch_with_retries(
        self,
        total_frames: int,
        job_payload: dict,
        max_retries: int = 1,
    ) -> list[RenderShardResult]:
        results = self.dispatch(total_frames, job_payload)
        for _ in range(max_retries):
            failed = [result for result in results if not result.success]
            if not failed:
                break
            retry_results = [self._dispatch_shard(result.shard, job_payload) for result in failed]
            retry_by_range = {
                (result.shard.start_frame, result.shard.end_frame): result
                for result in retry_results
            }
            results = [
                retry_by_range.get((result.shard.start_frame, result.shard.end_frame), result)
                if not result.success
                else result
                for result in results
            ]
        return results

    def _dispatch_shard(self, shard: RenderShard, job_payload: dict) -> RenderShardResult:
        payload = {
            **job_payload,
            "start_frame": shard.start_frame,
            "end_frame": shard.end_frame,
            "node": shard.node.name,
        }
        data = json.dumps(payload).encode("utf-8")
        req = request.Request(
            f"http://{shard.node.endpoint}/render",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                body = response.read().decode("utf-8")
                success = 200 <= response.status < 300
                return RenderShardResult(shard, success, body or response.reason)
        except OSError as exc:
            return RenderShardResult(shard, False, str(exc))

    def dispatch_transcode_segments(
        self,
        duration_seconds: float,
        segment_seconds: float,
        output_dir: Path,
        job_payload: dict,
    ) -> AdaptiveMergePlan:
        plan = plan_distributed_transcode(
            duration_seconds,
            segment_seconds,
            self.nodes,
            output_dir,
        )
        for segment in plan.segments:
            shard = RenderShard(
                node=segment.node,
                start_frame=round(segment.start_seconds * 1000),
                end_frame=round(segment.end_seconds * 1000),
            )
            self._dispatch_shard(
                shard,
                {
                    **job_payload,
                    "start_seconds": segment.start_seconds,
                    "end_seconds": segment.end_seconds,
                    "output_path": str(segment.output_path),
                },
            )
        return plan


def plan_distributed_transcode(
    duration_seconds: float,
    segment_seconds: float,
    nodes: Iterable[RenderNode],
    output_dir: Path,
) -> AdaptiveMergePlan:
    """Plan LAN transcoding segments with adaptive lossless merge mode."""

    node_list = list(nodes)
    if duration_seconds <= 0:
        raise ValueError("duration_seconds must be greater than zero.")
    if segment_seconds <= 0:
        raise ValueError("segment_seconds must be greater than zero.")
    if not node_list:
        raise ValueError("At least one render node is required.")
    output_dir.mkdir(parents=True, exist_ok=True)
    segments = []
    start = 0.0
    index = 0
    while start < duration_seconds:
        end = min(duration_seconds, start + segment_seconds)
        node = node_list[index % len(node_list)]
        segments.append(
            TranscodeSegment(
                node=node,
                start_seconds=start,
                end_seconds=end,
                output_path=output_dir / f"segment-{index:04}.mp4",
            )
        )
        start = end
        index += 1
    merge_mode = "stream-copy" if len(segments) > 1 else "single-segment"
    return AdaptiveMergePlan(segments=tuple(segments), merge_mode=merge_mode)


def merge_shard_outputs(shard_outputs: list[Path], output_path: Path) -> Path:
    """Merge completed shard video files losslessly with FFmpeg concat."""

    if not shard_outputs:
        raise ValueError("At least one shard output is required.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = require_binary("ffmpeg")
    concat_file = output_path.with_suffix(output_path.suffix + ".concat.txt")
    concat_file.write_text(
        "\n".join(f"file '{path.as_posix()}'" for path in shard_outputs),
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-c",
            "copy",
            str(output_path),
        ],
        capture_output=True,
        text=True,
    )
    concat_file.unlink(missing_ok=True)
    if result.returncode != 0:
        raise RuntimeError(f"Render shard merge failed: {result.stderr.strip()}")
    return output_path
