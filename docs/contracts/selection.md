# Selection & merge contract

The format-selection policy is intentionally small and testable. It lives in
`backend/ytdlp.py` (`video_selector`, `audio_selector`, `resolve_merge_format`)
and is covered by `tests/backend/test_selectors.py`.

## Selectors

| Mode | Selector | Meaning |
|------|----------|---------|
| Video + Audio | `bv*[height<=CAP]+ba/b` | Best video within the cap, best audio, falling back to a progressive format |
| Video Only | `bv*[height<=CAP]/b` | Best video-only stream, falling back to any video |
| Audio Only | `ba/b/bv*` | Best audio, falling back to a progressive/combined stream |

`CAP` comes from `AppConfig.quality_cap` (default `1080`). A cap of `0` (or a
selected format id) removes the height filter, so yt-dlp picks the best stream.

The fallback chain is **progressive-first**: if separate video/audio streams
cannot be merged, `bv*+ba/b` selects the best combined format instead of
failing. This is deliberately kept even when a cap is active.

## Merge container

`AppConfig.container` accepts `mkv`, `mp4`, or `auto` (stored as `""`).

- `auto` passes no `--merge-output-format`.
- `mp4` is always honored as-is.
- `mkv` is the **default preference**, not a hard lock: it falls back to
  `mp4` when the selected video is an mp4/m4v stream with an AVC/HEVC/AV1
  codec and the audio is AAC/MP4A/ALAC. This avoids a needless remux for the
  common YouTube `137 + 140` case while keeping mkv for codecs it cannot
  hold (e.g. VP9/Opus can technically live in mp4, but mkv is the safer
  default). A strict "always mkv" switch does not exist yet.

Audio-only downloads ignore the merge container entirely.

## Safety and reproducibility

Every probe and download command includes:

- `--ignore-config`
- `--no-config-locations`
- `--no-exec`

`--no-call-home` is **not** a real yt-dlp option (it was removed upstream), so
we do not pass it. `--no-config-locations` already prevents user/site config
files from injecting flags or post-processors.

## Size units

All sizes and speeds use **binary units** (`1 KiB = 1024 B`) and display
`KiB`/`MiB`/`GiB`/`TiB`. This matches yt-dlp's byte counts without pretending
they are decimal SI units. `human_size`/`human_speed` are the single formatting
path used by the format table and the download dashboard.
