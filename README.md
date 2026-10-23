<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="src/yoinktui/assets/logo-dark.png">
    <img src="src/yoinktui/assets/logo-light.png" alt="YoinkTUI" width="420">
  </picture>
</p>

# YoinkTUI

TUI download manager for YouTube (and 1000+ sites) via **yt-dlp** + **ffmpeg**.

> Yoink it. Keep it.

## Features

- **Paste URL → See formats → Download** — clean three-screen flow
- **Clip downloads** — pick a start/end range to grab just the useful part of a long podcast or tutorial
- **Steam-style download manager** — per-stream queue, live speed/ETA/peak/disk tiles,
  overall progress, pause/resume, cancel, and a timestamped activity log
- **Config file** — quality cap, container, audio format, fragment concurrency,
  rate limit, metadata/thumbnail embedding, output directory, and defaults
- **Trustworthy failures** — typed errors with hints, startup dependency checks,
  and a `yoinktui --doctor` pre-flight report
- **Live thumbnail** — renders via kitty graphics / sixel / Unicode fallback (`textual-image`)
- **Format picker** — resolution, codec, size, and bitrate at a glance
- **Video + Audio / Video Only / Audio Only** modes
- **Real pause & resume** — suspends the whole yt-dlp process group (POSIX)

## Live Demo
<p align="center">
  <a href="https://github.com/user-attachments/assets/4d92a270-7695-44be-a0ad-ab9ccb74ca62">Watch the Demo</a>
</p>

## Screenshots

<p align="center">
  <img src="assets/main.png" alt="YoinkTUI URL screen" width="100%">
  <br><br>
  <img src="assets/Video_Url.png" alt="YoinkTUI format picker" width="100%">
  <br><br>
  <img src="assets/Dashboard.png" alt="YoinkTUI download dashboard" width="100%">
  <br><br>
  <img src="assets/Download_Section.png" alt="YoinkTUI download in progress" width="100%">
</p>

## Install

Requires Python 3.12+, `yt-dlp`, and `ffmpeg` on your `PATH`.

```bash
git clone https://github.com/Zakariya-Zahid/YoinkTUI.git
cd YoinkTUI
uv sync
```

For a global install from the checkout:

```bash
uv tool install -e .
yoinktui --doctor
```

## Run

```bash
uv run yoinktui
```

Check the environment before the first download:

```bash
uv run yoinktui --doctor
```

`--doctor` verifies yt-dlp and ffmpeg, prints their versions, and checks that
the download directory is writable. Missing dependencies open a friendly
startup screen instead of a traceback.

## Usage

1. **Paste a URL** — YouTube, Twitter/X, Vimeo, Twitch, TikTok, etc.
2. **Pick a format** — Table shows video & audio streams; arrow keys navigate, Enter selects
3. **Choose mode** — `Video+Audio` (default), `Video Only`, `Audio Only`
4. **Optional clip** — press `C`, enter a start/end range, then Apply. Leave end blank to go to the end of the video.
5. **Download** — Steam-style dashboard with queue, stats, and activity log

## Configuration

YoinkTUI reads `$XDG_CONFIG_HOME/yoinktui/config.toml` (usually
`~/.config/yoinktui/config.toml`). Precedence, highest first:

1. CLI flags
2. `YOINKTUI_*` environment variables
3. the config file
4. built-in defaults

Create a default file with the current defaults:

```bash
yoinktui --write-default-config
```

Or write one by hand:

```toml
[general]
theme = "dark"            # dark, light, or a Textual theme name
default_mode = "video"    # video | vonly | audio

[download]
dir = "~/Videos/yoinktui"
quality_cap = 1080        # 0 = best available
container = "mkv"         # mkv (preferred) | mp4 | auto
audio_format = "mp3"      # mp3 | m4a | opus | flac | best
audio_quality = "0"
concurrent_fragments = 0  # 0 = yt-dlp default
rate_limit = ""           # e.g. "5M"
write_subtitles = false
embed_metadata = true
embed_thumbnail = false
keep_original = false

[network]
proxy = ""
cookies_from_browser = ""

[ui]
show_preview = true
ascii = false
no_color = false
```

Environment overrides use the same names with a `YOINKTUI_` prefix:
`YOINKTUI_DOWNLOAD_DIR`, `YOINKTUI_QUALITY_CAP`, `YOINKTUI_CONTAINER`,
`YOINKTUI_AUDIO_FORMAT`, `YOINKTUI_PROXY`, and so on.

Useful commands:

```bash
yoinktui --print-config          # show the merged result
yoinktui --config ./test.toml    # use a different file
yoinktui --doctor                # check dependencies + paths
```

Download policy can also be set per run:

```bash
yoinktui --quality-cap 720 --container mp4 --audio-format m4a
yoinktui --concurrent-fragments 4 --rate-limit 5M
```

Defaults: 1080p cap, `mkv`, `mp3`, `~/Videos/yoinktui`.

### Cookies and proxy

Some sites need a logged-in browser session or a different network:

```bash
yoinktui --cookies-from-browser firefox
yoinktui --cookies-from-browser "firefox:/path/to/profile" \
  --proxy socks5://127.0.0.1:1080
```

The same values can live in `[network]`. Use the same browser names as
yt-dlp: `chrome`, `firefox`, `edge`, `brave`, or `browser:profile`. Extra
yt-dlp flags can be passed with `--yt-dlp-arg=...` (repeatable).

### TikTok / HTTP 403

TikTok's anti-bot layer sometimes rejects yt-dlp with
`HTTP Error 403: Forbidden` before it can read the video. That is a
TikTok-side block, not a YoinkTUI site limit. Log into TikTok in your
browser and use `--cookies-from-browser`, or try a VPN/proxy. The same URL
may work later without changes.

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Enter` | Submit URL / Select format |
| `↑/↓` | Navigate format table |
| `D` | Download the selected format |
| `C` | Set a clip start/end range |
| `V` / `O` / `A` | Video+Audio / Video Only / Audio Only |
| `Esc` | Back, cancel download, or quit from the URL screen |
| `P` / `Space` | Pause / resume download |
| `Ctrl+Q` | Quit app |
| `Ctrl+D` | Toggle dark/light theme |

## Architecture

```
assets/                  # README screenshots + demo video
src/yoinktui/
├── app.py               # App shell, per-instance config/state, dependency gate
├── __main__.py          # CLI flags, config precedence, --doctor
├── assets/              # App logo (light & dark variants)
├── backend/
│   ├── config.py        # TOML schema, loader, XDG paths, last-URL state
│   ├── errors.py        # DownloadError + ErrorReason taxonomy
│   ├── models.py        # MediaInfo, FormatInfo, numeric coercions
│   └── ytdlp.py         # probe/download, progress contract, process control
└── tui/
    ├── app.tcss         # All styles (Textual 8 compatible)
    ├── widgets.py       # FormatTable, InfoPanel, ThumbnailCard, DownloadDashboard
    └── screens.py       # UrlScreen, FormatScreen, DownloadScreen, modals
tests/
├── backend/             # parser, models, config, selectors, command, control
└── tui/                 # smoke, flow, URL validation, SVG snapshots
docs/contracts/          # frozen progress, selection, and navigation contracts
```

- **Backend** runs yt-dlp in a thread (`@work(thread=True)`) so the UI stays responsive
- **Progress** is parsed from yt-dlp's `--progress-template` stdout stream;
  the field order is frozen in [`docs/contracts/progress.md`](docs/contracts/progress.md)
- **Control** uses POSIX `SIGSTOP`/`SIGCONT` for real pause/resume and
  terminates the whole process group on cancel
- **Failures** are classified into network/geo/auth/not-found/disk/ffmpeg/
  unsupported buckets, each with a hint and suggested next step
- **Thumbnails** are fetched via `httpx` and rendered by `textual-image.AutoImage`

## Development

```bash
uv sync --dev
uv run pytest                       # unit + parser + TUI + snapshots
uv run pytest --snapshot-update     # accept intentional UI changes
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```

CI runs the same checks on Linux and macOS for Python 3.12 and 3.13
([`.github/workflows/ci.yml`](.github/workflows/ci.yml)). The release
checklist lives in [`docs/RELEASING.md`](docs/RELEASING.md).

## Roadmap

See [ROADMAP.md](ROADMAP.md) and the per-module plans in [docs/plans/](docs/plans/).

## License

MIT — see [LICENSE](LICENSE).
