# Module 10 — Quality: Tests, CI & Types

> Status: 🟡 P0 complete (v0.2.0) · Phase: 0 · Primary files: `tests/`,
> `pyproject.toml` tool config, `.github/workflows/`
>
> Remaining unchecked items are P1 coverage policy and the optional nightly
> real-network job.

## 1. Purpose

Own **confidence**: automated tests, static analysis, CI, and the workflows that
keep the codebase healthy as modules grow. This module **blocks** Phase 1 work.

## 2. Current state

- **153 tests** across backend and TUI (`uv run pytest -q`): parser contract,
  models/coercions, selectors + merge fallback, config loader/precedence,
  command builder, process control, probe, timecode/clips, packaging,
  formatters.
- `ruff` (lint + format), `mypy`, `pre-commit`, and pytest config live in
  `pyproject.toml` / `.pre-commit-config.yaml`; all gates are green locally.
- CI runs on Linux + macOS for Python 3.12/3.13, with a separate wheel-install
  job; snapshot artifacts upload on failure.
- TUI tests cover startup, missing dependencies, URL validation, duplicate
  submits, probe→format→download flows, Esc semantics, and the action bar.
- 24 SVG snapshots cover `UrlScreen`, `FormatScreen`, `DownloadScreen`
  (running/paused/complete), and `ErrorModal` across two themes and two sizes.
- `docs/contracts/progress.md` and `navigation.md` (plus `selection.md`) are
  backed by tests.
- Coverage is not measured yet (P1).

## 3. Goals

- Every module has tests proportional to its risk.
- CI gates merges on tests + lint + types.
- Regressions in the UI are caught by snapshot tests.

**Non-goals:** 100% coverage vanity metrics.

## 4. Workstreams

### WS 10.1 — Harness & tooling — **[P0]**
- [x] Add `pytest`, `pytest-asyncio`, `pytest-textual-snapshot` (or
      `textual`'s snapshot fixture) as dev deps under `[dependency-groups]`.
- [x] Configure `[tool.pytest.ini_options]` (paths, asyncio mode, markers).
- [x] Add `ruff` (lint + format) and `mypy`/`pyright`; wire `[tool.ruff]`,
      `[tool.mypy]`.
- [x] Add `pre-commit` with ruff + basic hygiene hooks.

### WS 10.2 — Unit tests — **[P0]**
- [x] `tests/backend/test_progress_parser.py` — the field contract
      (incl. the `total_bytes == NA` YouTube case, fixed regression).
- [x] `tests/backend/test_formats.py` — `MediaInfo.from_dict` coercions
      (`NA`, `None`, `0`, floats), derived properties.
- [x] `tests/backend/test_selectors.py` — `video_selector` / `audio_selector`
      plus the mkv→mp4 merge fallback.
- [x] `tests/backend/test_control.py` — pause/resume/cancel against a real
      `sleep` process group.
- [x] `tests/backend/test_command.py` — `_build_cmd` emits expected args.
- [x] Extra: `test_config.py`, `test_errors.py`, `test_probe.py`,
      `test_timecode.py`, `test_cli.py`, `test_packaging.py`,
      `test_formatters.py`.

### WS 10.3 — TUI tests — **[P0]**
- [x] Smoke test: app boots, `UrlScreen` renders, no exceptions.
- [x] `run_test()` flow tests: submit URL (fake probe) → `FormatScreen` →
      start download (fake download) → dashboard states.
- [x] Snapshot tests for `UrlScreen`, `FormatScreen`, `DownloadScreen`
      (running/paused/complete), `ErrorModal`, across 2 themes + 2 sizes
      (24 snapshots, clock/time frozen in tests).
- [x] Regression test for the action-bar buttons and probe status.

### WS 10.4 — CI — **[P0]**
- [x] GitHub Actions matrix: Python 3.12/3.13 × Linux/macOS.
- [x] Steps: install (`uv sync`), `ruff check`, `ruff format --check`,
      `mypy`, `pytest`.
- [x] Snapshot artifact upload on failure.
- [x] Extra: wheel build + fresh-venv install + `--version`/data-file check.
- [ ] Optional: nightly job against real yt-dlp for a known public URL.

### WS 10.5 — Coverage & policy — **[P1]**
- [ ] Coverage reporting; backend target ≥ 80%, overall ≥ 60%.
- [~] `docs/contracts/` (progress, navigation, keys) are tested contracts
      (progress/navigation/selection covered; a keys contract is still TODO).
- [ ] A bug fixed ⇒ a test added (enforced by review checklist).

## 5. Milestones

| Milestone | Scope | Exit criteria |
|-----------|-------|---------------|
| M1 — Harness | WS 10.1 | `uv run pytest` runs; ruff+mypy configured |
| M2 — Core tests | WS 10.2–10.3 | Parser/model/control + boot + flow tests green |
| M3 — CI gate | WS 10.4 | PRs blocked on red CI |
| M4 — Snapshots | WS 10.3 | Visual regressions caught per screen |

## 6. Acceptance criteria

- A clean checkout runs the full suite locally in < 60 s.
- CI is required for merge; flaky tests are quarantined, not ignored.
- Re-introducing the progress field-shift bug fails CI.

## 7. Dependencies

- All code modules (tests target them). Blocks confidently shipping Phase 1+.

## 8. Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Snapshot flakiness (timing/theme) | Freeze clock, pin theme, deterministic sizes |
| Slow TUI tests | Small fake event streams; mark `slow` |
| Test maintenance burden | Test contracts & public APIs, not internals |

## 9. Metrics

- Coverage (backend / overall); CI duration; flake rate (target 0).

## 10. Open questions

- `pytest-textual-snapshot` vs. `app.export_screenshot()` SVGs in-repo?
- Do we test against real network in nightly only? (Proposal: yes.)
