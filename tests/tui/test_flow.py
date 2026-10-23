"""End-to-end screen flow tests with the backend faked out."""

from __future__ import annotations

import pytest

from yoinktui.app import YoinkTUIApp
from yoinktui.backend.models import FormatInfo, MediaInfo
from yoinktui.backend.ytdlp import ProgressEvent
from yoinktui.tui.screens import DownloadScreen, FormatScreen, UrlScreen
from yoinktui.tui.widgets import UrlInput


def _fake_info() -> MediaInfo:
    return MediaInfo(
        id="abc",
        title="Demo",
        uploader="Zak",
        duration=125,
        upload_date="20261023",
        webpage_url="https://example.com/v",
        video_formats=[
            FormatInfo(
                format_id="137",
                ext="mp4",
                vcodec="avc1",
                acodec="none",
                width=1920,
                height=1080,
                tbr=4000,
            )
        ],
        audio_formats=[
            FormatInfo(
                format_id="140",
                ext="m4a",
                vcodec="none",
                acodec="mp4a",
                abr=128,
            )
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


@pytest.mark.asyncio
async def test_probe_opens_format_screen(app: YoinkTUIApp, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("yoinktui.tui.screens.probe", lambda *args, **kwargs: _fake_info())
    async with app.run_test(size=(120, 40)) as pilot:
        screen = app.screen
        assert isinstance(screen, UrlScreen)
        screen.query_one("#url", UrlInput).value = "https://example.com/v"
        await pilot.press("enter")

        format_screen = await _wait_for(app, FormatScreen, pilot)
        assert format_screen.info.title == "Demo"
        assert app.state.last_url == "https://example.com/v"
        # The URL screen was not pushed twice.
        assert sum(isinstance(item, FormatScreen) for item in app.screen_stack) == 1


@pytest.mark.asyncio
async def test_download_flow_and_config_wiring(
    app: YoinkTUIApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    events = [
        ProgressEvent(
            kind="download",
            status="downloading",
            downloaded=512,
            total=1024,
            speed=2048.0,
            eta=1,
        ),
        ProgressEvent(kind="download", status="finished", downloaded=1024, total=1024),
        ProgressEvent(kind="done", filename="/tmp/demo.mkv"),
    ]
    monkeypatch.setattr("yoinktui.tui.screens.probe", lambda *args, **kwargs: _fake_info())
    monkeypatch.setattr("yoinktui.tui.screens.download", lambda *args, **kwargs: iter(events))

    async with app.run_test(size=(120, 40)) as pilot:
        url_screen = app.screen
        assert isinstance(url_screen, UrlScreen)
        url_screen.query_one("#url", UrlInput).value = "https://example.com/v"
        await pilot.press("enter")

        format_screen = await _wait_for(app, FormatScreen, pilot)
        format_screen._start_download()
        download_screen = await _wait_for(app, DownloadScreen, pilot)

        # Config policy is threaded into the dashboard.  The fake streams are
        # mp4/aac, so the mkv default falls back to mp4 (no needless remux).
        assert download_screen.merge_format == "mp4"
        assert download_screen.audio_format == app.config.audio_format
        assert download_screen.embed_metadata == app.config.embed_metadata
        assert app.state.current_info is not None
        assert app.state.mode == "video"

        for _ in range(100):
            await pilot.pause(0.02)
            if download_screen._finished:
                break
        assert download_screen._finished is True


@pytest.mark.asyncio
async def test_double_start_pushes_one_download_screen(
    app: YoinkTUIApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("yoinktui.tui.screens.probe", lambda *args, **kwargs: _fake_info())
    monkeypatch.setattr("yoinktui.tui.screens.download", lambda *args, **kwargs: iter(()))

    async with app.run_test(size=(120, 40)) as pilot:
        url_screen = app.screen
        assert isinstance(url_screen, UrlScreen)
        url_screen.query_one("#url", UrlInput).value = "https://example.com/v"
        await pilot.press("enter")

        format_screen = await _wait_for(app, FormatScreen, pilot)
        format_screen._start_download()
        format_screen._start_download()
        await _wait_for(app, DownloadScreen, pilot)

        assert sum(isinstance(item, DownloadScreen) for item in app.screen_stack) == 1
