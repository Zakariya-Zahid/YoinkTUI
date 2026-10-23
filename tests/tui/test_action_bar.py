"""Regression tests for the compact action bar and probe status."""

from __future__ import annotations

import pytest

from yoinktui.app import YoinkTUIApp
from yoinktui.backend.models import FormatInfo, MediaInfo
from yoinktui.backend.ytdlp import ProgressEvent
from yoinktui.tui.screens import FormatScreen, UrlScreen
from yoinktui.tui.widgets import UrlInput


def _fake_info() -> MediaInfo:
    return MediaInfo(
        id="abc",
        title="Demo",
        duration=125,
        webpage_url="https://example.com/v",
        video_formats=[
            FormatInfo(format_id="137", ext="mp4", vcodec="avc1", height=1080),
        ],
        audio_formats=[
            FormatInfo(format_id="140", ext="m4a", acodec="mp4a", abr=128),
        ],
    )


async def _open_format_screen(app, pilot, monkeypatch) -> FormatScreen:
    monkeypatch.setattr("yoinktui.tui.screens.probe", lambda *args, **kwargs: _fake_info())
    url_screen = app.screen
    assert isinstance(url_screen, UrlScreen)
    url_screen.query_one("#url", UrlInput).value = "https://example.com/v"
    await pilot.press("enter")
    for _ in range(100):
        await pilot.pause(0.02)
        if isinstance(app.screen, FormatScreen):
            return app.screen
    raise AssertionError("FormatScreen not pushed")


@pytest.mark.asyncio
async def test_action_bar_has_visible_labels(app: YoinkTUIApp, monkeypatch) -> None:
    async with app.run_test(size=(120, 40)) as pilot:
        format_screen = await _open_format_screen(app, pilot, monkeypatch)
        labels = {
            button_id: format_screen.query_one(f"#{button_id}").label.plain
            for button_id in (
                "btn_video",
                "btn_vonly",
                "btn_audio",
                "btn_clip",
                "btn_download",
            )
        }
        assert "Video+Audio" in labels["btn_video"]
        assert "Video" in labels["btn_vonly"]
        assert "Audio" in labels["btn_audio"]
        assert "Clip" in labels["btn_clip"]
        assert "Download" in labels["btn_download"]


@pytest.mark.asyncio
async def test_mode_buttons_switch_mode(app: YoinkTUIApp, monkeypatch) -> None:
    async with app.run_test(size=(120, 40)) as pilot:
        format_screen = await _open_format_screen(app, pilot, monkeypatch)
        await pilot.click("#btn_vonly")
        await pilot.pause()
        assert format_screen._mode == "vonly"

        await pilot.click("#btn_audio")
        await pilot.pause()
        assert format_screen._mode == "audio"


@pytest.mark.asyncio
async def test_download_button_starts_download(app: YoinkTUIApp, monkeypatch) -> None:
    from yoinktui.tui.screens import DownloadScreen

    monkeypatch.setattr(
        "yoinktui.tui.screens.download",
        lambda *args, **kwargs: iter([ProgressEvent(kind="done", filename="/tmp/demo.mkv")]),
    )
    async with app.run_test(size=(120, 40)) as pilot:
        await _open_format_screen(app, pilot, monkeypatch)
        await pilot.click("#btn_download")
        for _ in range(100):
            await pilot.pause(0.02)
            if isinstance(app.screen, DownloadScreen):
                break
        assert isinstance(app.screen, DownloadScreen)


@pytest.mark.asyncio
async def test_unwritable_download_dir_keeps_format_screen(
    app: YoinkTUIApp, monkeypatch, tmp_path
) -> None:
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")
    app.config.download_dir = blocker

    async with app.run_test(size=(120, 40)) as pilot:
        format_screen = await _open_format_screen(app, pilot, monkeypatch)
        await pilot.click("#btn_download")
        await pilot.pause()
        assert isinstance(app.screen, FormatScreen)
        assert format_screen._download_started is False


@pytest.mark.asyncio
async def test_probe_status_hidden_after_success(app: YoinkTUIApp, monkeypatch) -> None:
    async with app.run_test(size=(100, 30)) as pilot:
        url_screen = app.screen
        assert isinstance(url_screen, UrlScreen)
        await _open_format_screen(app, pilot, monkeypatch)
        status = url_screen.query_one("#probe-status")
        assert status.has_class("hidden")
