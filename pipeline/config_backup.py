"""Configuration backup, restore, and migration tooling.

Phase 7, Task 5
Exports presets, plugin settings, server profiles, and migration metadata
to a portable ZIP archive.  Restore re-applies the archive to a target
directory, verifying version compatibility.  A simple migration table allows
renaming / transforming keys between app versions.
"""

from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


# ---------------------------------------------------------------------------
# Version compatibility
# ---------------------------------------------------------------------------

APP_VERSION = "1.0.0"

# Semver-style: (major, minor, patch)
def _parse_version(v: str):
    parts = str(v).split(".")
    return tuple(int(p) for p in (parts + ["0", "0", "0"])[:3])


def is_compatible(saved_version: str, current_version: str = APP_VERSION) -> bool:
    """Return True when the saved backup's major version matches current."""
    sv = _parse_version(saved_version)
    cv = _parse_version(current_version)
    return sv[0] == cv[0]


# ---------------------------------------------------------------------------
# Migration rule
# ---------------------------------------------------------------------------


@dataclass
class MigrationRule:
    """Transforms a config dict from *from_version* to *to_version*."""

    from_version: str
    to_version: str
    transform: Callable[[Dict[str, Any]], Dict[str, Any]]

    def applies(self, version: str) -> bool:
        return version == self.from_version

    def run(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return self.transform(data)


class MigrationChain:
    """Applies a sequence of MigrationRules to upgrade a config dict."""

    def __init__(self) -> None:
        self._rules: List[MigrationRule] = []

    def add_rule(self, rule: MigrationRule) -> None:
        self._rules.append(rule)

    def migrate(self, data: Dict[str, Any], from_version: str) -> Dict[str, Any]:
        """Apply all matching rules in order, returning the migrated dict."""
        result = dict(data)
        current = from_version
        for rule in self._rules:
            if rule.applies(current):
                result = rule.run(result)
                current = rule.to_version
        return result


# ---------------------------------------------------------------------------
# Backup manifest stored inside the ZIP
# ---------------------------------------------------------------------------

_MANIFEST_NAME = "backup_manifest.json"


@dataclass
class BackupManifest:
    app_version: str = APP_VERSION
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    sections: List[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "app_version": self.app_version,
            "created_at": self.created_at,
            "sections": self.sections,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "BackupManifest":
        return cls(
            app_version=str(d.get("app_version", "0.0.0")),
            created_at=str(d.get("created_at", "")),
            sections=list(d.get("sections", [])),
            notes=str(d.get("notes", "")),
        )


# ---------------------------------------------------------------------------
# ConfigBackup — the main backup/restore engine
# ---------------------------------------------------------------------------

# Known section names (callers may use any string, these are the canonical ones)
SECTION_PRESETS = "presets"
SECTION_PLUGINS = "plugins"
SECTION_SERVER = "server"
SECTION_MIGRATION = "migration"


class ConfigBackup:
    """
    Creates and restores configuration backup archives.

    Usage (backup)::

        cb = ConfigBackup()
        cb.add_section("presets", {"scale_4k": {"scale": 4, "model": "realesr"}})
        cb.add_section("plugins", {"my_plugin": {"version": "1.0"}})
        path = cb.save(Path("/backups/config_v1.zip"))

    Usage (restore)::

        sections, manifest = ConfigBackup.restore(Path("/backups/config_v1.zip"))
        presets = sections["presets"]
    """

    def __init__(self, notes: str = "") -> None:
        self._sections: Dict[str, Any] = {}
        self._notes = notes

    # ------------------------------------------------------------------
    # Building a backup
    # ------------------------------------------------------------------

    def add_section(self, name: str, data: Any) -> "ConfigBackup":
        self._sections[name] = data
        return self

    def save(self, path: Path) -> Path:
        """Write a ZIP archive containing all sections as JSON files."""
        path.parent.mkdir(parents=True, exist_ok=True)
        manifest = BackupManifest(
            sections=list(self._sections.keys()),
            notes=self._notes,
        )
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(
                _MANIFEST_NAME,
                json.dumps(manifest.to_dict(), indent=2),
            )
            for section, data in self._sections.items():
                zf.writestr(
                    f"{section}.json",
                    json.dumps(data, indent=2),
                )
        return path

    # ------------------------------------------------------------------
    # Restoring
    # ------------------------------------------------------------------

    @staticmethod
    def restore(
        path: Path,
        migration_chain: Optional[MigrationChain] = None,
    ) -> tuple[Dict[str, Any], BackupManifest]:
        """
        Load all sections from *path*.

        Returns ``(sections_dict, manifest)``.
        Raises ``ValueError`` if the backup's major version is incompatible.
        If *migration_chain* is provided, applies migration rules to each
        section whose key contains ``"migration"`` metadata.
        """
        with zipfile.ZipFile(path, "r") as zf:
            manifest = BackupManifest.from_dict(
                json.loads(zf.read(_MANIFEST_NAME))
            )
            if not is_compatible(manifest.app_version):
                raise ValueError(
                    f"Backup version '{manifest.app_version}' is incompatible "
                    f"with current app version '{APP_VERSION}'. "
                    "Major versions must match."
                )
            sections: Dict[str, Any] = {}
            for name in manifest.sections:
                fname = f"{name}.json"
                if fname in zf.namelist():
                    sections[name] = json.loads(zf.read(fname))

        if migration_chain is not None:
            for key in list(sections.keys()):
                sections[key] = migration_chain.migrate(
                    sections[key], manifest.app_version
                )

        return sections, manifest

    @staticmethod
    def list_sections(path: Path) -> List[str]:
        """Return the list of section names stored in a backup ZIP."""
        with zipfile.ZipFile(path, "r") as zf:
            manifest = BackupManifest.from_dict(
                json.loads(zf.read(_MANIFEST_NAME))
            )
        return manifest.sections


SECTION_FILENAMES = {
    SECTION_PRESETS: "presets.json",
    SECTION_PLUGINS: "plugins.json",
    SECTION_SERVER: "server.json",
}


def backup_config_directory(
    config_dir: Path,
    backup_path: Path,
    *,
    sections: List[str] | None = None,
    notes: str = "",
) -> Path:
    """Create a portable backup from canonical config files in *config_dir*."""

    selected = sections or [SECTION_PRESETS, SECTION_PLUGINS, SECTION_SERVER]
    backup = ConfigBackup(notes=notes)
    for section in selected:
        filename = SECTION_FILENAMES.get(section, f"{section}.json")
        path = Path(config_dir) / filename
        if path.exists():
            backup.add_section(section, json.loads(path.read_text(encoding="utf-8")))
        else:
            backup.add_section(section, {})
    return backup.save(backup_path)


def restore_config_directory(
    backup_path: Path,
    config_dir: Path,
    *,
    migration_chain: MigrationChain | None = None,
) -> BackupManifest:
    """Restore backed-up config sections as JSON files in *config_dir*."""

    sections, manifest = ConfigBackup.restore(backup_path, migration_chain=migration_chain)
    target = Path(config_dir)
    target.mkdir(parents=True, exist_ok=True)
    for section, data in sections.items():
        filename = SECTION_FILENAMES.get(section, f"{section}.json")
        (target / filename).write_text(json.dumps(data, indent=2), encoding="utf-8")
    return manifest
