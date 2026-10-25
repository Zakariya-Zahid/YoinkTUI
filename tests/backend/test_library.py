"""History store lifecycle, search, and interrupted recovery."""

from __future__ import annotations

from pathlib import Path

from yoinktui.backend.library import LibraryStore
from yoinktui.backend.queue import QueueItem


def _item(url: str = "https://example.com/v", title: str = "Demo") -> QueueItem:
    return QueueItem(
        url=url,
        title=title,
        selector="137",
        merge_format="mp4",
        mode="video",
    )


def test_record_start_finish_and_list(tmp_path: Path) -> None:
    store = LibraryStore(tmp_path / "library.db")
    try:
        record_id = store.record_start(_item())
        records = store.list_records()
        assert len(records) == 1
        assert records[0].status == "running"
        assert records[0].title == "Demo"

        store.record_finish(
            record_id,
            status="done",
            path="/tmp/demo.mp4",
            size=1234,
            duration_s=2.5,
            avg_speed=493.6,
        )
        record = store.get(record_id)
        assert record is not None
        assert record.status == "done"
        assert record.path == "/tmp/demo.mp4"
        assert record.size == 1234
        assert record.duration_s == 2.5
        assert record.avg_speed == 493.6
        assert store.stats()["done"] == 1
    finally:
        store.close()


def test_search_and_delete(tmp_path: Path) -> None:
    store = LibraryStore(tmp_path / "library.db")
    try:
        first = store.record_start(_item("https://example.com/a", "Alpha"))
        store.record_start(_item("https://example.com/b", "Beta"))
        assert [r.title for r in store.list_records("alpha")] == ["Alpha"]
        assert [r.title for r in store.list_records("example.com/b")] == ["Beta"]
        store.delete(first)
        assert [r.title for r in store.list_records()] == ["Beta"]
    finally:
        store.close()


def test_mark_interrupted_updates_running_rows(tmp_path: Path) -> None:
    store = LibraryStore(tmp_path / "library.db")
    try:
        running = store.record_start(_item())
        store.record_finish(
            store.record_start(_item("https://example.com/b", "Done")),
            status="done",
        )
        assert store.mark_interrupted() == 1
        record = store.get(running)
        assert record is not None
        assert record.status == "interrupted"
        assert "Interrupted" in record.error_reason
        assert store.mark_interrupted() == 0
    finally:
        store.close()


def test_schema_is_versioned(tmp_path: Path) -> None:
    import sqlite3

    path = tmp_path / "library.db"
    store = LibraryStore(path)
    store.close()
    conn = sqlite3.connect(path)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
    finally:
        conn.close()


def test_memory_store_is_supported() -> None:
    store = LibraryStore(":memory:")
    try:
        record_id = store.record_start(_item())
        assert store.get(record_id) is not None
    finally:
        store.close()
