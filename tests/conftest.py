"""Suite-wide isolation from the developer's YoinkTUI environment."""

from __future__ import annotations

import os

import pytest

try:
    import textual_image._terminal
    from textual_image._terminal import CellSize, TerminalCapabilities

    textual_image._terminal.probe_terminal = lambda: TerminalCapabilities(
        cell_size=CellSize(width=10, height=20), sixel=False, tgp=False
    )
except (ImportError, AttributeError):
    pass


@pytest.fixture(autouse=True)
def isolated_yoinktui_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ignore real ``YOINKTUI_*`` variables unless a test sets them itself."""
    for name in list(os.environ):
        if name.startswith("YOINKTUI_"):
            monkeypatch.delenv(name, raising=False)
