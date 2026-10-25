# ADR 0001 — SQLite for download history

- **Status:** accepted
- **Date:** 2026-10-25
- **Context:** v0.3.0 adds persistent download history, search, and library
  actions. The queue is a separate, small, transient list.

## Decision

Store history in SQLite at `$XDG_DATA_HOME/yoinktui/library.db`.

- One `downloads` table with the fields documented in module 08.
- WAL mode plus a process-local `RLock`; one connection shared by the UI and
  the download worker (`check_same_thread=False`).
- `PRAGMA user_version` is the schema version. Version 1 is the initial schema.
- The queue remains JSON at `$XDG_DATA_HOME/yoinktui/queue.json`: it is a small
  ordered list, human-inspectable, and rewritten atomically after each state
  change.

## Why not JSONL for history?

Searching, sorting, updating a running record, and aggregate statistics are
awkward and slow with an append-only log. SQLite gives those operations without
adding a server or a dependency (`sqlite3` is in the standard library).

## Why not SQLite for the queue?

The queue is tiny and order-sensitive. JSON keeps it easy to inspect, back up,
and recover after a crash, and avoids coupling queue writes to the history
schema.

## Consequences

- History survives restarts and can be queried without loading everything.
- A corrupted database is isolated from the queue; the app falls back to an
  in-memory history store if opening the file fails.
- Future schema changes must bump `user_version` and add a migration before
  reading older databases.
