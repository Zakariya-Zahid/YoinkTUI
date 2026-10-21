# Module 08 — History, Library & Persistence

> Status: ⚪ not started · Phase: 2 · Primary files: *(new)* `backend/library.py`,
> screen `tui/screens.py` (`LibraryScreen`)

## 1. Purpose

Own **what persists between sessions**: download history, resumable queue,
last-used URL/settings, and a browse-able library of downloaded media.

## 2. Current state

- **Nothing is persisted** except files on disk.
- No history, no resume, no library screen, no recently-downloaded list.
- `DownloadScreen` forgets everything on pop.

## 3. Goals

- A durable, queryable history of downloads.
- Resume interrupted downloads and the queue after a restart.
- A library screen to find and act on past downloads.

**Non-goals:** media playback; we surface files and open them in the OS.

## 4. Workstreams

### WS 08.1 — Storage layer — **[P1]**
- [ ] Choose format for `~/.local/share/yoinktui/` — SQLite (recommended)
      or JSONL; document the decision (`docs/adr/0001-history-store.md`).
- [ ] Schema: id, url, title, uploader, format_id, container, path, size,
      status, started_at, finished_at, duration_s, avg_speed, error_reason.
- [ ] Migration/versioning; safe concurrent writes.

### WS 08.2 — Recording downloads — **[P1]**
- [ ] Write a record on start and update on finish/fail/cancel.
- [ ] Record the exact yt-dlp command + selected format for reproducibility.
- [ ] Handle moved/deleted files (verify existence lazily).

### WS 08.3 — Library screen — **[P1]**
- [ ] List with search/filter (by site, status, date), sort, and detail pane.
- [ ] Actions: open file, open folder, re-download, copy URL, delete record.
- [ ] Broken-file detection and cleanup.

### WS 08.4 — Resume & persistence of UI state — **[P2]**
- [ ] Persist the download queue and resume pending items on launch.
- [ ] Remember last URL, last mode, last profile, theme, window-ish layout.
- [ ] Offer "resume interrupted" prompt on startup.

### WS 08.5 — Stats & retention — **[P2]**
- [ ] Aggregate stats (total bytes, downloads/month) for a future insights view.
- [ ] Retention policy / vacuum; export to CSV/JSON.

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
