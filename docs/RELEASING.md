# Releasing YoinkTUI

This checklist is for maintainers cutting a release. The project is not on PyPI
yet; the same steps apply once it is.

## 1. Prepare

- [ ] `git status` is clean and you are on `main`.
- [ ] Bump `version` in `pyproject.toml` (the only version source; `__init__.py`
      reads it via `importlib.metadata`).
- [ ] Update `CHANGELOG.md` (`Added` / `Changed` / `Fixed`).
- [ ] Update `ROADMAP.md` and the relevant `docs/plans/` checkboxes.

```bash
./scripts/check_release.sh   # optional: runs the full gate below
```

## 2. Full local gate

```bash
uv sync --dev
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest -q
uv build
```

## 3. Verify the built wheel

Install the wheel into a throwaway environment — never test from the editable
checkout:

```bash
uv venv /tmp/yoinktui-release --python 3.12
uv pip install --python /tmp/yoinktui-release/bin/python dist/*.whl

/tmp/yoinktui-release/bin/yoinktui --version
/tmp/yoinktui-release/bin/yoinktui --print-config
/tmp/yoinktui-release/bin/python - <<'PY'
from importlib.resources import files
assert files("yoinktui").joinpath("tui/app.tcss").is_file()
assert files("yoinktui").joinpath("assets/logo-dark.png").is_file()
print("packaged data files: OK")
PY
```

CI runs the same install/version/data-file checks in the `packaging` job.

## 4. Tag and publish

```bash
git tag -a vX.Y.Z -m "vX.Y.Z"
git push origin vX.Y.Z
```

- [ ] GitHub release notes link to `CHANGELOG.md`.
- [ ] PyPI publish (when configured) uses the wheel + sdist from `dist/`.
- [ ] Verify `uv tool install yoinktui` and `pipx install yoinktui` in a clean
      environment after publication.

## 5. Post-release

- [ ] Bump `main` to the next development version.
- [ ] Open a tracking issue for the next milestone.
- [ ] Close the release milestone.
