"""Shared fixtures for TUI tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from yoinktui.app import AppConfig, YoinkTUIApp
from yoinktui.backend.ytdlp import DependencyReport, DependencyStatus


@pytest.fixture(autouse=True)
def isolated_state(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Never read or write the developer's real state, history, or queue."""
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    # Snapshots and theme tests must not depend on the developer's NO_COLOR.
    monkeypatch.delenv("NO_COLOR", raising=False)


@pytest.fixture
def config(tmp_path: Path) -> AppConfig:
    return AppConfig(
        download_dir=tmp_path / "downloads",
        show_preview=False,
        embed_metadata=False,
    )


@pytest.fixture
def app(config: AppConfig, monkeypatch: pytest.MonkeyPatch) -> YoinkTUIApp:
    report = DependencyReport(
        (
            DependencyStatus("yt-dlp", "/usr/bin/yt-dlp", "2026.08.19", True),
            DependencyStatus("ffmpeg", "/usr/bin/ffmpeg", "7.1", True),
        )
    )
    monkeypatch.setattr("yoinktui.app.check_dependencies", lambda: report)
    return YoinkTUIApp(config=config)
