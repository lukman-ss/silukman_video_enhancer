"""Plugin sandboxing and permission model for safe local extensions.

Phase 7, Task 2: Plugin Sandbox
The sandbox gates every plugin call behind a declared-permissions check.
Plugins must list required permissions in their manifest before any
restricted operation (file access, model loading, FFmpeg, network) is allowed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Set

from pipeline.plugin_sdk import PluginManifest


# ---------------------------------------------------------------------------
# Permission catalogue
# ---------------------------------------------------------------------------

ALL_PERMISSIONS: Set[str] = {
    "file.read",
    "file.write",
    "model.load",
    "ffmpeg.filter",
    "network",  # intentionally reserved — offline-first apps should not grant this
}

# Permissions that require explicit allowlisting by the host application
SENSITIVE_PERMISSIONS: Set[str] = {"file.write", "model.load", "network"}


class PermissionDeniedError(PermissionError):
    """Raised when a plugin tries to use an undeclared permission."""


# ---------------------------------------------------------------------------
# Sandbox configuration
# ---------------------------------------------------------------------------


@dataclass
class SandboxPolicy:
    """Host-level policy applied on top of each plugin's declared permissions."""

    # Set of permissions the host is willing to grant at all.
    allowed_permissions: Set[str] = field(
        default_factory=lambda: {
            "file.read",
            "file.write",
            "model.load",
            "ffmpeg.filter",
        }
    )
    # If True, 'network' permission is never granted regardless of what the
    # plugin declares (enforces offline-first).
    block_network: bool = True

    def effective_permissions(self, declared: List[str]) -> Set[str]:
        """Intersect declared permissions with host policy.

        Returns the set of permissions actually granted to the plugin.
        """
        requested = set(declared)
        if self.block_network:
            requested.discard("network")
        unknown = requested - ALL_PERMISSIONS
        if unknown:
            raise PermissionDeniedError(
                f"Plugin declared unknown permissions: {sorted(unknown)}. "
                f"Valid permissions are: {sorted(ALL_PERMISSIONS)}."
            )
        granted = requested & self.allowed_permissions
        denied = requested - granted
        if denied:
            raise PermissionDeniedError(
                f"Host policy denies permissions: {sorted(denied)}."
            )
        return granted


# ---------------------------------------------------------------------------
# Per-plugin sandbox context
# ---------------------------------------------------------------------------


class PluginSandbox:
    """Wraps a PluginManifest and enforces its declared permissions at runtime."""

    def __init__(
        self,
        manifest: PluginManifest,
        policy: SandboxPolicy | None = None,
    ) -> None:
        self._manifest = manifest
        self._policy = policy or SandboxPolicy()
        # Resolve the effective permission set once at construction time.
        self._granted: Set[str] = self._policy.effective_permissions(
            manifest.permissions
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return self._manifest.name

    @property
    def granted_permissions(self) -> Set[str]:
        return frozenset(self._granted)  # type: ignore[return-value]

    def has_permission(self, permission: str) -> bool:
        return permission in self._granted

    def require(self, permission: str) -> None:
        """Assert that the plugin holds *permission*, raising on failure."""
        if permission not in self._granted:
            raise PermissionDeniedError(
                f"Plugin '{self.name}' requires permission '{permission}' "
                "which was not granted. Add it to the plugin manifest's "
                "'permissions' list and ensure the host policy allows it."
            )

    def call(self, handler: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Invoke *handler* inside the sandbox context.

        The handler receives the sandbox instance as a keyword argument
        ``sandbox`` so it can perform fine-grained permission checks.
        """
        return handler(*args, sandbox=self, **kwargs)

    # ------------------------------------------------------------------
    # Convenience checkers for common permission groups
    # ------------------------------------------------------------------

    def check_file_read(self) -> None:
        self.require("file.read")

    def check_file_write(self) -> None:
        self.require("file.write")

    def check_model_load(self) -> None:
        self.require("model.load")

    def check_ffmpeg_filter(self) -> None:
        self.require("ffmpeg.filter")

    def check_network(self) -> None:
        self.require("network")

    # ------------------------------------------------------------------
    # Repr
    # ------------------------------------------------------------------

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"PluginSandbox(name={self.name!r}, "
            f"granted={sorted(self._granted)})"
        )


# ---------------------------------------------------------------------------
# SandboxedRegistry — wraps PluginRegistry with automatic sandboxing
# ---------------------------------------------------------------------------


class SandboxedRegistry:
    """A thin wrapper around a PluginRegistry that sandboxes every call."""

    def __init__(
        self,
        registry: Any,  # pipeline.plugin_sdk.PluginRegistry
        policy: SandboxPolicy | None = None,
    ) -> None:
        self._registry = registry
        self._policy = policy or SandboxPolicy()
        # Build sandbox instances for all already-registered plugins.
        self._sandboxes: Dict[str, PluginSandbox] = {}
        for plugin in registry.list_all():
            self._sandboxes[plugin.name] = PluginSandbox(plugin, self._policy)

    def sandbox_for(self, name: str) -> PluginSandbox:
        """Return (or lazily create) the sandbox for a registered plugin."""
        if name not in self._sandboxes:
            manifest = self._registry.get(name)
            self._sandboxes[name] = PluginSandbox(manifest, self._policy)
        return self._sandboxes[name]

    def call(self, name: str, *args: Any, **kwargs: Any) -> Any:
        """Sandboxed invocation: checks permissions, then delegates to handler."""
        sandbox = self.sandbox_for(name)
        plugin = self._registry.get(name)
        if plugin._handler is None:
            raise RuntimeError(f"Plugin '{name}' has no handler attached.")
        return sandbox.call(plugin._handler, *args, **kwargs)

    def granted_permissions(self, name: str) -> Set[str]:
        return self.sandbox_for(name).granted_permissions
