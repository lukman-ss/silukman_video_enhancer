"""Database defragmentation and cache compaction utility.

Phase 7, Task 11
DbCompactor prunes old job history records from a SQLite-backed job queue
database and runs SQLite VACUUM to reclaim fragmented space.
CacheCompactor removes stale cache files from a directory tree based on
age and total size limits.
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Job history pruner (SQLite)
# ---------------------------------------------------------------------------


@dataclass
class PruneResult:
    """Summary of a database prune + vacuum run."""
    rows_deleted: int = 0
    size_before_bytes: int = 0
    size_after_bytes: int = 0
    vacuumed: bool = False
    duration_ms: float = 0.0
    error: Optional[str] = None

    @property
    def bytes_reclaimed(self) -> int:
        return max(0, self.size_before_bytes - self.size_after_bytes)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rows_deleted": self.rows_deleted,
            "size_before_bytes": self.size_before_bytes,
            "size_after_bytes": self.size_after_bytes,
            "bytes_reclaimed": self.bytes_reclaimed,
            "vacuumed": self.vacuumed,
            "duration_ms": round(self.duration_ms, 2),
            "error": self.error,
        }


class DbCompactor:
    """
    Prunes old completed/failed job rows and runs VACUUM on a SQLite database.

    The database is expected to have a ``jobs`` table with at least:
      - ``id``  TEXT PRIMARY KEY
      - ``status``  TEXT  (values: "done" | "failed" | "queued" | "running")
      - ``updated_at``  REAL  (Unix timestamp)

    If the table does not exist yet, ``ensure_schema()`` creates a minimal one.
    """

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)

    # ------------------------------------------------------------------
    # Schema bootstrap
    # ------------------------------------------------------------------

    def ensure_schema(self) -> None:
        """Create a minimal jobs table if it doesn't exist."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id          TEXT PRIMARY KEY,
                    status      TEXT NOT NULL DEFAULT 'queued',
                    updated_at  REAL NOT NULL DEFAULT (cast(strftime('%s', 'now') as real))
                )
            """)
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def prune(
        self,
        keep_statuses: tuple = ("queued", "running"),
        older_than_days: float = 30.0,
        run_vacuum: bool = True,
    ) -> PruneResult:
        """
        Delete terminal (done/failed) job rows older than *older_than_days*.

        Args:
            keep_statuses: Statuses that are never deleted.
            older_than_days: Remove rows with updated_at older than this.
            run_vacuum: Whether to call VACUUM after deletion.

        Returns:
            ``PruneResult`` with counts and file size delta.
        """
        result = PruneResult()
        t0 = time.monotonic()
        try:
            self.ensure_schema()
            cutoff = time.time() - older_than_days * 86400
            size_before = self.db_path.stat().st_size if self.db_path.exists() else 0
            result.size_before_bytes = size_before

            placeholders = ",".join("?" * len(keep_statuses))
            sql = (
                f"DELETE FROM jobs "
                f"WHERE status NOT IN ({placeholders}) "
                f"AND updated_at < ?"
            )
            conn = sqlite3.connect(self.db_path)
            try:
                cur = conn.execute(sql, (*keep_statuses, cutoff))
                result.rows_deleted = cur.rowcount
                conn.commit()
            finally:
                conn.close()

            if run_vacuum:
                # VACUUM must run outside a transaction
                conn2 = sqlite3.connect(self.db_path)
                try:
                    conn2.execute("VACUUM")
                    conn2.commit()
                    result.vacuumed = True
                finally:
                    conn2.close()

            result.size_after_bytes = self.db_path.stat().st_size if self.db_path.exists() else 0
        except Exception as exc:
            result.error = str(exc)
        finally:
            result.duration_ms = (time.monotonic() - t0) * 1000
        return result

    def row_count(self, status: Optional[str] = None) -> int:
        """Return total row count, optionally filtered by status."""
        self.ensure_schema()
        conn = sqlite3.connect(self.db_path)
        try:
            if status:
                row = conn.execute(
                    "SELECT COUNT(*) FROM jobs WHERE status = ?", (status,)
                ).fetchone()
            else:
                row = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()
            return row[0]
        finally:
            conn.close()

    def insert_job(self, job_id: str, status: str, age_days: float = 0.0) -> None:
        """Helper for tests — insert a job row with a synthetic timestamp."""
        self.ensure_schema()
        updated_at = time.time() - age_days * 86400
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                "INSERT OR REPLACE INTO jobs (id, status, updated_at) VALUES (?,?,?)",
                (job_id, status, updated_at),
            )
            conn.commit()
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Cache directory compactor
# ---------------------------------------------------------------------------


@dataclass
class CacheCompactResult:
    files_removed: int = 0
    bytes_removed: int = 0
    duration_ms: float = 0.0
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "files_removed": self.files_removed,
            "bytes_removed": self.bytes_removed,
            "duration_ms": round(self.duration_ms, 2),
            "error": self.error,
        }


class CacheCompactor:
    """
    Removes stale files from a cache directory.

    Files are candidates for deletion when:
      - They are older than *max_age_days*, OR
      - The total cache size exceeds *max_size_bytes* (oldest files removed first).

    Files matching *protected_suffixes* are never deleted.
    """

    def __init__(
        self,
        cache_dir: Path,
        max_age_days: float = 7.0,
        max_size_bytes: int = 512 * 1024 * 1024,  # 512 MB
        protected_suffixes: tuple = (".lock", ".active"),
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.max_age_days = max_age_days
        self.max_size_bytes = max_size_bytes
        self.protected_suffixes = protected_suffixes

    def compact(self) -> CacheCompactResult:
        result = CacheCompactResult()
        t0 = time.monotonic()
        try:
            if not self.cache_dir.exists():
                return result

            cutoff = time.time() - self.max_age_days * 86400
            # Collect all non-protected files with mtime
            candidates: List[tuple] = []
            for f in self.cache_dir.rglob("*"):
                if not f.is_file():
                    continue
                if any(f.name.endswith(s) for s in self.protected_suffixes):
                    continue
                try:
                    st = f.stat()
                    candidates.append((st.st_mtime, st.st_size, f))
                except OSError:
                    pass

            # Phase 1: remove files older than max_age_days
            remaining: List[tuple] = []
            for mtime, size, f in candidates:
                if mtime < cutoff:
                    try:
                        f.unlink()
                        result.files_removed += 1
                        result.bytes_removed += size
                    except OSError:
                        remaining.append((mtime, size, f))
                else:
                    remaining.append((mtime, size, f))

            # Phase 2: enforce size quota (oldest first)
            remaining.sort(key=lambda x: x[0])  # oldest first
            total = sum(s for _, s, _ in remaining)
            for mtime, size, f in remaining:
                if total <= self.max_size_bytes:
                    break
                try:
                    f.unlink()
                    result.files_removed += 1
                    result.bytes_removed += size
                    total -= size
                except OSError:
                    pass

        except Exception as exc:
            result.error = str(exc)
        finally:
            result.duration_ms = (time.monotonic() - t0) * 1000
        return result

    def total_size(self) -> int:
        """Return current total cache size in bytes."""
        if not self.cache_dir.exists():
            return 0
        return sum(
            f.stat().st_size
            for f in self.cache_dir.rglob("*")
            if f.is_file()
        )


@dataclass
class MaintenanceResult:
    """Combined database and cache maintenance summary."""

    db: PruneResult
    cache: CacheCompactResult

    def to_dict(self) -> Dict[str, Any]:
        return {"db": self.db.to_dict(), "cache": self.cache.to_dict()}


def run_local_maintenance(
    db_path: Path,
    cache_dir: Path,
    *,
    older_than_days: float = 30.0,
    max_cache_age_days: float = 7.0,
    max_cache_size_bytes: int = 512 * 1024 * 1024,
) -> MaintenanceResult:
    """Run the local SQLite/job cache maintenance workflow."""

    db_result = DbCompactor(db_path).prune(older_than_days=older_than_days)
    cache_result = CacheCompactor(
        cache_dir,
        max_age_days=max_cache_age_days,
        max_size_bytes=max_cache_size_bytes,
    ).compact()
    return MaintenanceResult(db=db_result, cache=cache_result)
