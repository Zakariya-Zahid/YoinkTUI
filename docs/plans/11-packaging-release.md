# Module 11 — Packaging, Release & Distribution

> Status: 🔴 needs work · Phase: 0 · Primary files: `pyproject.toml`, `dist/`,
> *(new)* `.github/workflows/release.yml`

## 1. Purpose

Own **getting YoinkTUI into users' hands**: build config, versioning,
changelog, release automation, and distribution channels.

## 2. Current state

- `pyproject.toml` uses `uv_build`; entry point `yoinktui = yoinktui.__main__:main`.
- Version `0.1.0` duplicated in `pyproject.toml` and `__init__.py`.
- `dist/` contains a wheel + sdist (git-ignored, stale).
- No changelog, no tags, no release workflow, no installers.
- Runtime requires external `yt-dlp` + `ffmpeg` (not Python deps).
- README install instructions are hardcoded to a local path.

## 3. Goals

- Reproducible builds and a documented release process.
- One source of truth for the version.
- Easy install: `uv tool install yoinktui`, pipx, maybe packages.

**Non-goals:** bundling yt-dlp/ffmpeg binaries (document instead; revisit for
standalone builds).

## 4. Workstreams

### WS 11.1 — Versioning & metadata — **[P0]**
- [ ] Single-source the version (dynamic from `__init__.__version__` or
      `importlib.metadata`); remove the pyproject copy.
- [ ] Add `CHANGELOG.md` (Keep a Changelog) and start from v0.1.0.
- [ ] Add `classifiers`, `keywords`, `license` file, `urls` to `pyproject.toml`.

### WS 11.2 — Build correctness — **[P0]**
- [ ] Verify wheel contains `tui/app.tcss` (package data) — test that
      `importlib.resources` can read it from an installed wheel.
- [ ] Add a `--doctor` dependency check (shared with modules 01/12).
- [ ] Clean the stale `dist/`; document build via `uv build`.
- [ ] Add a test that installs the wheel in a fresh venv and runs `--version`.

### WS 11.3 — Release automation — **[P1]**
- [ ] GitHub Actions release workflow on tag: build, test, publish to PyPI
      (trusted publishing), attach artifacts, create GitHub Release from changelog.
- [ ] Enforce semver tags; a `release` checklist doc.
- [ ] Nightly/dev builds published to TestPyPI (optional).

### WS 11.4 — Distribution channels — **[P1]**
- [ ] Document `uv tool install`, `pipx install`, and (if wanted) a Homebrew tap
      and AUR package.
- [ ] Provide a `Dockerfile` for headless/CLI use (ties to module 09).
- [ ] Standalone notes for Windows (pause limitation, ffmpeg install).

### WS 11.5 — Supply chain & trust — **[P2]**
- [ ] Dependency pinning policy + `uv lock` in CI; Dependabot/renovate.
- [ ] Signed releases / SLSA-style provenance (stretch).
- [ ] SECURITY.md with a vulnerability reporting path.

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
