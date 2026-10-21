# Module 01 — Download Engine

> Status: 🟡 in progress · Phase: 1 · Primary files: `src/yoinktui/backend/ytdlp.py`

## 1. Purpose

Own everything about **running a download**: building the `yt-dlp` command,
selecting formats, streaming progress events, pause/resume/cancel, post-processing,
and mapping failures to typed errors. This is the module that must be usable
without any TUI.

## 2. Current state

- `download()` is a generator streaming typed `ProgressEvent`s.
- `--progress-template` emits `DL|status|downloaded|total|total_estimate|speed|eta`
  (fixed field-shift bug) plus `PP|…` and `FINAL|…` lines.
- `DownloadControl` implements real pause/resume/cancel via POSIX
  `SIGSTOP`/`SIGCONT`/`SIGTERM` on the process group (`start_new_session=True`).
- Format helpers `video_selector()` / `audio_selector()` build `-f` expressions.
- `tool_available()` exists but is **never called**.
- Always `--ignore-config`, `--no-playlist`; container `mkv` and audio `mp3`
  are **hardcoded**; 1080p cap hardcoded in `FormatScreen._start_download`.

## 3. Goals

- A dependable, headless, cancellable download engine with typed errors.
- All download policy (container, codec, cap, retries, concurrency) is data.
- Deterministic, testable progress parsing.

**Non-goals:** extraction/metadata (module 02), presentation (modules 03–05).

## 4. Workstreams

### WS 01.1 — Process lifecycle & robustness — **[P0]**
- [ ] Add startup dependency check (`yt-dlp`, `ffmpeg`) using `tool_available`,
      surfaced as a friendly pre-flight error before any screen opens.
- [ ] Capture and expose yt-dlp/ffmpeg **versions**; warn when yt-dlp is old.
- [ ] Guarantee no orphan processes: terminate the whole group in `finally`.
- [ ] Add `--no-exec`, `--no-call-home` (and `--no-config-locations` equivalents)
      to the command for safety/reproducibility.
- [ ] Timeouts: overall stall detection (no output for N seconds → error).
- [ ] Retries with backoff for transient network failures.

### WS 01.2 — Selection policy as data — **[P0]**
- [ ] Replace hardcoded `1080` cap with `AppConfig.quality_cap` (module 07).
- [ ] Replace hardcoded `merge_format="mkv"` / `audio_format="mp3"` with config.
- [ ] Add container preference fallback (`mkv` → `mp4` when streams are mp4/aac).
- [ ] Expose fragment concurrency / rate limit (`--concurrent-fragments`,
      `--limit-rate`) as options.
- [ ] Keep the progressive fallback chain (`bv*+ba/b`) and document it.

### WS 01.3 — Progress contract — **[P0]**
- [ ] Freeze the progress template as a documented **contract**
      (`docs/contracts/progress.md`) with field order + example lines.
- [ ] Add parser tests for every field combination (module 10).
- [ ] Keep decimal vs binary size formatting consistent across the app (pick one).
- [ ] Handle `downloaded == 0` / `total == 0` / `speed == NA` gracefully.
- [ ] Optional: emit a heartbeat when yt-dlp is silent (postprocessing).

### WS 01.4 — Failure taxonomy — **[P1]**
- [ ] Introduce a `DownloadError` enum (`NETWORK`, `GEO`, `AUTH`, `NOT_FOUND`,
      `DISK`, `FFMPEG_MISSING`, `CANCELLED`, `UNKNOWN`) derived from stderr.
- [ ] Each reason carries a `hint` and a suggested `action` (retry / login / …).
- [ ] Replace bare `BackendError(str)` raised sites with typed errors.

### WS 01.5 — Extended capabilities — **[P2]**
- [ ] Resume interrupted downloads (`-c` / `.part` handling) + UI affordance.
- [ ] Subtitles (`--write-subs`), chapters, metadata embed, thumbnail embed.
- [ ] SponsorBlock, cookies-from-browser, proxy, and playlist opt-in.
- [ ] Post-download verification (checksum/ffprobe) as an optional step.

## 5. Milestones

| Milestone | Scope | Exit criteria |
|-----------|-------|---------------|
| M1 — Safe pre-flight | WS 01.1 startup checks | Missing deps produce a clear modal, never a traceback |
| M2 — Config-driven | WS 01.2 | No hardcoded cap/container/codec in code paths |
| M3 — Contract-tested | WS 01.3 | Parser tests cover 100% fields; CI enforces |
| M4 — Typed errors | WS 01.4 | UI shows reason + suggested action for every failure |

## 6. Acceptance criteria

- `download()` never leaves a zombie process, even on cancel while paused.
- Killing the app mid-download stops yt-dlp and ffmpeg.
- Speed/ETA shown by the UI match yt-dlp's own output within ±10%.
- The engine can be driven from a plain Python script with no Textual import.

## 7. Dependencies

- Module 07 (Config) for policy values.
- Module 10 (Quality) for parser/contract tests.
- Module 12 (Diagnostics) for logging + version reporting.

## 8. Risks & mitigations

| Risk | Mitigation |
|------|------------|
| yt-dlp template field renames | Contract tests + version guard + tolerant parser |
| SIGSTOP unsupported (Windows) | `DownloadControl.supported` guard; document limitation |
| ffmpeg missing mid-postprocess | Detect at pre-flight; typed `FFMPEG_MISSING` |
| Long-running stall | Heartbeat + stall timeout |

## 9. Metrics

- Download success rate; retries per download.
- Parser test coverage; count of untyped error paths (target 0).
- Orphaned-process incidents (target 0).

## 10. Open questions

- Do we support concurrent downloads (N workers) or strictly one at a time?
- Is `--ignore-config` right as a default, or should we layer user yt-dlp config?
