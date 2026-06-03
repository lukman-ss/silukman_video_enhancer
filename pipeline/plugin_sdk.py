"""Plugin/extension SDK for custom model stages, FFmpeg filters, and export hooks.

Phase 7, Task 1: Plugin SDK
Plugins declare a manifest (dict or JSON) and register themselves via
``PluginRegistry``.  The registry validates the manifest schema, then stores
the plugin so the pipeline can call its stage hooks without editing core code.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


# ---------------------------------------------------------------------------
# Manifest schema
# ---------------------------------------------------------------------------

REQUIRED_MANIFEST_KEYS = {"name", "version", "stage"}

VALID_STAGES = {"model", "ffmpeg_filter", "export_hook"}


@dataclass
class PluginManifest:
    """Validated plugin manifest."""

    name: str
    version: str
    stage: str
    description: str = ""
    author: str = ""
    # Declared permissions — consumed by PluginSandbox (Task 2)
    permissions: List[str] = field(default_factory=list)
    # Arbitrary extension metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Runtime-attached callable (set by PluginRegistry.register)
    _handler: Optional[Callable[..., Any]] = field(
        default=None, repr=False, compare=False
    )

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PluginManifest":
        """Parse and validate a manifest dictionary."""
        missing = REQUIRED_MANIFEST_KEYS - set(data)
        if missing:
            raise ValueError(
                f"Plugin manifest missing required keys: {sorted(missing)}"
            )
        stage = data["stage"]
        if stage not in VALID_STAGES:
            raise ValueError(
                f"Invalid plugin stage '{stage}'. Must be one of {sorted(VALID_STAGES)}."
            )
        return cls(
            name=str(data["name"]),
            version=str(data["version"]),
            stage=stage,
            description=str(data.get("description", "")),
            author=str(data.get("author", "")),
            permissions=list(data.get("permissions", [])),
            metadata={
                k: v
                for k, v in data.items()
                if k
                not in {
                    "name",
                    "version",
                    "stage",
                    "description",
                    "author",
                    "permissions",
                }
            },
        )

    @classmethod
    def from_json_file(cls, path: Path) -> "PluginManifest":
        """Load a manifest from a JSON file on disk."""
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return cls.from_dict(data)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "stage": self.stage,
            "description": self.description,
            "author": self.author,
            "permissions": self.permissions,
            **self.metadata,
        }


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class PluginRegistry:
    """Central registry that loads and stores plugin manifests + handlers."""

    def __init__(self) -> None:
        self._plugins: Dict[str, PluginManifest] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self,
        manifest: PluginManifest | Dict[str, Any],
        handler: Callable[..., Any] | None = None,
    ) -> PluginManifest:
        """Register a plugin from a manifest dict/object plus an optional handler."""
        if isinstance(manifest, dict):
            manifest = PluginManifest.from_dict(manifest)
        if manifest.name in self._plugins:
            raise ValueError(
                f"Plugin '{manifest.name}' is already registered. "
                "Unregister it first or use a different name."
            )
        manifest._handler = handler
        self._plugins[manifest.name] = manifest
        return manifest

    def register_from_file(
        self,
        json_path: Path,
        handler: Callable[..., Any] | None = None,
    ) -> PluginManifest:
        """Load manifest from a JSON file and register it."""
        manifest = PluginManifest.from_json_file(json_path)
        return self.register(manifest, handler)

    def unregister(self, name: str) -> None:
        """Remove a plugin from the registry."""
        self._plugins.pop(name, None)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get(self, name: str) -> PluginManifest:
        """Return a registered plugin by name, raising KeyError if absent."""
        return self._plugins[name]

    def list_all(self) -> List[PluginManifest]:
        return list(self._plugins.values())

    def list_by_stage(self, stage: str) -> List[PluginManifest]:
        return [p for p in self._plugins.values() if p.stage == stage]

    def __len__(self) -> int:
        return len(self._plugins)

    def __contains__(self, name: str) -> bool:
        return name in self._plugins

    # ------------------------------------------------------------------
    # Invocation helpers
    # ------------------------------------------------------------------

    def call(self, name: str, *args: Any, **kwargs: Any) -> Any:
        """Invoke a plugin's handler by name."""
        plugin = self.get(name)
        if plugin._handler is None:
            raise RuntimeError(
                f"Plugin '{name}' has no handler attached."
            )
        return plugin._handler(*args, **kwargs)


# ---------------------------------------------------------------------------
# Module-level default registry (convenience)
# ---------------------------------------------------------------------------

_default_registry = PluginRegistry()


def register_plugin(
    manifest: PluginManifest | Dict[str, Any],
    handler: Callable[..., Any] | None = None,
) -> PluginManifest:
    """Register a plugin in the default global registry."""
    return _default_registry.register(manifest, handler)


def get_plugin(name: str) -> PluginManifest:
    return _default_registry.get(name)


def list_plugins(stage: str | None = None) -> List[PluginManifest]:
    if stage:
        return _default_registry.list_by_stage(stage)
    return _default_registry.list_all()


def call_plugin(name: str, *args: Any, **kwargs: Any) -> Any:
    return _default_registry.call(name, *args, **kwargs)


def unregister_plugin(name: str) -> None:
    _default_registry.unregister(name)
