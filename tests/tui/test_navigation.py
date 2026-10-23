"""Navigation contract: documented Escape semantics and focus restoration."""

from __future__ import annotations

import time

import pytest

from yoinktui.app import YoinkTUIApp
from yoinktui.backend.models import FormatInfo, MediaInfo
from yoinktui.backend.ytdlp import ProgressEvent
from yoinktui.tui.screens import ClipModal, DownloadScreen, FormatScreen, UrlScreen
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


async def _wait_for(app, screen_type, pilot, attempts: int = 100):
    for _ in range(attempts):
        await pilot.pause(0.02)
        if isinstance(app.screen, screen_type):
            return app.screen
    raise AssertionError(
        f"{screen_type.__name__} was not pushed; current={type(app.screen).__name__}"
    )


async def _open_format_screen(app, pilot, monkeypatch) -> FormatScreen:
    monkeypatch.setattr("yoinktui.tui.screens.probe", lambda *args, **kwargs: _fake_info())
    url_screen = app.screen
    assert isinstance(url_screen, UrlScreen)
    url_screen.query_one("#url", UrlInput).value = "https://example.com/v"
    await pilot.press("enter")
    return await _wait_for(app, FormatScreen, pilot)


@pytest.mark.asyncio
async def test_escape_on_url_screen_quits(app: YoinkTUIApp, monkeypatch) -> None:
    calls: list[bool] = []
    monkeypatch.setattr(app, "exit", lambda *args, **kwargs: calls.append(True))
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, UrlScreen)
        await pilot.press("escape")
        await pilot.pause()
        assert calls == [True]


@pytest.mark.asyncio
async def test_escape_on_format_screen_goes_back_and_restores_focus(
    app: YoinkTUIApp, monkeypatch
) -> None:
    async with app.run_test(size=(120, 40)) as pilot:
        await _open_format_screen(app, pilot, monkeypatch)
        await pilot.press("escape")
        await pilot.pause()

        assert isinstance(app.screen, UrlScreen)
        url_input = app.screen.query_one("#url", UrlInput)
        assert url_input.disabled is False
        assert app.focused is url_input


@pytest.mark.asyncio
async def test_escape_on_clip_modal_dismisses(app: YoinkTUIApp, monkeypatch) -> None:
    async with app.run_test(size=(120, 40)) as pilot:
        format_screen = await _open_format_screen(app, pilot, monkeypatch)
        await pilot.press("c")
        await _wait_for(app, ClipModal, pilot)
        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, FormatScreen)
        assert format_screen._section is None


@pytest.mark.asyncio
async def test_escape_on_download_screen_cancels(app: YoinkTUIApp, monkeypatch) -> None:
    def slow_download(*args, **kwargs):
        control = kwargs["control"]
        while not control.cancelled:
            time.sleep(0.01)
        yield ProgressEvent(kind="log", text="cancelled")

    monkeypatch.setattr("yoinktui.tui.screens.download", slow_download)
    async with app.run_test(size=(120, 40)) as pilot:
        format_screen = await _open_format_screen(app, pilot, monkeypatch)
        format_screen._start_download()
        download_screen = await _wait_for(app, DownloadScreen, pilot)

        await pilot.press("escape")
        await pilot.pause()
        assert download_screen._cancelled is True
        assert download_screen._control.cancelled is True
