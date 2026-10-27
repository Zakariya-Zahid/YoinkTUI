# Module 01 — Download Engine

> Status: 🟡 P0 complete (v0.2.0) · Phase: 1 · Primary files: `src/yoinktui/backend/ytdlp.py`
>
> Remaining unchecked items are P2 polish (chapters, SponsorBlock,
> post-download verification, optional postprocessing heartbeat).

## 1. Purpose

Own everything about **running a download**: building the `yt-dlp` command,
selecting formats, streaming progress events, pause/resume/cancel, post-processing,
and mapping failures to typed errors. This is the module that must be usable
without any TUI.

## 2. Current state

- `download()` is a generator streaming typed `ProgressEvent`s.
- `--progress-template` emits `DL|status|downloaded|total|total_estimate|speed|eta`
  plus `PP|…` and `FINAL|…` lines; the field order is frozen in
  `docs/contracts/progress.md`.
- `DownloadControl` implements real pause/resume/cancel via POSIX
  `SIGSTOP`/`SIGCONT`/`SIGTERM` on the process group (`start_new_session=True`).
- Format helpers `video_selector()` / `audio_selector()` build `-f` expressions;
  `resolve_merge_format()` falls back from mkv to mp4 for mp4/aac streams
  (documented in `docs/contracts/selection.md`).
- `Section` + `parse_timecode()` support clip downloads via
  `--download-sections` and optional `--force-keyframes-at-cuts`.
- Section downloads use a file-size progress fallback because yt-dlp's
  range downloader does not emit normal live progress hooks.
- `check_dependencies()` runs at app startup and via `yoinktui --doctor`;
  missing tools open `StartupErrorScreen` instead of a traceback.
- Commands add `--ignore-config`, `--no-config-locations`, `--no-exec`, kill the
  process group on cancel, detect stalls, and retry transient failures.
- All policy (cap, container, audio codec, fragments, rate limit, subtitles,
  metadata/thumbnail embedding, keep-original) is config-driven (module 07).
- Failures are typed (`DownloadError` + `ErrorReason`) with hints/actions.
- Sizes/speeds use binary units (KiB/MiB/GiB) everywhere.
- Site-specific workflow notes live in `docs/guides/udemy.md` (cookies,
  browser impersonation, legacy lecture URLs, and DRM limits).

## 3. Goals

- A dependable, headless, cancellable download engine with typed errors.
- All download policy (container, codec, cap, retries, concurrency) is data.
- Deterministic, testable progress parsing.

**Non-goals:** extraction/metadata (module 02), presentation (modules 03–05).

## 4. Workstreams

### WS 01.1 — Process lifecycle & robustness — **[P0]**
- [x] Add startup dependency check (`yt-dlp`, `ffmpeg`) using `tool_available`,
      surfaced as a friendly pre-flight error before any screen opens.
- [x] Capture and expose yt-dlp/ffmpeg **versions**; warn when yt-dlp is old.
- [x] Guarantee no orphan processes: terminate the whole group in `finally`.
- [x] Add `--no-exec` and `--no-config-locations` to the command for
      safety/reproducibility. (`--no-call-home` no longer exists upstream.)
- [x] Timeouts: overall stall detection (no output for N seconds → error).
- [x] Retries with backoff for transient network failures.

### WS 01.2 — Selection policy as data — **[P0]**
- [x] Replace hardcoded `1080` cap with `AppConfig.quality_cap` (module 07).
- [x] Replace hardcoded `merge_format="mkv"` / `audio_format="mp3"` with config.
- [x] Add container preference fallback (`mkv` → `mp4` when streams are mp4/aac).
- [x] Expose fragment concurrency / rate limit (`--concurrent-fragments`,
      `--limit-rate`) as options.
- [x] Keep the progressive fallback chain (`bv*+ba/b`) and document it
      (`docs/contracts/selection.md`).

### WS 01.3 — Progress contract — **[P0]**
- [x] Freeze the progress template as a documented **contract**
      (`docs/contracts/progress.md`) with field order + example lines.
- [x] Add parser tests for every field combination (module 10).
- [x] Keep decimal vs binary size formatting consistent across the app (binary).
- [x] Handle `downloaded == 0` / `total == 0` / `speed == NA` gracefully.
- [ ] Optional: emit a heartbeat when yt-dlp is silent (postprocessing).

### WS 01.4 — Failure taxonomy — **[P1]**
- [x] Introduce a `DownloadError` enum (`NETWORK`, `GEO`, `AUTH`, `NOT_FOUND`,
      `DISK`, `FFMPEG_MISSING`, `CANCELLED`, `UNKNOWN`) derived from stderr.
- [x] Each reason carries a `hint` and a suggested `action` (retry / login / …).
- [x] Replace bare `BackendError(str)` raised sites with typed errors.

### WS 01.5 — Extended capabilities — **[P2]**
- [x] Resume interrupted downloads (`--continue` / `.part` handling) + the
      queue screen's resume affordance.
- [x] Subtitles (`--write-subs`), metadata embed, thumbnail embed.
- [ ] Chapters and SponsorBlock.
- [x] Cookies file / cookies-from-browser, proxy, and playlist opt-in (`--yes-playlist`).
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
