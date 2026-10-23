# Contract: yt-dlp progress stream

YoinkTUI drives yt-dlp with `--newline` and two `--progress-template` values.
This file freezes the field order. Change it only together with
`_parse_line()` and `tests/backend/test_progress_parser.py`.

## Download lines

Template:

```text
download:DL|%(progress.status)s|%(progress.downloaded_bytes)s|%(progress.total_bytes)s|%(progress.total_bytes_estimate)s|%(progress.speed)s|%(progress.eta)s
```

Field order:

| # | Field | Type | Notes |
|---|-------|------|-------|
| 0 | `DL` | literal | Record discriminator |
| 1 | `status` | string | `downloading`, `finished`, `error` |
| 2 | `downloaded` | number | Bytes transferred so far; `NA` → 0 |
| 3 | `total` | number or `NA` | Exact total; `NA` when unknown |
| 4 | `total_estimate` | number or `NA` | Used when `total` is `NA` |
| 5 | `speed` | number or `NA` | Bytes/second; `NA` when paused/stalled |
| 6 | `eta` | number or `NA` | Seconds |

Examples:

```text
DL|downloading|1048576|10485760|NA|524288.0|18
DL|downloading|0|NA|10485760|NA|NA
DL|finished|10485760|10485760|NA|NA|NA
```

Parser rules:

- `NA`, `None`, empty, and non-finite values become `None` (except
  `downloaded`, which becomes `0`).
- `total` falls back to `total_estimate` when the exact total is unavailable;
  a total of `0` is normalized to `None` (unknown).
- Unknown/extra pipes are tolerated by limiting the split to 6 separators.

## Post-processing lines

Template:

```text
postprocess:PP|%(progress.status)s|%(progress.section_name)s|%(progress.filename)s
```

Examples:

```text
PP|started|Merger|/home/me/Videos/yoinktui/demo.mkv
PP|finished|ExtractAudio|/home/me/Videos/yoinktui/demo.mp3
```

## Completion line

`--print after_move:FINAL|%(filepath)s` emits:

```text
FINAL|/home/me/Videos/yoinktui/demo.mkv
```

Any other stdout line is surfaced as a `log` event. Blank lines are ignored.

## Dashboard mapping

- Speed, ETA, and peak come from fields 5, 6, and the running maximum of 5.
- The overall progress bar combines the video pass and audio pass; clip and
  audio-only downloads are single-pass.
- Section downloads (clips) additionally sample the output `.part` file size
  because yt-dlp's range downloader may not emit normal progress hooks.
