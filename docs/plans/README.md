# Module Plans — Index & Conventions

This folder holds one **living plan per module**. They are intentionally modular:
each document covers a durable area of the product, is owned by whoever touches
that code, and is updated continuously rather than "completed".

---

## How to use these documents

1. **Find your module** in the table below and open its doc.
2. Read *Current state* so you know what already exists.
3. Work the lowest-numbered **`P0`** task in *Workstreams*.
4. When you land a change: tick the checkbox, update *Current state* and *Metrics*,
   and reflect any status change in the index table here.
5. If a task grows a life of its own, promote it to a new workstream — don't
   inflate the parent.

## Conventions

- **Tags:** `**[P0]**` now/blocking · `**[P1]**` next · `**[P2]**` later.
- **Checkbox:** `[ ]` todo · `[~]` in progress · `[x]` done · `[!]` blocked · `[-]` dropped.
- **Workstream id:** `WS <module>.<n>` (e.g. `WS 05.3`).
- **File references** point at the primary code paths the module owns.
- Every module doc uses the same section skeleton (see *Template* below).

## Module index

| # | Module | Primary files | Status | Phase |
|---|--------|---------------|--------|-------|
| 01 | [Download Engine](01-download-engine.md) | `backend/ytdlp.py` | 🟡 | 1 |
| 02 | [Media Metadata & Extraction](02-media-metadata.md) | `backend/models.py`, `backend/ytdlp.py` | 🔴 | 1 |
| 03 | [TUI Shell & Navigation](03-tui-shell.md) | `app.py`, `tui/screens.py` | 🟡 | 1 |
| 04 | [Format Picker & Preview](04-format-picker.md) | `tui/widgets.py` (`FormatTable`, `InfoPanel`, `ThumbnailCard`) | 🟡 | 2 |
| 05 | [Download Manager & Queue](05-download-manager.md) | `tui/widgets.py` (`DownloadDashboard`), `tui/screens.py` (`DownloadScreen`) | 🟡 | 2 |
| 06 | [Theming, A11y & Keybindings](06-theming-accessibility.md) | `tui/app.tcss` | 🔴 | 4 |
| 07 | [Configuration & Profiles](07-configuration-profiles.md) | `app.py` (`AppConfig`) | 🔴 | 1 |
| 08 | [History, Library & Persistence](08-history-library.md) | *(new)* `backend/library.py` | ⚪ | 2 |
| 09 | [CLI & Automation](09-cli-automation.md) | `__main__.py`, *(new)* `cli.py` | ⚪ | 3 |
| 10 | [Quality: Tests, CI & Types](10-quality-testing.md) | `tests/`, `.github/workflows/` | 🔴 | 0 |
| 11 | [Packaging, Release & Distribution](11-packaging-release.md) | `pyproject.toml`, `dist/` | 🔴 | 0 |
| 12 | [Performance, Resources & Diagnostics](12-performance-diagnostics.md) | all | 🔴 | 4 |

## Template

Every module doc uses this skeleton:

```markdown
# Module NN — Name
> Status · Phase · Owner · Primary files

## 1. Purpose
## 2. Current state
## 3. Goals / Non-goals
## 4. Workstreams        # checkbox tasks, tagged P0/P1/P2
## 5. Milestones         # table: milestone → scope → exit criteria
## 6. Acceptance criteria
## 7. Dependencies
## 8. Risks & mitigations
## 9. Metrics
## 10. Open questions
```
