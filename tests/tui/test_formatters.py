"""Tests for display formatters (shared by every screen)."""

from __future__ import annotations

from yoinktui.tui.widgets import human_size, human_speed, human_time


def test_human_size_uses_binary_units() -> None:
    assert human_size(None) == "—"
    assert human_size(0) == "—"
    assert human_size(1024) == "1.0 KiB"
    assert human_size(1024**2) == "1.0 MiB"
    assert human_size(1024**3) == "1.0 GiB"
    assert human_size(1024**4) == "1.0 TiB"


def test_human_speed_uses_binary_units() -> None:
    assert human_speed(None) == "—"
    assert human_speed(1024) == "1.0 KiB/s"
    assert human_speed(1024**2) == "1.0 MiB/s"


def test_human_time() -> None:
    assert human_time(None) == "—"
    assert human_time(-1) == "—"
    assert human_time(0) == "00:00"
    assert human_time(65) == "01:05"
    assert human_time(3725) == "1:02:05"
