# Module 11 — Packaging, Release & Distribution

> Status: 🟢 stable (v1.0.0) · Phase: 0/4 · Primary files: `pyproject.toml`, `dist/`,
> `.github/workflows/release.yml`, `SECURITY.md`

## 1. Purpose

Own **getting YoinkTUI into users' hands**: build config, versioning,
changelog, release automation, and distribution channels.

## 2. Current state

- `pyproject.toml` uses `uv_build`; entry point `yoinktui = yoinktui.__main__:main`.
- Version `1.0.0` lives only in `pyproject.toml`; `__init__.__version__` reads it
  through `importlib.metadata`.
- First public release is v1.0.0 with `Development Status :: 5 - Production/Stable`.
- `CHANGELOG.md`, `LICENSE` (MIT), classifiers, keywords, and project URLs are
  in place.
- `uv build` produces an sdist + wheel; the wheel contains `tui/app.tcss` and
  the logo assets. CI and release workflows install the wheel in a fresh venv and
  run `--version` + data-file checks.
- `yoinktui --doctor` reports dependency versions, config path, download dir,
  and writability.
- Automated tag-based release workflow `.github/workflows/release.yml` with PyPI
  Trusted Publishing and GitHub Release generation.
- `SECURITY.md` defines vulnerability disclosure policy.

## 3. Goals

- Reproducible builds and a documented release process.
- One source of truth for the version.
- Easy install: `uv tool install yoinktui`, pipx, maybe packages.

**Non-goals:** bundling yt-dlp/ffmpeg binaries (document instead; revisit for
standalone builds).

## 4. Workstreams

### WS 11.1 — Versioning & metadata — **[P0]**
- [x] Single-source the version (pyproject as the source; `__init__` reads it
      via `importlib.metadata`).
- [x] Add `CHANGELOG.md` (Keep a Changelog) and maintain through v1.0.0.
- [x] Add `classifiers`, `keywords`, `license` file, `urls` to `pyproject.toml`.

### WS 11.2 — Build correctness — **[P0]**
- [x] Verify wheel contains `tui/app.tcss` (package data) — test that
      `importlib.resources` can read it from an installed wheel.
- [x] Add a `--doctor` dependency check (shared with modules 01/12).
- [x] Clean the stale `dist/`; document build via `uv build`.
- [x] Add a test that installs the wheel in a fresh venv and runs `--version`
      (CI `packaging` job; local equivalent in `docs/RELEASING.md`).

### WS 11.3 — Release automation — **[P1]**
- [x] GitHub Actions release workflow on tag: build, test, publish to PyPI
      (trusted publishing), attach artifacts, create GitHub Release from changelog.
- [x] Enforce semver tags; a `release` checklist doc (`docs/RELEASING.md`).
- [~] Nightly/dev builds published to TestPyPI (optional).

### WS 11.4 — Distribution channels — **[P1]**
- [x] Document `uv tool install`, `pipx install`, and release distribution.
- [ ] Provide a `Dockerfile` for headless/CLI use (ties to module 09).
- [ ] Standalone notes for Windows (pause limitation, ffmpeg install).

### WS 11.5 — Supply chain & trust — **[P2]**
- [x] Dependency pinning policy + `uv lock` in CI; Dependabot/renovate.
- [ ] Signed releases / SLSA-style provenance (stretch).
- [x] SECURITY.md with a vulnerability reporting path.

## 5. Milestones

| Milestone | Scope | Exit criteria |
|-----------|-------|---------------|
| M1 — Clean metadata | WS 11.1–11.2 | One version source; CSS ships in wheel |
| M2 — Automated release | WS 11.3 | Tag → PyPI + GitHub Release, no manual steps |
| M3 — Multiple channels | WS 11.4–11.5 | Documented installs + Dependabot active |

## 6. Acceptance criteria

- `uv build && uv pip install dist/*.whl` yields a working `yoinktui`.
- Installed wheel can load `app.tcss` from any working directory.
- A tagged release publishes without manual file juggling.

## 7. Dependencies

- Module 10 (tests must pass before publish), 01/12 (`--doctor`).

## 8. Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Missing package data | Wheel-install test in CI |
| Version drift | Single source + `--version` test |
| External deps confusion | `--doctor` + prominent README requirements |

## 9. Metrics

- Releases per quarter; time from tag to published; install failures reported.

## 10. Open questions

- Publish to PyPI under which name/scope? (`yoinktui` availability check.)
- Do we ever bundle ffmpeg for a zero-setup install?
