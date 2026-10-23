# Changelog

All notable changes to YoinkTUI are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
