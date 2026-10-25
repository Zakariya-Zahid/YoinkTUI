"""Visual regression snapshots for the main shell screens."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from textual.app import App
from textual.widgets import Button, Static
from textual.widgets import _header as header_module

import yoinktui.tui.widgets as widgets
from yoinktui.backend.config import AppConfig
from yoinktui.backend.library import HistoryRecord
from yoinktui.backend.models import FormatInfo, MediaInfo
from yoinktui.backend.presets import builtin_presets
from yoinktui.backend.queue import DownloadQueue, QueueItem
from yoinktui.backend.ytdlp import (
    DependencyReport,
    DependencyStatus,
    PlaylistEntry,
    PlaylistInfo,
    ProgressEvent,
    Section,
)
from yoinktui.tui import screens
from yoinktui.tui.screens import (
    ClipModal,
    ConfirmModal,
    DownloadScreen,
    ErrorModal,
    FormatScreen,
    LibraryScreen,
    PlaylistScreen,
    PresetModal,
    QueueScreen,
    StartupErrorScreen,
    UrlScreen,
)

_CSS = Path(__file__).resolve().parents[2] / "src" / "yoinktui" / "tui" / "app.tcss"


class _FixedDatetime:
    """A deterministic stand-in for ``datetime`` in snapshot-sensitive widgets."""

    @staticmethod
    def now() -> datetime:
        return datetime(2026, 10, 23, 12, 0, 0)


@pytest.fixture
def frozen_time(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(header_module, "datetime", _FixedDatetime)
    monkeypatch.setattr(widgets, "datetime", _FixedDatetime)


class UrlSnapshotApp(App):
    CSS_PATH = str(_CSS)

    def __init__(self, theme: str | None = None) -> None:
        super().__init__()
        self.config = AppConfig(show_preview=False)
        if theme:
            self.theme = theme

    def on_mount(self) -> None:
        self.push_screen(UrlScreen())


class FormatSnapshotApp(App):
    CSS_PATH = str(_CSS)

    def __init__(self, info: MediaInfo, theme: str) -> None:
        super().__init__()
        self.info = info
        self.theme = theme
        self.config = AppConfig(show_preview=False, download_dir=Path("/tmp"))

    def on_mount(self) -> None:
        self.push_screen(FormatScreen(self.info))


class FrozenDownloadScreen(DownloadScreen):
    """A dashboard that never touches yt-dlp, the clock, or the real disk."""

    def _dl(self) -> None:
        pass

    def _tick(self) -> None:
        pass

    def _disk_free(self) -> str:
        return "42.0 GiB"


class DownloadSnapshotApp(App):
    CSS_PATH = str(_CSS)

    def __init__(self, theme: str) -> None:
        super().__init__()
        self.theme = theme
        self.config = AppConfig(show_preview=False, download_dir=Path("/tmp"))

    def on_mount(self) -> None:
        self.push_screen(
            FrozenDownloadScreen(
                url="https://example.com/v",
                selector="bv*+ba/b",
                out_template="/tmp/%(title)s.%(ext)s",
                extract_audio=False,
                title="Snapshot demo",
                expected_bytes=100_000_000,
                merge_format="mp4",
            )
        )


class ErrorSnapshotApp(App):
    CSS_PATH = str(_CSS)

    def __init__(self, theme: str) -> None:
        super().__init__()
        self.theme = theme
        self.config = AppConfig(show_preview=False)

    def on_mount(self) -> None:
        self.push_screen(
            ErrorModal(
                "Network error: connection timed out.\n\n"
                "Hint: check your internet connection and retry."
            )
        )


class ConfirmSnapshotApp(App):
    CSS_PATH = str(_CSS)

    def __init__(self, theme: str) -> None:
        super().__init__()
        self.theme = theme
        self.config = AppConfig(show_preview=False)

    def on_mount(self) -> None:
        self.push_screen(
            ConfirmModal(
                "Remove all queue items?",
                "Remove 3 item(s) from the queue?\n\nThis cannot be undone.",
                confirm_label="Remove all",
                danger=True,
            )
        )


class QueueSnapshotApp(App):
    CSS_PATH = str(_CSS)

    def __init__(self, theme: str) -> None:
        super().__init__()
        self.theme = theme
        self.config = AppConfig(show_preview=False, download_dir=Path("/tmp"))
        self.queue = DownloadQueue(
            items=[
                QueueItem(
                    url="https://example.com/one",
                    title="First download",
                    mode="video",
                    status="done",
                ),
                QueueItem(
                    url="https://example.com/two",
                    title="Second download",
                    mode="audio",
                    status="interrupted",
                ),
                QueueItem(
                    url="https://example.com/three",
                    title="Third download",
                    mode="video",
                    status="pending",
                ),
            ]
        )

    def on_mount(self) -> None:
        self.push_screen(QueueScreen(queue=self.queue))


class _FakeLibrary:
    def __init__(self) -> None:
        self.records = [
            HistoryRecord(
                id=1,
                url="https://example.com/one",
                title="A finished download",
                status="done",
                size=48_000_000,
                started_at="2026-10-23T12:00:00+00:00",
                # /proc exists but this subdirectory cannot, so the
                # missing-file detail is deterministic on every machine.
                path="/proc/yoinktui-snapshot/a-finished-download.mp4",
                mode="video",
            ),
            HistoryRecord(
                id=2,
                url="https://example.com/two",
                title="An interrupted download",
                status="interrupted",
                started_at="2026-10-22T12:00:00+00:00",
                error_reason="Interrupted before completion",
                mode="video",
            ),
        ]

    def list_records(self, query: str = "", *, limit: int = 500) -> list[HistoryRecord]:
        needle = query.lower()
        return [
            record
            for record in self.records
            if not needle or needle in record.title.lower() or needle in record.url.lower()
        ][:limit]

    def delete(self, record_id: int) -> None:
        self.records = [record for record in self.records if record.id != record_id]


class LibrarySnapshotApp(App):
    CSS_PATH = str(_CSS)

    def __init__(self, theme: str) -> None:
        super().__init__()
        self.theme = theme
        self.config = AppConfig(show_preview=False)
        self.library = _FakeLibrary()

    def on_mount(self) -> None:
        self.push_screen(LibraryScreen(store=self.library))  # type: ignore[arg-type]


class PlaylistSnapshotApp(App):
    CSS_PATH = str(_CSS)

    def __init__(self, theme: str) -> None:
        super().__init__()
        self.theme = theme
        self.config = AppConfig(show_preview=False)
        self.playlist = PlaylistInfo(
            title="A snapshot playlist",
            entries=[
                PlaylistEntry(
                    url="https://example.com/one",
                    title="Episode one",
                    id="one",
                    uploader="Channel",
                    duration=125,
                ),
                PlaylistEntry(
                    url="https://example.com/two",
                    title="Episode two",
                    id="two",
                    uploader="Channel",
                    duration=95,
                ),
            ],
        )

    def on_mount(self) -> None:
        self.push_screen(PlaylistScreen(self.playlist))


class PresetSnapshotApp(App):
    CSS_PATH = str(_CSS)

    def __init__(self, theme: str) -> None:
        super().__init__()
        self.theme = theme
        self.config = AppConfig(show_preview=False)

    def on_mount(self) -> None:
        self.push_screen(PresetModal(builtin_presets()))


class ClipSnapshotApp(App):
    CSS_PATH = str(_CSS)

    def __init__(self, theme: str) -> None:
        super().__init__()
        self.theme = theme
        self.config = AppConfig(show_preview=False)

    def on_mount(self) -> None:
        self.push_screen(ClipModal(125, Section(start=10, end=50, precise=True)))


class StartupSnapshotApp(App):
    CSS_PATH = str(_CSS)

    def __init__(self, theme: str) -> None:
        super().__init__()
        self.theme = theme
        self.config = AppConfig(show_preview=False)
        self.report = DependencyReport(
            (
                DependencyStatus("yt-dlp", "", "", False),
                DependencyStatus("ffmpeg", "/usr/bin/ffmpeg", "7.1", True),
            )
        )

    def on_mount(self) -> None:
        self.push_screen(StartupErrorScreen(self.report))


class MultiDownloadSnapshotApp(App):
    CSS_PATH = str(_CSS)

    def __init__(self, theme: str) -> None:
        super().__init__()
        self.theme = theme
        self.config = AppConfig(show_preview=False, download_dir=Path("/tmp"))

    def on_mount(self) -> None:
        self.push_screen(
            FrozenDownloadScreen(
                items=[
                    QueueItem(
                        url="https://example.com/one",
                        title="First item",
                        selector="bv*+ba/b",
                        out_template="/tmp/first.%(ext)s",
                        mode="video",
                    ),
                    QueueItem(
                        url="https://example.com/two",
                        title="Second item",
                        selector="ba/b",
                        out_template="/tmp/second.%(ext)s",
                        mode="audio",
                        extract_audio=True,
                    ),
                    QueueItem(
                        url="https://example.com/three",
                        title="Third item",
                        selector="bv*+ba/b",
                        out_template="/tmp/third.%(ext)s",
                        mode="video",
                    ),
                ]
            )
        )


def _info() -> MediaInfo:
    return MediaInfo(
        id="abc",
        title="Snapshot demo",
        uploader="YoinkTUI",
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
                fps=30,
                tbr=4000,
                filesize=100_000_000,
            ),
            FormatInfo(
                format_id="22",
                ext="mp4",
                vcodec="avc1",
                acodec="mp4a",
                width=1280,
                height=720,
                fps=30,
                tbr=2500,
                filesize=50_000_000,
            ),
        ],
        audio_formats=[
            FormatInfo(
                format_id="140",
                ext="m4a",
                vcodec="none",
                acodec="mp4a",
                abr=128,
                filesize=2_000_000,
            )
        ],
    )


def _seed_download(state: str):
    def seed(pilot) -> None:
        screen = pilot.app.screen
        assert isinstance(screen, FrozenDownloadScreen)
        screen._handle_event(
            ProgressEvent(
                kind="download",
                status="downloading",
                downloaded=42_000_000,
                total=100_000_000,
                speed=5_242_880,
                eta=11,
            )
        )
        if state == "paused":
            screen._paused = True
            screen._dashboard().set_paused(True)
            screen.query_one("#btn_pause", Button).label = "▶ Resume"
        elif state == "complete":
            screen._handle_event(
                ProgressEvent(
                    kind="download",
                    status="finished",
                    downloaded=100_000_000,
                    total=100_000_000,
                )
            )
            screen._handle_event(ProgressEvent(kind="done", filename="/tmp/Snapshot demo.mp4"))

    return seed


THEMES = ("textual-dark", "textual-light")
SIZES = ((100, 30), (120, 40))


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("size", SIZES)
def test_url_screen_snapshot(
    snap_compare,
    monkeypatch: pytest.MonkeyPatch,
    frozen_time,
    theme: str,
    size: tuple[int, int],
) -> None:
    # The real logo is a terminal-graphics image; use a plain wordmark so the
    # snapshot is independent of kitty/sixel support.
    monkeypatch.setattr(screens, "_brand_logo", lambda: Static("YoinkTUI", classes="title"))
    assert snap_compare(UrlSnapshotApp(theme=theme), terminal_size=size)


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("size", SIZES)
def test_format_screen_snapshot(
    snap_compare, frozen_time, theme: str, size: tuple[int, int]
) -> None:
    assert snap_compare(
        FormatSnapshotApp(_info(), theme=theme),
        terminal_size=size,
    )


@pytest.mark.parametrize("state", ["running", "paused", "complete"])
@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("size", SIZES)
def test_download_screen_snapshot(
    snap_compare,
    frozen_time,
    state: str,
    theme: str,
    size: tuple[int, int],
) -> None:
    assert snap_compare(
        DownloadSnapshotApp(theme=theme),
        terminal_size=size,
        run_before=_seed_download(state),
    )


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("size", SIZES)
def test_error_modal_snapshot(snap_compare, frozen_time, theme: str, size: tuple[int, int]) -> None:
    assert snap_compare(ErrorSnapshotApp(theme=theme), terminal_size=size)


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("size", SIZES)
def test_confirm_modal_snapshot(
    snap_compare, frozen_time, theme: str, size: tuple[int, int]
) -> None:
    assert snap_compare(ConfirmSnapshotApp(theme=theme), terminal_size=size)


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("size", SIZES)
def test_queue_screen_snapshot(
    snap_compare, frozen_time, theme: str, size: tuple[int, int]
) -> None:
    assert snap_compare(QueueSnapshotApp(theme=theme), terminal_size=size)


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("size", SIZES)
def test_library_screen_snapshot(
    snap_compare, frozen_time, theme: str, size: tuple[int, int]
) -> None:
    assert snap_compare(LibrarySnapshotApp(theme=theme), terminal_size=size)


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("size", SIZES)
def test_playlist_screen_snapshot(
    snap_compare, frozen_time, theme: str, size: tuple[int, int]
) -> None:
    assert snap_compare(PlaylistSnapshotApp(theme=theme), terminal_size=size)


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("size", SIZES)
def test_preset_modal_snapshot(
    snap_compare, frozen_time, theme: str, size: tuple[int, int]
) -> None:
    assert snap_compare(PresetSnapshotApp(theme=theme), terminal_size=size)


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("size", SIZES)
def test_clip_modal_snapshot(snap_compare, frozen_time, theme: str, size: tuple[int, int]) -> None:
    assert snap_compare(ClipSnapshotApp(theme=theme), terminal_size=size)


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("size", SIZES)
def test_startup_error_snapshot(
    snap_compare, frozen_time, theme: str, size: tuple[int, int]
) -> None:
    assert snap_compare(StartupSnapshotApp(theme=theme), terminal_size=size)


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("size", SIZES)
def test_multi_item_download_snapshot(
    snap_compare, frozen_time, theme: str, size: tuple[int, int]
) -> None:
    assert snap_compare(MultiDownloadSnapshotApp(theme=theme), terminal_size=size)
