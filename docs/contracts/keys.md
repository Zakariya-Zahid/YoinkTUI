# Contract: keyboard model and shortcuts

YoinkTUI is designed for full keyboard navigation without requiring mouse input.
This document defines the keybinding taxonomy, conflict rules, and the complete
screen-by-screen binding map.

---

## 1. Principles

1. **Vim and ANSI arrow parity**: Whenever row or list navigation is supported,
   both `↑/↓` and `k/j` work identically.
2. **Context-sensitive character bindings**: Single-letter shortcuts (`d`, `q`,
   `p`, `?`) are active only when a text input is not focused. When an input is
   focused, character keys type literal text; `F1` and `Ctrl` chords remain active.
3. **Esc always retreats**: `Esc` closes the topmost modal, cancels active
   operations, or navigates back one level in the screen stack.
4. **Help is always available**: Pressing `?` (or `F1`) opens `HelpModal` from
   any screen.

---

## 2. Global Bindings

| Key | Action | Scope |
|-----|--------|-------|
| `?` / `F1` | Open keyboard shortcuts & help overlay | Global |
| `Ctrl+D` | Toggle dark / light theme | Global |
| `Ctrl+Q` | Quit application cleanly (saves queue & history) | Global |

---

## 3. Screen-by-Screen Bindings

### UrlScreen (Home)
| Key | Action |
|-----|--------|
| `Enter` | Submit URL and probe available media streams |
| `Tab` / `Shift+Tab` | Cycle focus between URL input and action buttons |
| `P` | Jump directly to Playlist screen |
| `Q` | Jump directly to Queue screen |
| `L` | Jump directly to Library / History screen |
| `Esc` / `Ctrl+C` | Quit application |

### FormatScreen (Stream Selection)
| Key | Action |
|-----|--------|
| `↑` / `k` | Navigate to previous format row |
| `↓` / `j` | Navigate to next format row |
| `1` | Select **Video + Audio** mode (merges video with best audio) |
| `2` | Select **Video Only** mode |
| `3` | Select **Audio Only** mode |
| `D` | Start download immediately using the highlighted format |
| `Q` | Enqueue the highlighted format into persistent queue |
| `C` | Open timecode clipping modal (`ClipModal`) |
| `P` | Open presets modal (`PresetModal`) |
| `Esc` | Return to `UrlScreen` |

### QueueScreen & PlaylistScreen (Multi-Select Tables)
| Key | Action |
|-----|--------|
| `↑` / `k` | Move cursor up |
| `↓` / `j` | Move cursor down |
| `Space` / `Enter` | Toggle selection for highlighted row |
| `Ctrl+A` | Select all rows |
| `Ctrl+Shift+A` | Deselect all rows |
| `D` | Start / queue all selected items |
| `R` / `Delete` | Remove selected item(s) from queue |
| `Esc` | Return to previous screen |

### DownloadScreen (Active Transfer Dashboard)
| Key | Action |
|-----|--------|
| `Space` | Pause or resume active download process (POSIX `SIGSTOP`/`SIGCONT`) |
| `C` / `Esc` | Cancel running download (terminates process group cleanly) |

### LibraryScreen (History Store)
| Key | Action |
|-----|--------|
| `↑` / `k` | Move cursor up |
| `↓` / `j` | Move cursor down |
| `O` | Open downloaded file or folder in system file manager |
| `D` | Re-download selected media item |
| `Delete` | Remove history entry from database |
| `Esc` | Return to `UrlScreen` |

### Modals (HelpModal, PresetModal, ClipModal, ConfirmModal)
| Key | Action |
|-----|--------|
| `Esc` | Dismiss modal without saving |
| `Enter` | Confirm / apply modal choice |
| `Tab` / `Shift+Tab` | Cycle focus between modal fields and buttons |
