# Module 08 — History, Library & Persistence

> Status: 🟡 P1 complete (v0.3.0) · Phase: 2 · Primary files: `backend/library.py`,
> `backend/queue.py`, screen `tui/screens.py` (`LibraryScreen`, `QueueScreen`),
> `docs/adr/0001-history-store.md`
>
> Remaining unchecked items are UI-state persistence, retention/export, and
> richer library filters.

## 1. Purpose

Own **what persists between sessions**: download history, resumable queue,
last-used URL/settings, and a browse-able library of downloaded media.

## 2. Current state

- SQLite history at `$XDG_DATA_HOME/yoinktui/library.db` (WAL, versioned
  schema, one lock-guarded connection) records start/finish/fail/cancel and
  interrupted runs. See `docs/adr/0001-history-store.md`.
- The persistent queue lives at `$XDG_DATA_HOME/yoinktui/queue.json`; startup
  opens `QueueScreen` when resumable (pending/interrupted/failed) items exist.
- `LibraryScreen` lists and searches history, shows a detail pane, opens files
  or folders, copies URLs, re-downloads, and deletes records. Missing files are
  flagged lazily.
- `DownloadScreen` writes history from its worker thread, so the UI never waits
  on disk I/O. Records include URL, title, uploader, format id, container,
  path, size, status, timestamps, duration, average speed, mode, and clip.
- UI state persistence beyond the last URL/theme and retention/export are not
  implemented yet.

## 3. Goals

- A durable, queryable history of downloads.
- Resume interrupted downloads and the queue after a restart.
- A library screen to find and act on past downloads.

**Non-goals:** media playback; we surface files and open them in the OS.

## 4. Workstreams

### WS 08.1 — Storage layer — **[P1]**
- [x] Choose SQLite for `$XDG_DATA_HOME/yoinktui/`; document the decision
      (`docs/adr/0001-history-store.md`).
- [x] Schema: id, url, title, uploader, format_id, container, path, size,
      status, started_at, finished_at, duration_s, avg_speed, error_reason,
      mode, section.
- [x] Migration/versioning (`PRAGMA user_version`) and safe concurrent writes
      (WAL + `RLock`, `check_same_thread=False`).

### WS 08.2 — Recording downloads — **[P1]**
- [x] Write a record on start and update on finish/fail/cancel/interrupted.
- [~] Record the selected format, container, mode, and clip for
      reproducibility; the exact argv is not stored yet.
- [x] Handle moved/deleted files (verify existence lazily in the library).

### WS 08.3 — Library screen — **[P1]**
- [x] List with search (title/uploader/URL), newest-first sort, and detail pane.
- [x] Actions: open file, open folder, re-download, copy URL, delete record.
- [x] Broken-file detection and cleanup (delete record; no automatic file sweep).

### WS 08.4 — Resume & persistence of UI state — **[P2]**
- [x] Persist the download queue and resume pending/interrupted items on launch.
- [~] Remember last URL and theme; last mode/profile and layout are not persisted.
- [x] Offer the interrupted queue automatically on startup (`QueueScreen`).

### WS 08.5 — Stats & retention — **[P2]**
- [x] Aggregate stats backend (`total`, `done`, `failed`, `interrupted`, bytes).
- [ ] Stats UI, retention policy / vacuum, export to CSV/JSON.

## 5. Milestones

| Milestone | Scope | Exit criteria |
|-----------|-------|---------------|
| M1 — Store | WS 08.1–08.2 | Every download recorded and queryable |
| M2 — Library UI | WS 08.3 | Browse/search/act on history |
| M3 — Resume | WS 08.4–08.5 | Queue + UI state survive restart |

## 6. Acceptance criteria

- Killing the app mid-download yields a "was interrupted" record on next launch.
- Library search returns in < 50 ms for 10k records.
- History writes never block the UI thread.

## 7. Dependencies

- Module 03 (state), 05 (queue events), 07 (data path), 10 (store tests).

## 8. Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Schema churn | Versioned migrations from day one |
| PII/privacy (URLs) | Local-only, no telemetry; documented + deletable |
| DB corruption | WAL mode, backups, integrity check command |

## 9. Metrics

- Records written vs. downloads completed (should match).
- Resume success rate.

## 10. Open questions

- SQLite vs. append-only JSONL for simplicity?
- Should history be opt-in for privacy-conscious users?
