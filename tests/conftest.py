"""Suite-wide isolation from the developer's YoinkTUI environment."""

from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def isolated_yoinktui_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ignore real ``YOINKTUI_*`` variables unless a test sets them itself."""
    for name in list(os.environ):
        if name.startswith("YOINKTUI_"):
            monkeypatch.delenv(name, raising=False)
