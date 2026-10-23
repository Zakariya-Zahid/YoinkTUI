"""URL entry behaviour: validation, inline errors, duplicate guards."""

from __future__ import annotations

import threading
import time
from types import SimpleNamespace

import pytest
from textual.widgets import Static

from yoinktui.app import YoinkTUIApp
from yoinktui.backend.errors import DownloadError, ErrorReason
from yoinktui.tui.screens import UrlScreen, clean_url
from yoinktui.tui.widgets import UrlInput


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  https://example.com/watch?v=1  ", "https://example.com/watch?v=1"),
        ("<https://example.com/v>", "https://example.com/v"),
        ("'http://example.com'", "http://example.com"),
    ],
)
def test_clean_url_accepts_and_trims(raw: str, expected: str) -> None:
    assert clean_url(raw) == expected


@pytest.mark.parametrize(
    "raw",
    ["", "   ", "not-a-url", "ftp://example.com/file", "https://"],
)
def test_clean_url_rejects_bad_input(raw: str) -> None:
    with pytest.raises(ValueError):
        clean_url(raw)


@pytest.mark.asyncio
async def test_invalid_url_shows_inline_error(app: YoinkTUIApp) -> None:
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, UrlScreen)
        screen = app.screen
        screen.query_one("#url", UrlInput).value = "not-a-url"
        await pilot.press("enter")
        await pilot.pause()

        status = screen.query_one("#probe-status", Static)
        assert not status.has_class("hidden")
        # Still on the URL screen: no modal/stacked error screens.
        assert isinstance(app.screen, UrlScreen)
        assert not screen.query_one("#url", UrlInput).disabled


@pytest.mark.asyncio
async def test_ascii_mode_uses_text_logo(app: YoinkTUIApp, monkeypatch: pytest.MonkeyPatch) -> None:
    from textual_image.widget import AutoImage

    app.config.ascii = True
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, UrlScreen)
        assert not list(app.screen.query(AutoImage))


@pytest.mark.asyncio
async def test_duplicate_submit_while_probing_is_ignored(app: YoinkTUIApp) -> None:
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, UrlScreen)
        screen._probing = True
        event = SimpleNamespace(value="https://example.com/v")
        screen._on_submit(event)  # type: ignore[arg-type]
        await pilot.pause()
        assert isinstance(app.screen, UrlScreen)
        assert screen._probing is True


@pytest.mark.asyncio
async def test_cancel_work_stops_inflight_probe(
    app: YoinkTUIApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    started = threading.Event()
    cancelled = threading.Event()

    def slow_probe(url: str, **kwargs):
        started.set()
        check = kwargs["cancel_check"]
        for _ in range(500):
            if check():
                cancelled.set()
                raise DownloadError("Probe cancelled", ErrorReason.CANCELLED)
            time.sleep(0.01)
        raise AssertionError("cancel_check was never true")

    monkeypatch.setattr("yoinktui.tui.screens.probe", slow_probe)

    async with app.run_test(size=(100, 30)) as pilot:
        screen = app.screen
        assert isinstance(screen, UrlScreen)
        screen.query_one("#url", UrlInput).value = "https://example.com/v"
        await pilot.press("enter")
        for _ in range(100):
            if started.is_set():
                break
            await pilot.pause(0.01)
        assert started.is_set()

        screen.cancel_work()
        for _ in range(100):
            if cancelled.is_set():
                break
            await pilot.pause(0.01)
        assert cancelled.is_set()
        assert isinstance(app.screen, UrlScreen)
