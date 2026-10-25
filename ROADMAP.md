# YoinkTUI — Roadmap

> A keyboard-driven, offline-first TUI download manager for YouTube and 1000+ sites,
> built on `yt-dlp` + `ffmpeg`, with a Steam-style download dashboard.

This roadmap is **modular**, not a task dump. Work is grouped into long-lived
**modules** (one document per module under [`docs/plans/`](docs/plans/)). Each
module owns a slice of the product and keeps its own workstreams, milestones,
and metrics. Modules span multiple releases; they are never "finished once".

---

## 1. Vision

Make downloading media from the terminal **fast, trustworthy, and pleasant**:

- **Trustworthy** — clear progress, correct speed/ETA, resumable, real errors.
- **Fast** — start a download in a few keystrokes; never blocks the UI.
- **Pleasant** — a polished, consistent TUI that looks intentional on every screen.

Non-goals: becoming a media *player*, a browser, or a full-blown download farm.
We orchestrate `yt-dlp` well and present it beautifully.

---

## 2. Guiding principles

1. **The backend is a library, the TUI is a client.** `backend/` must be usable
   headlessly (CLI/scripts) with zero Textual imports.
2. **One source of truth per concern.** Metadata lives in `models.py`, process
   control in `ytdlp.py`, presentation in `tui/`.
3. **Never block the event loop.** All I/O runs in workers; the UI only renders.
4. **Fail visibly and recoverably.** Every error maps to a typed reason + action.
5. **Config over code.** Caps, containers, output paths, and presets are data.
6. **Every module is testable in isolation.**

---

## 3. How this roadmap is organized

- **Module** — a durable area of ownership (e.g. *Download Engine*).
- **Workstream (WS)** — a themed group of tasks inside a module.
- **Priority** — `P0` (now, blocking quality), `P1` (next), `P2` (later/nice).
- **Status** — 🟢 stable · 🟡 in progress · 🔴 needs work · ⚪ not started.

Legend used inside module docs:

```
[x] done     [ ] todo     [~] in progress     [!] blocked     [-] dropped
```

**Workflow:** pick the lowest-numbered `P0` task in the module you own, do it,
tick the box, and update the module's *Current state* and the index table in
[`docs/plans/README.md`](docs/plans/README.md).

---

## 4. Phase overview

| Phase | Theme | Exit criteria |
|-------|-------|---------------|
| **Phase 0 — Foundations** | Stabilize v0.1.0 | Known bugs fixed, test harness + CI green, wheel installs cleanly |
| **Phase 1 — Reliable core** | Backend robustness | Typed errors, startup checks, config file, resume, retries |
| **Phase 2 — Power UX** | Queue, library, presets | Playlists/queue, persistent history, presets, theming |
| **Phase 3 — Automation** | CLI & headless | Flags, non-interactive mode, yt-dlp passthrough, IPC/hook |
| **Phase 4 — Scale & polish** | Perf, a11y, distribution | Snapshot tests, a11y pass, PyPI + installers, i18n |

Phases overlap deliberately — modules advance independently.

---

## 5. Module index

| # | Module | Doc | Status | Phase focus |
|---|--------|-----|--------|-------------|
| 01 | Download Engine | [01-download-engine](docs/plans/01-download-engine.md) | 🟡 | 1 |
| 02 | Media Metadata & Extraction | [02-media-metadata](docs/plans/02-media-metadata.md) | 🟡 | 1 |
| 03 | TUI Shell & Navigation | [03-tui-shell](docs/plans/03-tui-shell.md) | 🟡 | 1 |
| 04 | Format Picker & Preview | [04-format-picker](docs/plans/04-format-picker.md) | 🟡 | 2 |
| 05 | Download Manager & Queue | [05-download-manager](docs/plans/05-download-manager.md) | 🟡 | 2 |
| 06 | Theming, A11y & Keybindings | [06-theming-accessibility](docs/plans/06-theming-accessibility.md) | 🔴 | 4 |
| 07 | Configuration & Profiles | [07-configuration-profiles](docs/plans/07-configuration-profiles.md) | 🟡 | 1 |
| 08 | History, Library & Persistence | [08-history-library](docs/plans/08-history-library.md) | 🟡 | 2 |
| 09 | CLI & Automation | [09-cli-automation](docs/plans/09-cli-automation.md) | ⚪ | 3 |
| 10 | Quality: Tests, CI & Types | [10-quality-testing](docs/plans/10-quality-testing.md) | 🟡 | 0 |
| 11 | Packaging, Release & Distribution | [11-packaging-release](docs/plans/11-packaging-release.md) | 🟡 | 0 |
| 12 | Performance, Resources & Diagnostics | [12-performance-diagnostics](docs/plans/12-performance-diagnostics.md) | 🔴 | 4 |

---

## 6. Release milestones

### v0.2.0 — "Trustworthy" — ✅ implemented, unreleased internal milestone
- All `P0` tasks in modules 01, 02, 03, 07, 10, 11.
- Typed error taxonomy + startup dependency checks (yt-dlp/ffmpeg).
- Config file (`~/.config/yoinktui/config.toml`) with output dir, quality cap,
  container, audio codec.
- Test suite (unit + parser + smoke + snapshots) and CI on Linux + macOS.
- README corrected to the real architecture.

See [`CHANGELOG.md`](CHANGELOG.md) and [`docs/RELEASING.md`](docs/RELEASING.md).

### v0.3.0 — "Power user" — ✅ implemented, unreleased internal milestone
- [x] Queue / playlist support and multi-item dashboard.
- [x] Persistent history + library browse screen.
- [x] Presets (*Music*, *Archive*, *Mobile*) and resume pending, interrupted, or failed downloads.
- [x] Snapshot tests for every screen.

The first public release and tag remain v1.0.0.

### v1.0.0 — "Product"
- CLI flags + headless mode.
- Accessibility pass (screen readers, no-color, ASCII mode).
- PyPI wheel + `uv tool install`, Homebrew/AUR formulae.
- i18n scaffolding and documentation site.

---

## 7. Cross-cutting KPIs

| KPI | Target | Measured by |
|-----|--------|-------------|
| Crash-free sessions | ≥ 99.5% | Diagnostics module |
| Download success rate | ≥ 98% on supported sites | History module |
| Time-to-first-download | ≤ 15 s from launch | Manual benchmark |
| Cold start | ≤ 400 ms to first paint | Perf module |
| Speed/ETA accuracy | within ±10% of yt-dlp | Parser tests |
| Test coverage (backend) | ≥ 80% | Quality module |

---

## 8. Top risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Site changes break extraction | High | Track yt-dlp releases; add `yt-dlp -U` guidance; typed errors |
| Progress template format drifts | Medium | Parser contract tests + version guard |
| Terminal graphics inconsistency | Medium | Capability detection + graceful fallbacks |
| Feature creep into a player/DL farm | Medium | Re-read vision & non-goals each planning cycle |
| Coverage gaps → regressions | Medium | CI gates (ruff/mypy/pytest/snapshots); coverage reporting in v0.3 |

---

## 9. Keeping this document current

- Every module doc is the **source of truth** for its area; update it in the same
  PR as the code change.
- Review the whole roadmap once per release; move `P2` → `P1` only when `P0` is clear.
- Keep the module index table's **Status** column honest.
