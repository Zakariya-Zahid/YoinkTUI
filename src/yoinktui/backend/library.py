"""SQLite-backed download history and library queries.

The store is small on purpose: one table, one connection guarded by a lock.
Downloads can write from a worker thread while the library screen reads from
the UI thread; SQLite's WAL mode keeps those operations cheap.
"""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from yoinktui.backend.config import data_dir
from yoinktui.backend.queue import QueueItem

HistoryStatus = Literal["running", "done", "failed", "cancelled", "interrupted"]

_SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS downloads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    uploader TEXT NOT NULL DEFAULT '',
    format_id TEXT NOT NULL DEFAULT '',
    container TEXT NOT NULL DEFAULT '',
    path TEXT NOT NULL DEFAULT '',
    size REAL,
    status TEXT NOT NULL DEFAULT 'pending',
    started_at TEXT NOT NULL,
    finished_at TEXT,
    duration_s REAL,
    avg_speed REAL,
    error_reason TEXT NOT NULL DEFAULT '',
    mode TEXT NOT NULL DEFAULT '',
    section TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_downloads_started ON downloads(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_downloads_status ON downloads(status);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _section_text(item: QueueItem) -> str:
    if item.section is None:
        return ""
    end = "end" if item.section.end is None else f"{item.section.end:g}"
    return f"{item.section.start:g}-{end}"


@dataclass(frozen=True, slots=True)
class HistoryRecord:
    id: int
    url: str
    title: str
    uploader: str = ""
    format_id: str = ""
    container: str = ""
    path: str = ""
    size: float | None = None
    status: str = "pending"
    started_at: str = ""
    finished_at: str | None = None
    duration_s: float | None = None
    avg_speed: float | None = None
    error_reason: str = ""
    mode: str = ""
    section: str = ""

    @property
    def display_title(self) -> str:
        return self.title or self.url or "Untitled"

    @property
    def is_finished(self) -> bool:
        return self.status in ("done", "failed", "cancelled", "interrupted")


class LibraryStore:
    """Thread-safe history store with a versioned schema."""

    def __init__(self, path: Path | str | None = None) -> None:
        if path is None:
            path = data_dir() / "library.db"
        if str(path) != ":memory:":
            path = Path(path).expanduser()
        self.path = path
        self._lock = threading.RLock()
        if isinstance(path, Path):
            path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.executescript(_SCHEMA)
            self._conn.execute(f"PRAGMA user_version={_SCHEMA_VERSION}")
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # -- writes -----------------------------------------------------------

    def record_start(self, item: QueueItem, *, title: str | None = None) -> int:
        """Insert a running record and return its id."""
        with self._lock:
            cursor = self._conn.execute(
                """
                INSERT INTO downloads
                    (url, title, uploader, format_id, container, status,
                     started_at, mode, section)
                VALUES (?, ?, ?, ?, ?, 'running', ?, ?, ?)
                """,
                (
                    item.url,
                    title if title is not None else item.display_title,
                    item.uploader,
                    item.selector,
                    item.merge_format,
                    _now(),
                    item.mode,
                    _section_text(item),
                ),
            )
            self._conn.commit()
            return int(cursor.lastrowid or 0)

    def record_finish(
        self,
        record_id: int,
        *,
        status: HistoryStatus = "done",
        path: str = "",
        size: float | None = None,
        error: str = "",
        duration_s: float | None = None,
        avg_speed: float | None = None,
    ) -> None:
        with self._lock:
            self._conn.execute(
                """
                UPDATE downloads
                SET status = ?, path = ?, size = ?, finished_at = ?,
                    error_reason = ?, duration_s = ?, avg_speed = ?
                WHERE id = ?
                """,
                (
                    status,
                    path,
                    size,
                    _now(),
                    error,
                    duration_s,
                    avg_speed,
                    record_id,
                ),
            )
            self._conn.commit()

    def mark_interrupted(self) -> int:
        """Mark records left running by a previous process as interrupted."""
        with self._lock:
            cursor = self._conn.execute(
                """
                UPDATE downloads
                SET status = 'interrupted', finished_at = ?,
                    error_reason = 'Interrupted before completion'
                WHERE status = 'running'
                """,
                (_now(),),
            )
            self._conn.commit()
            return int(cursor.rowcount or 0)

    def delete(self, record_id: int) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM downloads WHERE id = ?", (record_id,))
            self._conn.commit()

    # -- reads ------------------------------------------------------------

    def list_records(self, query: str = "", *, limit: int = 500) -> list[HistoryRecord]:
        needle = f"%{query.strip()}%"
        with self._lock:
            if query.strip():
                rows = self._conn.execute(
                    """
                    SELECT * FROM downloads
                    WHERE title LIKE ? OR url LIKE ? OR uploader LIKE ?
                    ORDER BY started_at DESC, id DESC
                    LIMIT ?
                    """,
                    (needle, needle, needle, limit),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    """
                    SELECT * FROM downloads
                    ORDER BY started_at DESC, id DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
        return [self._row(row) for row in rows]

    def get(self, record_id: int) -> HistoryRecord | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM downloads WHERE id = ?", (record_id,)
            ).fetchone()
        return self._row(row) if row is not None else None

    def stats(self) -> dict[str, Any]:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT COUNT(*) AS total,
                       COALESCE(SUM(CASE WHEN status = 'done' THEN 1 ELSE 0 END), 0) AS done,
                       COALESCE(SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END), 0) AS failed,
                       COALESCE(SUM(CASE WHEN status = 'interrupted' THEN 1 ELSE 0 END), 0)
                           AS interrupted,
                       COALESCE(SUM(size), 0) AS bytes
                FROM downloads
                """
            ).fetchone()
        return dict(row) if row is not None else {}

    @staticmethod
    def _row(row: sqlite3.Row) -> HistoryRecord:
        return HistoryRecord(
            id=int(row["id"]),
            url=str(row["url"] or ""),
            title=str(row["title"] or ""),
            uploader=str(row["uploader"] or ""),
            format_id=str(row["format_id"] or ""),
            container=str(row["container"] or ""),
            path=str(row["path"] or ""),
            size=float(row["size"]) if row["size"] is not None else None,
            status=str(row["status"] or "pending"),
            started_at=str(row["started_at"] or ""),
            finished_at=str(row["finished_at"]) if row["finished_at"] else None,
            duration_s=float(row["duration_s"]) if row["duration_s"] is not None else None,
            avg_speed=float(row["avg_speed"]) if row["avg_speed"] is not None else None,
            error_reason=str(row["error_reason"] or ""),
            mode=str(row["mode"] or ""),
            section=str(row["section"] or ""),
        )


__all__ = ["HistoryRecord", "HistoryStatus", "LibraryStore"]
