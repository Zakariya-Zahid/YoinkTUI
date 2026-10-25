"""Queue, library, playlist, and preset flows for v0.3.0."""

from __future__ import annotations

import pytest

from yoinktui.app import YoinkTUIApp
from yoinktui.backend.config import AppConfig
from yoinktui.backend.models import FormatInfo, MediaInfo
from yoinktui.backend.presets import Preset
from yoinktui.backend.queue import QueueItem, QueueStore
from yoinktui.backend.ytdlp import PlaylistEntry, PlaylistInfo, ProgressEvent
from yoinktui.tui.screens import (
    ConfirmModal,
    DownloadScreen,
    FormatScreen,
    LibraryScreen,
    PlaylistScreen,
    PresetModal,
    QueueScreen,
    UrlScreen,
)


def _item(title: str = "Demo", url: str = "https://example.com/v") -> QueueItem:
    return QueueItem(
        url=url,
        title=title,
        selector="bv*+ba/b",
        out_template="/tmp/demo.%(ext)s",
        mode="video",
    )


class _FrozenDownloadScreen(DownloadScreen):
    """A dashboard whose worker and clock are inert for UI-only assertions."""

    def _dl(self) -> None:
        pass

    def _tick(self) -> None:
        pass


def _info() -> MediaInfo:
    return MediaInfo(
        id="abc",
        title="Demo",
        uploader="Zak",
        duration=125,
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
async def test_url_screen_queue_and_library_actions(app: YoinkTUIApp) -> None:
    async with app.run_test(size=(120, 40)) as pilot:
        url_screen = app.screen
        assert isinstance(url_screen, UrlScreen)
        url_screen.query_one("#btn_queue").press()
        queue_screen = await _wait_for(app, QueueScreen, pilot)
        assert queue_screen.queue is app.state.queue
        await pilot.pause(0.2)
        app.pop_screen()
        await pilot.pause(0.2)
        url_screen.query_one("#btn_library").press()
        library_screen = await _wait_for(app, LibraryScreen, pilot)
        assert library_screen.store is app.library
        await pilot.pause(0.2)


@pytest.mark.asyncio
async def test_queue_screen_starts_items_and_updates_status(
    app: YoinkTUIApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    events = [
        ProgressEvent(kind="download", status="downloading", downloaded=512, total=1024),
        ProgressEvent(kind="download", status="finished", downloaded=1024, total=1024),
        ProgressEvent(kind="done", filename="/tmp/demo.mp4"),
    ]
    monkeypatch.setattr("yoinktui.tui.screens.download", lambda *args, **kwargs: iter(events))
    first = _item("First")
    second = _item("Second", "https://example.com/second")
    app.state.queue.items = [first, second]

    async with app.run_test(size=(120, 40)) as pilot:
        app.push_screen(QueueScreen(queue=app.state.queue))
        queue_screen = await _wait_for(app, QueueScreen, pilot)
        assert queue_screen.query_one("#queue-table").row_count == 2
        assert not queue_screen.query_one("#queue-start").disabled

        await pilot.click("#queue-start")
        download_screen = await _wait_for(app, DownloadScreen, pilot)
        for _ in range(100):
            await pilot.pause(0.02)
            if download_screen._finished:
                break
        for _ in range(100):
            await pilot.pause(0.02)
            if download_screen._completed == 2:
                break
        assert download_screen._finished
        assert first.status == "done"
        assert second.status == "done"
        assert download_screen._completed == 2
        records = app.library.list_records()
        assert [record.status for record in records] == ["done", "done"]


@pytest.mark.asyncio
async def test_multi_item_dashboard_reuses_stream_rows_for_mixed_modes(
    app: YoinkTUIApp,
) -> None:
    audio = _item("Audio item")
    audio.mode = "audio"
    audio.extract_audio = True
    video = _item("Video item", "https://example.com/video")

    async with app.run_test(size=(120, 40)) as pilot:
        screen = _FrozenDownloadScreen(items=[audio, video])
        app.push_screen(screen)
        await _wait_for(app, _FrozenDownloadScreen, pilot)
        dashboard = screen._dashboard()

        screen._begin_item(0)
        first = dashboard.stream_item(0)
        second = dashboard.stream_item(1)
        assert first is not None and first.display
        assert second is not None and not second.display

        screen._begin_item(1)
        first = dashboard.stream_item(0)
        second = dashboard.stream_item(1)
        assert first is not None and first.display
        assert second is not None and second.display


@pytest.mark.asyncio
async def test_playlist_screen_queues_all_entries(app: YoinkTUIApp) -> None:
    playlist = PlaylistInfo(
        title="A playlist",
        entries=[
            PlaylistEntry(url="https://example.com/one", title="One", id="one"),
            PlaylistEntry(url="https://example.com/two", title="Two", id="two"),
        ],
    )
    async with app.run_test(size=(120, 40)) as pilot:
        app.push_screen(PlaylistScreen(playlist))
        playlist_screen = await _wait_for(app, PlaylistScreen, pilot)
        assert playlist_screen.query_one("#playlist-table").row_count == 2
        await pilot.click("#playlist-queue")
        queue_screen = await _wait_for(app, QueueScreen, pilot)
        assert queue_screen.query_one("#queue-table").row_count == 2
        assert [item.title for item in app.state.queue.items] == ["One", "Two"]


@pytest.mark.asyncio
async def test_playlist_screen_queues_all_entries_as_audio(app: YoinkTUIApp) -> None:
    playlist = PlaylistInfo(
        title="A playlist",
        entries=[
            PlaylistEntry(url="https://example.com/one", title="One", id="one"),
            PlaylistEntry(url="https://example.com/two", title="Two", id="two"),
        ],
    )
    async with app.run_test(size=(120, 40)) as pilot:
        app.push_screen(PlaylistScreen(playlist))
        playlist_screen = await _wait_for(app, PlaylistScreen, pilot)
        await pilot.click("#playlist-mode-audio")
        await pilot.pause()
        assert playlist_screen._mode == "audio"
        assert playlist_screen.query_one("#playlist-quality").disabled
        await pilot.click("#playlist-queue")
        queue_screen = await _wait_for(app, QueueScreen, pilot)
        assert queue_screen.query_one("#queue-table").row_count == 2
        items = app.state.queue.items
        assert [item.mode for item in items] == ["audio", "audio"]
        assert all(item.extract_audio for item in items)
        assert all(item.selector == "ba/b/bv*" for item in items)


@pytest.mark.asyncio
async def test_playlist_screen_queues_all_entries_with_selected_quality(
    app: YoinkTUIApp,
) -> None:
    playlist = PlaylistInfo(
        title="A playlist",
        entries=[
            PlaylistEntry(url="https://example.com/one", title="One", id="one"),
            PlaylistEntry(url="https://example.com/two", title="Two", id="two"),
        ],
    )
    async with app.run_test(size=(120, 40)) as pilot:
        app.push_screen(PlaylistScreen(playlist))
        playlist_screen = await _wait_for(app, PlaylistScreen, pilot)
        quality = playlist_screen.query_one("#playlist-quality")
        quality.value = 720
        await pilot.pause()
        assert playlist_screen._quality_cap == 720
        await pilot.click("#playlist-queue")
        await _wait_for(app, QueueScreen, pilot)
        assert all("height<=720" in item.selector for item in app.state.queue.items)


@pytest.mark.asyncio
async def test_playlist_screen_queues_selected_entries_only(app: YoinkTUIApp) -> None:
    playlist = PlaylistInfo(
        title="A playlist",
        entries=[
            PlaylistEntry(url="https://example.com/one", title="One", id="one"),
            PlaylistEntry(url="https://example.com/two", title="Two", id="two"),
        ],
    )
    async with app.run_test(size=(120, 40)) as pilot:
        app.push_screen(PlaylistScreen(playlist))
        playlist_screen = await _wait_for(app, PlaylistScreen, pilot)
        table = playlist_screen.query_one("#playlist-table")
        table.toggle_key("2")
        await pilot.pause()
        assert table.selected_count == 1
        await pilot.click("#playlist-queue-selected")
        queue_screen = await _wait_for(app, QueueScreen, pilot)
        assert queue_screen.query_one("#queue-table").row_count == 1
        assert [item.title for item in app.state.queue.items] == ["Two"]


@pytest.mark.asyncio
async def test_queue_screen_multi_select_removes_selected_items(app: YoinkTUIApp) -> None:
    app.state.queue.items = [
        _item("First"),
        _item("Second", "https://example.com/second"),
        _item("Third", "https://example.com/third"),
    ]

    async with app.run_test(size=(120, 40)) as pilot:
        app.push_screen(QueueScreen(queue=app.state.queue))
        queue_screen = await _wait_for(app, QueueScreen, pilot)
        table = queue_screen.query_one("#queue-table")
        await pilot.press("space")
        await pilot.press("down")
        await pilot.press("space")
        await pilot.pause()
        assert table.selected_count == 2

        await pilot.click("#queue-remove")
        await pilot.pause()
        assert queue_screen.query_one("#queue-table").row_count == 1
        assert [item.title for item in app.state.queue.items] == ["Third"]
        assert queue_screen.query_one("#queue-table").selected_count == 0


@pytest.mark.asyncio
async def test_queue_screen_starts_selected_items_only(
    app: YoinkTUIApp,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = [
        ProgressEvent(kind="download", status="downloading", downloaded=512, total=1024),
        ProgressEvent(kind="download", status="finished", downloaded=1024, total=1024),
        ProgressEvent(kind="done", filename="/tmp/demo.mp4"),
    ]
    monkeypatch.setattr("yoinktui.tui.screens.download", lambda *args, **kwargs: iter(events))
    first = _item("First")
    second = _item("Second", "https://example.com/second")
    app.state.queue.items = [first, second]

    async with app.run_test(size=(120, 40)) as pilot:
        app.push_screen(QueueScreen(queue=app.state.queue))
        await _wait_for(app, QueueScreen, pilot)
        await pilot.press("down")
        await pilot.press("space")
        await pilot.pause()
        await pilot.click("#queue-start")
        download_screen = await _wait_for(app, DownloadScreen, pilot)
        assert download_screen.items[0].title == "Second"


@pytest.mark.asyncio
async def test_queue_screen_removes_all_items_after_confirmation(
    app: YoinkTUIApp,
) -> None:
    app.state.queue.items = [
        _item("First"),
        _item("Second", "https://example.com/second"),
        _item("Third", "https://example.com/third"),
    ]

    async with app.run_test(size=(120, 40)) as pilot:
        app.push_screen(QueueScreen(queue=app.state.queue))
        queue_screen = await _wait_for(app, QueueScreen, pilot)
        assert queue_screen.query_one("#queue-table").row_count == 3

        await pilot.click("#queue-remove-all")
        modal = await _wait_for(app, ConfirmModal, pilot)
        assert "Remove all queue items?" in str(modal._title)
        await pilot.click("#confirm-ok")
        await pilot.pause()
        assert queue_screen.query_one("#queue-table").row_count == 0
        assert app.state.queue.items == []
        assert app.queue_store.load().items == []


@pytest.mark.asyncio
async def test_queue_uses_highlighted_format_not_initial_default(app: YoinkTUIApp) -> None:
    info = _info()
    info.video_formats.append(
        FormatInfo(
            format_id="135",
            ext="mp4",
            vcodec="avc1",
            acodec="none",
            width=640,
            height=360,
            tbr=800,
        )
    )

    async with app.run_test(size=(120, 40)) as pilot:
        screen = FormatScreen(info)
        app.push_screen(screen)
        await _wait_for(app, FormatScreen, pilot)

        table = screen.query_one("#table")
        table.move_cursor(row=1)
        await pilot.pause()

        # Moving the cursor is not a confirmation; the initial format remains
        # selected. The queue action must still use the row the user sees.
        assert screen._selected_format is not None
        assert screen._selected_format.format_id == "137"

        screen.action_queue()
        await pilot.pause()

        assert app.state.queue.items[-1].selector == "135+ba/135/b"


@pytest.mark.asyncio
async def test_preset_modal_applies_to_format_screen(app: YoinkTUIApp) -> None:
    app.config.presets["test"] = Preset(
        name="test",
        mode="audio",
        quality_cap=0,
        audio_format="flac",
    )
    async with app.run_test(size=(120, 40)) as pilot:
        format_screen = FormatScreen(_info())
        app.push_screen(format_screen)
        await _wait_for(app, FormatScreen, pilot)
        format_screen.action_preset()
        modal = await _wait_for(app, PresetModal, pilot)
        assert modal.query_one("#preset-table").row_count == len(app.config.presets)
        # Select the test preset and press Apply.
        table = modal.query_one("#preset-table")
        table.move_cursor(row=table.get_row_index("test"))
        await pilot.pause()
        await pilot.click("#preset-apply")
        await pilot.pause()
        assert format_screen._preset is not None
        assert format_screen._preset.name == "test"
        assert format_screen._mode == "audio"


@pytest.mark.asyncio
async def test_library_screen_lists_searches_and_deletes(app: YoinkTUIApp) -> None:
    record_id = app.library.record_start(_item("Alpha"))
    app.library.record_finish(record_id, status="done", path="/tmp/alpha.mp4", size=2048)
    app.library.record_start(_item("Beta", "https://example.com/beta"))

    async with app.run_test(size=(120, 40)) as pilot:
        app.push_screen(LibraryScreen(store=app.library))
        library = await _wait_for(app, LibraryScreen, pilot)
        table = library.query_one("#library-table")
        assert table.row_count == 2
        search = library.query_one("#library-search")
        search.value = "alpha"
        await pilot.pause()
        assert table.row_count == 1
        table.move_cursor(row=0)
        await pilot.pause()
        await pilot.click("#library-delete")
        await pilot.pause()
        assert table.row_count == 0
        assert app.library.get(record_id) is None


@pytest.mark.asyncio
async def test_startup_opens_queue_when_interrupted_items_exist(
    config: AppConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = QueueStore()
    queue = store.load()
    queue.items = [_item("Resume me")]
    queue.items[0].status = "interrupted"
    store.save(queue)

    from yoinktui.backend.ytdlp import DependencyReport, DependencyStatus

    report = DependencyReport(
        (
            DependencyStatus("yt-dlp", "/usr/bin/yt-dlp", "2026.08.19", True),
            DependencyStatus("ffmpeg", "/usr/bin/ffmpeg", "7.1", True),
        )
    )
    monkeypatch.setattr("yoinktui.app.check_dependencies", lambda: report)
    fresh = YoinkTUIApp(config=config)
    async with fresh.run_test(size=(120, 40)) as pilot:
        await _wait_for(fresh, QueueScreen, pilot)
        assert isinstance(fresh.screen, QueueScreen)
        assert fresh.screen.queue.items[0].status == "interrupted"
