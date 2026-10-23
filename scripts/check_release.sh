#!/usr/bin/env bash
# Run the full local release gate. See docs/RELEASING.md.
set -euo pipefail

cd "$(dirname "$0")/.."

uv sync --dev
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest -q
uv build
