"""Smoke tests: the app boots and owns its config/state."""

from __future__ import annotations

import pytest

from yoinktui.app import AppConfig, AppState, YoinkTUIApp
from yoinktui.backend.ytdlp import DependencyReport, DependencyStatus
from yoinktui.tui.screens import StartupErrorScreen, UrlScreen


@pytest.mark.asyncio
async def test_app_starts_on_url_screen(app: YoinkTUIApp) -> None:
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, UrlScreen)
        assert app.screen.query_one("#url")


@pytest.mark.asyncio
async def test_missing_dependency_shows_startup_screen(
    app: YoinkTUIApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = DependencyReport(
        (
            DependencyStatus("yt-dlp", None, None, False),
            DependencyStatus("ffmpeg", "/usr/bin/ffmpeg", "7.1", True),
        )
    )
    monkeypatch.setattr("yoinktui.app.check_dependencies", lambda: report)
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, StartupErrorScreen)


def test_config_and_state_are_per_instance(tmp_path) -> None:
    first = YoinkTUIApp(
        config=AppConfig(download_dir=tmp_path / "a"),
        state=AppState(last_url="https://a.example"),
    )
    second = YoinkTUIApp(
        config=AppConfig(download_dir=tmp_path / "b"),
        state=AppState(last_url="https://b.example"),
    )
    assert first.config is not second.config
    assert first.state is not second.state
    assert first.config.download_dir != second.config.download_dir
    assert first.state.last_url == "https://a.example"


@pytest.mark.asyncio
async def test_light_theme_config_is_applied(tmp_path) -> None:
    app = YoinkTUIApp(
        config=AppConfig(theme="light", download_dir=tmp_path / "light"),
        state=AppState(),
    )
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        assert app.theme == "textual-light"
        assert app.dark is False


def test_no_color_config_installs_monochrome_filter(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import os

    monkeypatch.delenv("NO_COLOR", raising=False)
    app = YoinkTUIApp(
        config=AppConfig(no_color=True, download_dir=tmp_path / "mono"),
        state=AppState(),
    )
    assert app.no_color is True
    # The bridge must not leak into later app instances.
    assert "NO_COLOR" not in os.environ
