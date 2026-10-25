# Changelog

All notable changes to YoinkTUI are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] — "Power user" — unreleased (internal milestone)

Phase 2 "power user" work. This version is an internal development milestone;
the first public release remains v1.0.0.

### Added

- Persistent, sequential download queue (`backend/queue.py`) with item
  statuses, per-item policy snapshots, atomic JSON persistence, and automatic
  interrupted-state recovery after a restart.
- `QueueScreen` for reviewing, retrying, removing, and starting queued items;
  `DownloadScreen` now renders a multi-item dashboard with per-item status and
  the current item's stream progress.
- Playlist expansion via a fast `--flat-playlist` probe and `PlaylistScreen`
  for queueing every entry.
- Playlist queue modes: Video+Audio, Video Only, and Audio Only. “Queue all”
  applies the selected mode to every playlist entry.
- Udemy workflow guide covering cookie export, browser impersonation, legacy
  lecture URLs, whole-course playlist queueing, audio-only mode, and DRM
  limitations.
- SQLite download history (`backend/library.py`) with WAL mode, searchable
  records, status/size/path metadata, and interrupted-run recovery.
- `LibraryScreen` with search, details, open file/folder, copy URL, re-download,
  and delete actions.
- Built-in `music`, `archive`, and `mobile` presets plus user-defined
  `[presets.<name>]` tables; `PresetModal` applies a preset from the format
  screen and the action bar shows the active profile.
- `--continue` for resumable `.part` downloads, queue resume on startup, and
  history records for running, completed, failed, cancelled, and interrupted
  downloads.
- Snapshot coverage for every screen: URL, format, download, multi-item
  download, queue, library, playlist, preset modal, clip modal, startup error,
  and error modal, across two themes and two terminal sizes.
- Backend tests for queue serialization, resume, history, presets, and playlist
  probing.

### Changed

- `AppState` now owns the persistent `DownloadQueue`; the app owns the history
  store and queue store.
- `DownloadScreen` processes a list of queue items sequentially and continues
  after an individual item fails.
- Config serialization includes the preset tables so `--print-config` and
  `--write-default-config` document the full effective policy.
- `UrlScreen` exposes Playlist, Queue, and Library entry points.
- Data and history live under `$XDG_DATA_HOME/yoinktui/`; the queue survives a
  restart and offers to resume pending, interrupted, or failed items.

### Fixed

- Interrupted app exits leave queued items resumable and record the active
  download as `interrupted` in history instead of losing it.
- Queue failures are reported per item without aborting the remaining items.
- Video+Audio downloads now append the best audio stream when the selected
  format is video-only, instead of saving a silent video.
- Queue and download actions now use the highlighted format row, so clicking a
  format such as 360p before queueing no longer falls back to the initial
  best-quality default.
- Header and Footer now render on the main screens; their borders previously
  consumed their entire one-row height.
- User-controlled titles and URLs render literally, including uppercase
  bracket tags such as `[Official Video]`, instead of being parsed as markup.
- The clip modal no longer overlaps the precise-cut switch at 100×30, and the
  library table fits without a horizontal scrollbar.

## [0.2.0] — "Trustworthy" — 2026-10-23

Phase 0/1 reliability release. All P0 work for modules 01, 02, 03, 07, 10,
and 11 is in place.

### Added

- `config.toml` support at `$XDG_CONFIG_HOME/yoinktui/config.toml` with
  validated `[general]`, `[download]`, `[network]`, and `[ui]` sections.
- Configuration precedence: CLI flags > `YOINKTUI_*` environment variables >
  config file > built-in defaults.
- CLI flags `--config`, `--print-config`, `--write-default-config`,
  `--doctor`, `--quality-cap`, `--container`, `--audio-format`,
  `--audio-quality`, `--concurrent-fragments`, `--rate-limit`,
  `--default-mode`, `--theme`, `--ascii`, and `--no-color`.
- `yoinktui --doctor` pre-flight report for yt-dlp/ffmpeg, config, and
  download-directory writability.
- Typed backend errors (`DownloadError` + `ErrorReason`) with hints and
  suggested actions for network, geo, auth, not-found, disk, ffmpeg, and
  unsupported-site failures.
- Startup dependency check: missing yt-dlp/ffmpeg shows a friendly screen
  instead of a traceback.
- Probe cancellation/timeout support and a cancellable `probe()` API.
- Download stall detection, process-group cleanup, and bounded retries with
  backoff for transient network failures.
- Container fallback from mkv to mp4 for mp4/aac streams, documented in
  `docs/contracts/selection.md`.
- Per-instance `AppState`, URL validation, duplicate-submit guards, inline
  probe errors, and last-URL persistence across launches.
- Test suite (153 unit/parser/config/error/control/CLI/packaging/TUI tests,
  including 24 SVG snapshots across two themes and two terminal sizes) plus
  GitHub Actions CI on Linux and macOS and a wheel-install packaging job.
- Package metadata: single-source version via `importlib.metadata`,
  classifiers, keywords, license, changelog, and project URLs.

### Changed

- Download policy is now data: quality cap, container, audio format/quality,
  fragment concurrency, rate limit, subtitles, metadata, thumbnail, and
  keep-original options come from config/CLI instead of hardcoded constants.
- yt-dlp commands now pass `--no-config-locations` and `--no-exec`.
- Sizes and speeds consistently use binary units (KiB/MiB/GiB).
- `UrlScreen` shows inline errors and disables the input while probing instead
  of stacking error modals.
- The README documents the real backend/TUI architecture and config workflow.

### Fixed

- No orphaned yt-dlp/ffmpeg processes after cancel/quitting.
- Numeric metadata coercion for `"NA"`, `null`, zero, and non-finite values.
- `upload_date`/`duration` rendered as human labels in the info panel.

## [0.1.0] — 2026-10

### Added

- Initial TUI: URL entry, format picker, download dashboard, and completion
  flow.
- Steam-style dashboard with per-stream queue, speed/ETA/peak/disk tiles,
  overall progress, and activity log.
- Real POSIX pause/resume/cancel via process groups.
- Clip downloads with start/end ranges and precise cuts.
- Thumbnail rendering through `textual-image`.
- Cookies, proxy, and extra yt-dlp argument passthrough.

[0.2.0]: https://github.com/Zakariya-Zahid/YoinkTUI/compare/v0.1.0...v0.2.0
