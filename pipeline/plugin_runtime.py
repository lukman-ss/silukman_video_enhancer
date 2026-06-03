"""Runtime integration helpers for sandboxed pipeline plugins."""

from __future__ import annotations

from typing import Any

from pipeline.audit_log import AuditLog, EVENT_PERMISSION_DENIED, EVENT_PLUGIN_ACTION
from pipeline.plugin_sandbox import SandboxPolicy, SandboxedRegistry
from pipeline.plugin_sdk import PluginRegistry, _default_registry


def sandboxed_registry(
    registry: PluginRegistry | None = None,
    policy: SandboxPolicy | None = None,
) -> SandboxedRegistry:
    """Return a sandboxed view of the active plugin registry."""

    return SandboxedRegistry(registry or _default_registry, policy)


def call_stage_plugins(
    stage: str,
    payload: Any,
    *,
    registry: PluginRegistry | None = None,
    policy: SandboxPolicy | None = None,
    audit_log: AuditLog | None = None,
    **context: Any,
) -> Any:
    """Run all plugins for *stage*, piping each result into the next plugin."""

    active_registry = registry or _default_registry
    sandboxed = sandboxed_registry(active_registry, policy)
    result = payload
    for plugin in active_registry.list_by_stage(stage):
        try:
            result = sandboxed.call(plugin.name, result, **context)
            if audit_log is not None:
                audit_log.record(
                    EVENT_PLUGIN_ACTION,
                    actor=f"plugin:{plugin.name}",
                    plugin_id=plugin.name,
                    detail={"stage": stage},
                )
        except PermissionError as exc:
            if audit_log is not None:
                audit_log.record(
                    EVENT_PERMISSION_DENIED,
                    actor=f"sandbox:{plugin.name}",
                    plugin_id=plugin.name,
                    detail={"stage": stage, "reason": str(exc)},
                )
            raise
    return result


def collect_ffmpeg_filters(
    *,
    registry: PluginRegistry | None = None,
    policy: SandboxPolicy | None = None,
    audit_log: AuditLog | None = None,
    **context: Any,
) -> tuple[str, ...]:
    """Collect FFmpeg video filter fragments from registered filter plugins."""

    active_registry = registry or _default_registry
    sandboxed = sandboxed_registry(active_registry, policy)
    filters: list[str] = []
    for plugin in active_registry.list_by_stage("ffmpeg_filter"):
        try:
            produced = sandboxed.call(plugin.name, **context)
            if audit_log is not None:
                audit_log.record(
                    EVENT_PLUGIN_ACTION,
                    actor=f"plugin:{plugin.name}",
                    plugin_id=plugin.name,
                    detail={"stage": "ffmpeg_filter"},
                )
        except PermissionError as exc:
            if audit_log is not None:
                audit_log.record(
                    EVENT_PERMISSION_DENIED,
                    actor=f"sandbox:{plugin.name}",
                    plugin_id=plugin.name,
                    detail={"stage": "ffmpeg_filter", "reason": str(exc)},
                )
            raise
        if produced is None:
            continue
        if isinstance(produced, str):
            filters.append(produced)
        else:
            filters.extend(str(item) for item in produced)
    return tuple(filter(None, filters))
