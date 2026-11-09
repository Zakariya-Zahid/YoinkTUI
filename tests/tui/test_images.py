"""Tests for terminal image renderer selection."""

from __future__ import annotations

import pytest
from textual_image.widget import HalfcellImage, TGPImage

from yoinktui.tui import widgets


class _FakeTty:
    def isatty(self) -> bool:
        return True


def _force_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(widgets.sys, "__stdout__", _FakeTty())


def test_auto_uses_halfcell_on_konsole(monkeypatch: pytest.MonkeyPatch) -> None:
    _force_tty(monkeypatch)
    monkeypatch.setenv("KONSOLE_VERSION", "230805")
    monkeypatch.setenv("TERM", "xterm-256color")
    monkeypatch.delenv("KITTY_WINDOW_ID", raising=False)
    monkeypatch.delenv("TERM_PROGRAM", raising=False)

    assert widgets._terminal_image_class() is HalfcellImage


def test_auto_uses_kitty_graphics_in_kitty(monkeypatch: pytest.MonkeyPatch) -> None:
    _force_tty(monkeypatch)
    monkeypatch.setenv("KITTY_WINDOW_ID", "1")
    monkeypatch.setenv("TERM", "xterm-kitty")
    monkeypatch.delenv("KONSOLE_VERSION", raising=False)

    assert widgets._terminal_image_class() is TGPImage


def test_explicit_image_modes(monkeypatch: pytest.MonkeyPatch) -> None:
    _force_tty(monkeypatch)
    monkeypatch.setenv("KONSOLE_VERSION", "230805")

    assert isinstance(widgets.image_widget(mode="halfcell"), HalfcellImage)
    assert isinstance(widgets.image_widget(mode="kitty"), TGPImage)
    assert isinstance(widgets.image_widget(mode="auto"), HalfcellImage)
