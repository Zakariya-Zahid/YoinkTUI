# Module 05 — Download Manager & Queue

> Status: 🟡 in progress · Phase: 2 · Primary files: `tui/widgets.py`
> (`DownloadDashboard`, `DownloadQueueItem`, `StatTile`), `tui/screens.py`
> (`DownloadScreen`)

## 1. Purpose

Own the **download experience**: the Steam-style dashboard, per-stream queue,
live stats, pause/resume/cancel, completion, and (later) multi-item queues.

## 2. Current state

- `DownloadScreen` hosts `DownloadDashboard`: header + status pill, per-stream
  `DownloadQueueItem` rows with mini progress bars, 5 `StatTile`s
  (SPEED/ETA/PEAK/ELAPSED/DISK FREE), overall progress bar, and an activity log.
- Controls: Pause/Resume + Cancel buttons, `P`/`Space`/`Esc` bindings.
- States: CONNECTING → DOWNLOADING → PAUSED → PROCESSING → COMPLETE/FAILED.
- Two-pass (video then audio) overall progress; audio-only single pass.
- On completion: `Cancel` becomes `Close`, auto-dismiss after 6 s.
- One download at a time; no queue, no history write, no notifications.

## 3. Goals

- A reliable, single-item download manager (done, keeps improving).
- A **queue** for multiple items (playlists, batch selections).
- Clean hand-off to the library/history module.

**Non-goals:** engine policy (01), format choice (04).

## 4. Workstreams

### WS 05.1 — Single-item polish — **[P0]**
- [ ] Pause button disabled while `PROCESSING` (no-op today is confusing).
- [ ] Speed sparkline / history for the last N seconds (visual rate context).
- [ ] "Open folder" / "Copy path" actions on completion.
- [ ] Persist the last download result into history (module 08).
- [ ] Keep elapsed ticking consistent with real progress; freeze on pause if desired.

### WS 05.2 — Queue model — **[P1]**
- [ ] `DownloadQueue` in the shell/backend with items: pending/running/done/failed.
- [ ] One worker processes items sequentially; per-item retry/skip/cancel.
- [ ] Queue-aware dashboard: item list with statuses, current item highlighted.
- [ ] Playlist expansion (`--yes-playlist`) feeding the queue.
- [ ] Persist the queue so an interrupted app can resume (module 08).

### WS 05.3 — Controls & automation — **[P1]**
- [ ] Optional concurrency (N active items) with a global vs. per-item limit.
- [ ] Global rate limit / scheduled start / "download later".
- [ ] Notifications on completion (desktop notify, module 09 hook).
- [ ] Keyboard: reorder queue, retry all failed, clear finished.

### WS 05.4 — Diagnostics in the dashboard — **[P2]**
- [ ] Show the exact yt-dlp command (debug panel, opt-in).
- [ ] Show selected format id / container / output path.
- [ ] Copyable error block on failure.

## 5. Milestones

| Milestone | Scope | Exit criteria |
|-----------|-------|---------------|
| M1 — Solid single item | WS 05.1 | No dead controls; completion writes history |
| M2 — Queue | WS 05.2 | ≥ 10 items queue + playlist works, resumable |
| M3 — Automation | WS 05.3–05.4 | Concurrency, retries, notifications, debug view |

## 6. Acceptance criteria

- Pause/resume/cancel never leave a stuck dashboard or orphan process.
- A playlist of N items downloads sequentially with correct per-item status.
- Queue survives an app restart (resume within history module).

## 7. Dependencies

- Module 01 (control/events), 03 (state), 08 (persistence), 09 (notify hook).

## 8. Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Queue state vs. UI drift | Single `DownloadQueue` owner; UI renders only |
| Concurrency complicates pause | Start sequential; add concurrency behind a flag |
| Large playlists | Cap + streaming add, virtualised list |

## 9. Metrics

- Median keystrokes to start a download.
- Queue completion rate; retry rate; per-item failure reasons.

## 10. Open questions

- Should finished items auto-dismiss from the dashboard or stay in a list?
- Do we allow reordering on completion or only while pending?
