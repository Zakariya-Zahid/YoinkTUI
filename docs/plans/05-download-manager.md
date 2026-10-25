# Module 05 — Download Manager & Queue

> Status: 🟡 P1 queue complete (v0.3.0) · Phase: 2 · Primary files: `tui/widgets.py`
> (`DownloadDashboard`, `DownloadQueueItem`, `StatTile`), `tui/screens.py`
> (`DownloadScreen`, `QueueScreen`, `PlaylistScreen`), `backend/queue.py`
>
> Remaining unchecked items are single-item polish and P1/P2 automation.

## 1. Purpose

Own the **download experience**: the Steam-style dashboard, per-stream queue,
live stats, pause/resume/cancel, completion, and multi-item queue management.

## 2. Current state

- `DownloadScreen` hosts `DownloadDashboard`: header + status pill, per-stream
  `DownloadQueueItem` rows with mini progress bars, 5 `StatTile`s
  (SPEED/ETA/PEAK/ELAPSED/DISK FREE), overall progress bar, and an activity log.
- Controls: Pause/Resume + Cancel buttons, `P`/`Space`/`Esc` bindings.
- States: CONNECTING → DOWNLOADING → PAUSED → PROCESSING → COMPLETE/FAILED.
- Two-pass (video then audio) overall progress; audio-only single pass.
- On completion: `Cancel` becomes `Close`, auto-dismiss after 6 s.
- `DownloadScreen` accepts a list of `QueueItem`s and processes them
  sequentially; each item has its own policy snapshot and history record.
- Multi-item mode adds a queue-aware item list above the per-stream rows, with
  per-item status and current-item progress; one failure continues the queue.
- `QueueScreen` reviews, retries, removes, clears, and starts/resumes queued
  items; it supports multi-select with bulk actions for the selected rows and
  “Remove all” clears the entire queue after confirmation.
- `PlaylistScreen` queues every entry from a flat playlist probe and can apply
  Video+Audio, Video Only, or Audio Only to the whole batch. It also supports
  multi-select so only chosen entries are queued; a quality selector applies
  Best available or a resolution cap (2160p–240p) to queued entries.
- Queue state is persisted to `$XDG_DATA_HOME/yoinktui/queue.json`; running
  items become `interrupted` on restart and are offered for resume.
- Completion writes history through `LibraryStore`; pause/resume/cancel are
  still single-item controls (no per-item cancel or concurrency yet).

## 3. Goals

- A reliable, single-item download manager (done, keeps improving).
- A **queue** for multiple items (playlists, batch selections).
- Clean hand-off to the library/history module.

**Non-goals:** engine policy (01), format choice (04).

## 4. Workstreams

### WS 05.1 — Single-item polish — **[P0]**
- [x] Pause button disabled while `PROCESSING` / finished.
- [ ] Speed sparkline / history for the last N seconds (visual rate context).
- [ ] "Open folder" / "Copy path" actions on completion.
- [x] Persist the last download result into history (module 08).
- [x] Keep elapsed ticking consistent with real progress; paused time is
      excluded and the clock resets per queue item (post-processing covered).

### WS 05.2 — Queue model — **[P1]**
- [x] `DownloadQueue` in the shell/backend with items: pending/running/done/failed.
- [~] One worker processes items sequentially; failures continue the queue.
      Retry is available from `QueueScreen`; per-item skip/cancel is not.
- [x] Queue-aware dashboard: item list with statuses, current item highlighted.
- [x] Playlist expansion (`--flat-playlist` probe) feeding the queue.
- [x] Playlist queue modes (Video+Audio, Video Only, Audio Only).
- [x] Playlist quality cap (Best available, 2160p–240p).
- [x] Persist the queue so an interrupted app can resume (module 08).

### WS 05.3 — Controls & automation — **[P1]**
- [ ] Optional concurrency (N active items) with a global vs. per-item limit.
- [~] Global rate limit is config-driven; scheduled start / "download later" is not.
- [ ] Notifications on completion (desktop notify, module 09 hook).
- [~] Clear finished / remove selected / remove all / retry all failed via
      `QueueScreen`; multi-select bulk actions are implemented, keyboard
      reordering is not.

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
