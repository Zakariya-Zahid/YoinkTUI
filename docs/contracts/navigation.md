# Contract: navigation and Escape semantics

The shell is a stack of Textual `Screen`s. This file documents the intended
graph so tests and future screens stay consistent.

## Screen graph

```text
StartupErrorScreen            (only when yt-dlp/ffmpeg is missing)

UrlScreen
├── probe → FormatScreen → DownloadScreen
│            ├── ClipModal
│            └── PresetModal
├── playlist → PlaylistScreen → QueueScreen
├── queue → QueueScreen → DownloadScreen (queue items)
└── library → LibraryScreen
```

Startup also opens `QueueScreen` when `queue.json` contains pending,
interrupted, or failed items. `ErrorModal` is a legacy fallback.

## Escape semantics

| Screen | `Esc` | Notes |
|--------|-------|-------|
| `UrlScreen` | Quit the app | `Ctrl+Q` and `Ctrl+C` also quit |
| `FormatScreen` | Pop back to `UrlScreen` | The input is re-enabled and focused |
| `DownloadScreen` | Cancel the running download | Press again / after finish to close |
| `QueueScreen` | Pop back | Queue state is already persisted |
| `PlaylistScreen` | Pop back without queueing | |
| `LibraryScreen` | Pop back | |
| `PresetModal` | Dismiss without applying | |
| `ClipModal` | Dismiss without changing the clip | |
| `ErrorModal` | Dismiss | |
| `StartupErrorScreen` | Quit | Dependency problem cannot be fixed in-app |

## Rules

1. A screen push must be idempotent: repeated `Enter`/`d` while a probe or
   download is starting must not push a second screen.
2. After a pop, the previous screen restores input state and focus
   (`on_screen_resume`).
3. Cancelling/leaving `DownloadScreen` terminates the yt-dlp process group;
   no child process may outlive the screen.
4. `Esc` never opens a new modal; retryable errors are shown inline.
