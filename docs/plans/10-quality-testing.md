# Module 10 — Quality: Tests, CI & Types

> Status: 🔴 needs work · Phase: 0 · Primary files: *(new)* `tests/`,
> `pyproject.toml` tool config, `.github/workflows/`

## 1. Purpose

Own **confidence**: automated tests, static analysis, CI, and the workflows that
keep the codebase healthy as modules grow. This module **blocks** Phase 1 work.

## 2. Current state

- **Zero tests** in the repository.
- No lint/format/type configuration, no CI, no pre-commit.
- Bugs shipped that tests would have caught (progress field shift; undefined
  `url` in `UrlScreen._on_probed`; `Static.Clicked` misuse during a refactor).
- Manual verification has been done via ad-hoc `run_test()` scripts and
  `export_screenshot()` — a good foundation to formalise.

## 3. Goals

- Every module has tests proportional to its risk.
- CI gates merges on tests + lint + types.
- Regressions in the UI are caught by snapshot tests.

**Non-goals:** 100% coverage vanity metrics.

## 4. Workstreams

### WS 10.1 — Harness & tooling — **[P0]**
- [ ] Add `pytest`, `pytest-asyncio`, `pytest-textual-snapshot` (or
      `textual`'s snapshot fixture) as dev deps under `[dependency-groups]`.
- [ ] Configure `[tool.pytest.ini_options]` (paths, asyncio mode, markers).
- [ ] Add `ruff` (lint + format) and `mypy`/`pyright`; wire `[tool.ruff]`,
      `[tool.mypy]`.
- [ ] Add `pre-commit` with ruff + basic hygiene hooks.

### WS 10.2 — Unit tests — **[P0]**
- [ ] `tests/backend/test_progress_parser.py` — the field contract
      (incl. the `total_bytes == NA` YouTube case, fixed regression).
- [ ] `tests/backend/test_formats.py` — `MediaInfo.from_dict` coercions
      (`NA`, `None`, `0`, floats), derived properties.
- [ ] `tests/backend/test_selectors.py` — `video_selector` / `audio_selector`.
- [ ] `tests/backend/test_control.py` — pause/resume/cancel against a real
      `sleep` process group (already prototyped; make it a test).
- [ ] `tests/backend/test_command.py` — `_build_cmd` emits expected args.

### WS 10.3 — TUI tests — **[P0]**
- [ ] Smoke test: app boots, `UrlScreen` renders, no exceptions.
- [ ] `run_test()` flow tests: submit URL (fake probe) → `FormatScreen` →
      start download (fake download) → dashboard states.
- [ ] Snapshot tests for `UrlScreen`, `FormatScreen`, `DownloadScreen`
      (running/paused/complete), `ErrorModal`, across 2 themes + 2 sizes.
- [ ] Regression test for the action-bar buttons and probe status.

### WS 10.4 — CI — **[P0]**
- [ ] GitHub Actions matrix: Python 3.12/3.13 × Linux/macOS.
- [ ] Steps: install (`uv sync`), `ruff check`, `ruff format --check`,
      `mypy`, `pytest`.
- [ ] Snapshot artifact upload on failure.
- [ ] Optional: nightly job against real yt-dlp for a known public URL.

### WS 10.5 — Coverage & policy — **[P1]**
- [ ] Coverage reporting; backend target ≥ 80%, overall ≥ 60%.
- [ ] `docs/contracts/` (progress, navigation, keys) are tested contracts.
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
