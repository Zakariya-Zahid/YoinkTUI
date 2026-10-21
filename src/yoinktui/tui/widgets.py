"""Custom widgets for the TUI."""

from __future__ import annotations

import io
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from textual import on, work
from textual._easing import EASING as Easing
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.coordinate import Coordinate
from textual.css.query import NoMatches
from textual.events import Click, Resize
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import (
    DataTable,
    Input,
    Label,
    ProgressBar,
    RichLog,
    Static,
)
from textual_image.widget import AutoImage

if TYPE_CHECKING:
    from yoinktui.backend.models import FormatInfo


class ThumbnailCard(Static):
    """A card that shows the video thumbnail using the best available method.

    Falls back gracefully to a styled placeholder if the terminal doesn't
    support graphics protocols (kitty, sixel, iterm2).
    """

    image_url: reactive[str] = reactive("", init=False)
    _img: AutoImage | None = None

    def compose(self):
        self._img = AutoImage(id="thumb", classes="hidden")
        yield self._img
        yield Static("▶ LOADING", id="placeholder", classes="placeholder")

    def on_mount(self) -> None:
        # Set border title to distinguish the card visually
        self.border_title = "THUMBNAIL"
        # We'll animate the placeholder text while loading
        self._animate_placeholder()

    def _animate_placeholder(self) -> None:
        placeholder = self.query_one("#placeholder", Static)
        dots = ["", ".", "..", "..."]
        idx = 0

        def tick() -> None:
            nonlocal idx
            if not self.has_class("-loading"):
                return
            placeholder.update(f"▶ LOADING{dots[idx % len(dots)]}")
            idx += 1

        self.set_interval(0.4, tick)

    def watch_image_url(self, url: str) -> None:
        self.remove_class("-error")
        self.add_class("-loading")
        placeholder = self.query_one("#placeholder", Static)
        placeholder.update("▶ LOADING")
        if url:
            self._load_image(url)

    @work(exclusive=True, name="thumb-fetch")
    async def _load_image(self, url: str) -> None:
        import httpx

        data: io.BytesIO | None = None
        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = io.BytesIO(resp.content)
        except Exception:
            data = None

        if self.is_mounted:
            self._on_fetched(data)

    def _on_fetched(self, data: io.BytesIO | None) -> None:
        if data is None:
            self.remove_class("-loading")
            self.add_class("-error")
            self.query_one("#placeholder", Static).update("✗ NO IMAGE")
            return

        img = self._img
        if img:
            try:
                img.image = data
                img.remove_class("hidden")
                self.query_one("#placeholder", Static).add_class("hidden")
            except Exception:
                self.remove_class("-loading")
                self.add_class("-error")
                self.query_one("#placeholder", Static).update("✗ NO IMAGE")
                return

        self.remove_class("-loading")

    def reset(self) -> None:
        self.image_url = ""
        if self._img:
            self._img.image = None
            self._img.add_class("hidden")
        self.remove_class("-error", "-loading")
        placeholder = self.query_one("#placeholder", Static)
        placeholder.remove_class("hidden")
        placeholder.update("▶ NO URL")


class FormatTable(DataTable):
    """Interactive table of available formats.

    Emits `FormatSelected` when the user confirms a row.
    """

    class FormatSelected(Message):
        def __init__(self, fmt: "FormatInfo", row_key, cursor_row: int = 0) -> None:
            super().__init__()
            self.fmt = fmt
            self.row_key = row_key
            self.cursor_row = cursor_row

    DEFAULT_CSS = """
    FormatTable {
        height: 1fr;
    }
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._formats: list[FormatInfo] = []
        self._selected_row: int = -1

    def load(self, video_formats: list["FormatInfo"], audio_formats: list["FormatInfo"]) -> None:
        self.clear(columns=True)
        self._formats = []
        self._selected_row = -1
        self.add_columns(
            ("#", "idx"),
            ("Type", "type"),
            ("Quality", "quality"),
            ("Codec", "codec"),
            ("Ext", "ext"),
            ("Size", "size"),
            ("Note", "note"),
        )
        self.cursor_type = "row"
        self.show_cursor = True
        self.zebra_stripes = True

        # Video formats first
        for i, fmt in enumerate(video_formats):
            self._formats.append(fmt)
            size = self._human_size(fmt.size) if fmt.size else "—"
            # Include FPS in quality column if available
            quality = fmt.resolution
            if hasattr(fmt, "fps") and fmt.fps and fmt.fps > 1:
                quality = f"{fmt.resolution} {fmt.fps_label}fps"
            self.add_row(
                str(i + 1),
                "VIDEO",
                quality,
                fmt.codec_label,
                fmt.ext.upper(),
                size,
                fmt.format_note or fmt.dynamic_range or "",
                key=f"v{i}",
            )

        # Then audio formats
        for i, fmt in enumerate(audio_formats):
            self._formats.append(fmt)
            size = self._human_size(fmt.size) if fmt.size else "—"
            self.add_row(
                str(len(video_formats) + i + 1),
                "AUDIO",
                f"{fmt.abr:.0f}k" if fmt.abr else "—",
                fmt.codec_label,
                fmt.ext.upper(),
                size,
                fmt.format_note or "",
                key=f"a{i}",
            )

    def set_selected(self, row: int) -> None:
        """Mark a row as the confirmed-selected format, adding a bold marker."""
        if 0 <= row < len(self._formats):
            self._selected_row = row
            self.move_cursor(row=row)
            self.refresh()

    @staticmethod
    def _human_size(num: float) -> str:
        for unit in ("B", "KB", "MB", "GB"):
            if num < 1024:
                return f"{num:.1f}{unit}"
            num /= 1024
        return f"{num:.1f}TB"

    @on(DataTable.RowSelected)
    def _on_row_selected(self, event: DataTable.RowSelected) -> None:
        if 0 <= event.cursor_row < len(self._formats):
            self.post_message(self.FormatSelected(self._formats[event.cursor_row], event.row_key, event.cursor_row))


# ---------------------------------------------------------------------------
# Download dashboard (Steam-style download manager)
# ---------------------------------------------------------------------------


def human_size(num: float | None) -> str:
    """Format a byte count for display."""
    if not num:
        return "—"
    value = float(num)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024:
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def human_speed(bps: float | None) -> str:
    """Format a bytes-per-second rate for display."""
    if not bps:
        return "—"
    value = float(bps)
    for unit in ("B/s", "KB/s", "MB/s", "GB/s"):
        if value < 1024:
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB/s"


def human_time(seconds: float | None) -> str:
    """Format a duration as ``mm:ss`` (or ``h:mm:ss``)."""
    if seconds is None or seconds < 0:
        return "—"
    s = int(seconds)
    hours, rem = divmod(s, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


class StatTile(Static):
    """A small two-line label/value tile, like a download stat card."""

    DEFAULT_CSS = """
    StatTile {
        width: 1fr;
        height: 2;
        padding: 0 1;
        background: $surface;
        border-left: solid $border;
        content-align: left middle;
    }
    """

    def __init__(self, label: str, value: str = "—", **kwargs) -> None:
        super().__init__(markup=True, **kwargs)
        self._label = label
        self._value = value

    def on_mount(self) -> None:
        self._paint()

    def set_value(self, value: str) -> None:
        if value != self._value:
            self._value = value
            self._paint()

    def _paint(self) -> None:
        self.update(f"[dim]{self._label}[/dim]\n[bold]{self._value}[/bold]")


class DownloadQueueItem(Container):
    """One stream in the download queue with its own mini progress bar."""

    DEFAULT_CSS = """
    DownloadQueueItem {
        height: 2;
        layout: vertical;
        background: $surface;
        border-left: thick $border;
        padding: 0 1;
    }
    DownloadQueueItem > .q-head {
        height: 1;
        layout: horizontal;
    }
    DownloadQueueItem .q-label {
        width: 1fr;
        color: $text;
        text-style: bold;
    }
    DownloadQueueItem .q-state {
        width: auto;
        color: $text-muted;
    }
    DownloadQueueItem .q-bytes {
        width: 26;
        color: $text-muted;
        text-align: right;
    }
    DownloadQueueItem ProgressBar {
        height: 1;
        width: 100%;
    }
    DownloadQueueItem.active {
        border-left: thick $accent;
        background: $surface-lighten-1;
    }
    DownloadQueueItem.done {
        border-left: thick $success;
    }
    DownloadQueueItem.paused {
        border-left: thick $warning;
    }
    DownloadQueueItem.active .q-state {
        color: $accent;
    }
    DownloadQueueItem.done .q-state {
        color: $success;
    }
    DownloadQueueItem.paused .q-state {
        color: $warning;
    }
    """

    def __init__(self, icon: str, label: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self._icon = icon
        self._label = label

    def compose(self) -> ComposeResult:
        with Horizontal(classes="q-head"):
            yield Static(f"{self._icon} {self._label}", classes="q-label")
            yield Static("· Queued", classes="q-state")
            yield Static("", classes="q-bytes")
        yield ProgressBar(total=1, show_percentage=False, show_eta=False)

    # -- state helpers ----------------------------------------------------

    def _set_state(self, state: str, text: str) -> None:
        self.remove_class("active", "done", "paused", "pending")
        self.add_class(state)
        self.query_one(".q-state", Static).update(text)

    def _set_bar(self, fraction: float) -> None:
        self.query_one(ProgressBar).update(total=1, progress=min(max(fraction, 0.0), 1.0))

    def _set_bytes(self, text: str) -> None:
        self.query_one(".q-bytes", Static).update(text)

    def set_pending(self) -> None:
        self._set_state("pending", "· Queued")
        self._set_bar(0.0)
        self._set_bytes("")

    def set_active(self) -> None:
        if not self.has_class("active"):
            self._set_state("active", "↓ Downloading")

    def set_paused(self) -> None:
        self._set_state("paused", "⏸ Paused")

    def set_progress(self, downloaded: float, total: float | None) -> None:
        fraction = (downloaded / total) if total else 0.0
        self._set_bar(fraction)
        if total:
            pct = f"{fraction * 100:.0f}%"
            self._set_bytes(f"{human_size(downloaded)} / {human_size(total)}  {pct}")
        else:
            self._set_bytes(human_size(downloaded))

    def set_done(self, size: float | None = None) -> None:
        self._set_state("done", "✓ Completed")
        self._set_bar(1.0)
        if size:
            self._set_bytes(human_size(size))


class DownloadDashboard(Container):
    """Steam-like download manager panel: queue, stats, overall bar, log."""

    DEFAULT_CSS = """
    DownloadDashboard {
        height: 1fr;
        width: 100%;
        layout: vertical;
    }
    DownloadDashboard > .dl-top {
        height: 3;
        layout: horizontal;
    }
    DownloadDashboard .dl-badge {
        width: 4;
        height: 3;
        content-align: center middle;
        color: $accent;
        text-style: bold;
    }
    DownloadDashboard .dl-titles {
        width: 1fr;
        height: 3;
        layout: vertical;
    }
    DownloadDashboard .dl-kicker {
        height: 1;
        color: $text-muted;
        text-style: bold;
    }
    DownloadDashboard .dl-title {
        height: 2;
        color: $text;
        text-style: bold;
        overflow: hidden;
    }
    DownloadDashboard .dl-status {
        width: auto;
        height: 3;
        padding: 0 1;
        content-align: right middle;
        text-style: bold;
    }
    DownloadDashboard .dl-status.downloading {
        color: $accent;
    }
    DownloadDashboard .dl-status.paused {
        color: $warning;
    }
    DownloadDashboard .dl-status.complete {
        color: $success;
    }
    DownloadDashboard .dl-status.error {
        color: $error;
    }
    DownloadDashboard .dl-phase {
        height: 1;
        color: $text-muted;
        margin-bottom: 1;
        text-style: italic;
    }
    DownloadDashboard .dl-queue {
        height: auto;
        margin-bottom: 1;
    }
    DownloadDashboard .dl-stats {
        height: 2;
        margin-bottom: 1;
    }
    DownloadDashboard .dl-overall {
        height: 1;
        width: 100%;
    }
    DownloadDashboard .dl-bytes {
        height: 1;
        color: $text-muted;
    }
    DownloadDashboard .dl-log {
        height: 1fr;
        min-height: 5;
        margin-top: 1;
        background: $surface;
        border: solid $border;
        padding: 0 1;
        overflow-y: auto;
        scrollbar-size-vertical: 1;
    }
    """

    def __init__(
        self,
        *,
        title: str,
        extract_audio: bool = False,
        disk_free: str = "—",
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._title = title or "Untitled"
        self._extract_audio = extract_audio
        self._disk_free = disk_free
        self._passes = 1 if extract_audio else 2
        self._peak = 0.0
        self._status_text = "● CONNECTING"

    def compose(self) -> ComposeResult:
        with Horizontal(classes="dl-top"):
            yield Static("⬇", classes="dl-badge")
            with Vertical(classes="dl-titles"):
                yield Static("DOWNLOAD MANAGER", classes="dl-kicker")
                yield Static(self._title, classes="dl-title")
            yield Static("● CONNECTING", classes="dl-status downloading")
        yield Static("Preparing download…", classes="dl-phase")
        with Vertical(classes="dl-queue"):
            if self._extract_audio:
                yield DownloadQueueItem("🎵", "Audio stream", id="q-audio")
            else:
                yield DownloadQueueItem("▶", "Video stream", id="q-video")
                yield DownloadQueueItem("🎵", "Audio stream", id="q-audio")
        with Horizontal(classes="dl-stats"):
            yield StatTile("SPEED", "—", id="stat-speed")
            yield StatTile("ETA", "—", id="stat-eta")
            yield StatTile("PEAK", "—", id="stat-peak")
            yield StatTile("ELAPSED", "00:00", id="stat-elapsed")
            yield StatTile("DISK FREE", self._disk_free, id="stat-disk")
        yield ProgressBar(
            id="dl-overall",
            total=1,
            show_percentage=True,
            show_eta=False,
            classes="dl-overall",
        )
        yield Static("", classes="dl-bytes")
        yield RichLog(classes="dl-log", markup=True, max_lines=300, auto_scroll=True)

    def on_mount(self) -> None:
        for item in self.query(DownloadQueueItem):
            item.set_pending()
        self.add_event("Connecting to media source…")

    # -- public API -------------------------------------------------------

    @property
    def passes(self) -> int:
        return self._passes

    def item(self, index: int) -> DownloadQueueItem | None:
        items = list(self.query(DownloadQueueItem))
        return items[index] if 0 <= index < len(items) else None

    def add_event(self, message: str, tone: str = "info") -> None:
        icons = {
            "info": "[cyan]•[/cyan]",
            "ok": "[green]✓[/green]",
            "warn": "[yellow]⚠[/yellow]",
            "err": "[red]✗[/red]",
        }
        stamp = datetime.now().strftime("%H:%M:%S")
        try:
            self.query_one(RichLog).write(
                f"[dim]{stamp}[/dim]  {icons.get(tone, icons['info'])} {message}"
            )
        except NoMatches:  # pragma: no cover - log not mounted yet
            pass

    def set_status(self, text: str, state: str = "downloading") -> None:
        if text == self._status_text:
            return
        self._status_text = text
        status = self.query_one(".dl-status", Static)
        status.update(text)
        status.remove_class("downloading", "paused", "complete", "error")
        status.add_class(state)

    def set_phase(self, text: str) -> None:
        self.query_one(".dl-phase", Static).update(text)

    def set_elapsed(self, seconds: float) -> None:
        self.query_one("#stat-elapsed", StatTile).set_value(human_time(seconds))

    def mark_done(self, index: int, size: float | None = None) -> None:
        item = self.item(index)
        if item is not None:
            item.set_done(size)

    def update_download(
        self,
        downloaded: float,
        total: float | None,
        speed: float | None,
        eta: float | None,
        pass_num: int,
    ) -> None:
        # Everything before the current pass is complete.
        for index in range(min(pass_num, self._passes)):
            item = self.item(index)
            if item is not None and not item.has_class("done"):
                item.set_done()

        current = self.item(pass_num)
        if current is not None:
            current.set_active()
            current.set_progress(downloaded, total)

        if speed:
            self._peak = max(self._peak, speed)

        fraction = (downloaded / total) if total else 0.0
        overall = min((pass_num + fraction) / self._passes, 1.0)
        self.query_one("#dl-overall", ProgressBar).update(total=1, progress=overall)

        self.query_one("#stat-speed", StatTile).set_value(human_speed(speed))
        self.query_one("#stat-eta", StatTile).set_value(human_time(eta))
        self.query_one("#stat-peak", StatTile).set_value(human_speed(self._peak))
        total_text = human_size(total) if total else "?"
        self.query_one(".dl-bytes", Static).update(
            f"Stream {pass_num + 1} of {self._passes}   "
            f"[bold]{human_size(downloaded)}[/bold] / {total_text}   "
            f"[dim]overall {overall * 100:.0f}%[/dim]"
        )

    def update_postprocess(self, section: str) -> None:
        self.set_status("⚙ PROCESSING", "downloading")
        self.set_phase(f"Post-processing: {section or 'merging streams'}")
        self.query_one("#stat-speed", StatTile).set_value("—")
        self.query_one("#stat-eta", StatTile).set_value("—")

    def set_paused(self, paused: bool) -> None:
        if paused:
            self.set_status("⏸ PAUSED", "paused")
            self.set_phase("Download paused — press P to resume")
            self.query_one("#stat-speed", StatTile).set_value("Paused")
            self.query_one("#stat-eta", StatTile).set_value("—")
            for item in self.query(DownloadQueueItem).filter(".active"):
                item.set_paused()
        else:
            self.set_status("● DOWNLOADING", "downloading")
            self.query_one("#stat-speed", StatTile).set_value("—")
            for item in self.query(DownloadQueueItem).filter(".paused"):
                item.set_active()

    def finish(self, path: str) -> None:
        self.set_status("✓ COMPLETE", "complete")
        self.set_phase("Download finished")
        for item in self.query(DownloadQueueItem):
            item.set_done()
        self.query_one("#dl-overall", ProgressBar).update(total=1, progress=1)
        self.query_one("#stat-speed", StatTile).set_value("—")
        self.query_one("#stat-eta", StatTile).set_value("—")
        self.query_one(".dl-bytes", Static).update(f"[green]Saved to[/green] {path}")
        self.add_event(f"Saved to {path}", "ok")

    def error(self, message: str) -> None:
        self.set_status("✗ FAILED", "error")
        self.set_phase(message)
        self.query_one("#stat-speed", StatTile).set_value("—")
        self.query_one("#stat-eta", StatTile).set_value("—")
        self.add_event(message, "err")


class InfoPanel(Container):
    """Metadata panel shown alongside the thumbnail."""

    DEFAULT_CSS = """
    InfoPanel {
        layout: vertical;
    }
    InfoPanel .row {
        layout: horizontal;
        height: 1;
    }
    InfoPanel .label {
        width: 14;
        color: $text-muted;
    }
    InfoPanel .value {
        width: 1fr;
        color: $text;
    }
    """

    def compose(self):
        from textual.widgets import Static
        from textual.containers import Horizontal

        yield Horizontal(
            Static("Title:", classes="label"),
            Static("", id="title", classes="value"),
            classes="row",
        )
        yield Horizontal(
            Static("Channel:", classes="label"),
            Static("", id="channel", classes="value"),
            classes="row",
        )
        yield Horizontal(
            Static("Duration:", classes="label"),
            Static("", id="duration", classes="value"),
            classes="row",
        )
        yield Horizontal(
            Static("Uploaded:", classes="label"),
            Static("", id="date", classes="value"),
            classes="row",
        )
        yield Horizontal(
            Static("Views:", classes="label"),
            Static("", id="views", classes="value"),
            classes="row",
        )
        yield Horizontal(
            Static("Max Quality:", classes="label"),
            Static("", id="maxq", classes="value"),
            classes="row",
        )

    def load(self, info) -> None:
        from yoinktui.backend.models import MediaInfo
        info: MediaInfo
        self.query_one("#title", Static).update(info.title or "—")
        self.query_one("#channel", Static).update(info.display_channel or "—")
        dur = f"{int(info.duration)//60}:{int(info.duration)%60:02d}" if info.duration else "—"
        self.query_one("#duration", Static).update(dur)
        self.query_one("#date", Static).update(info.upload_date or "—")
        views = f"{int(info.view_count):,}" if info.view_count else "—"
        self.query_one("#views", Static).update(views)
        self.query_one("#maxq", Static).update(f"{info.max_video_height}p" if info.max_video_height else "—")


class UrlInput(Input):
    """URL input with validation feedback."""

    BINDINGS = [("enter", "submit", "Submit")]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, placeholder="Paste a YouTube URL (or any yt-dlp supported link)...", **kwargs)
        self._valid = True

    def validate(self, value: str) -> str:
        """Called on every keystroke; we just track validity."""
        import re
        # Very loose check — yt-dlp will do real validation
        self._valid = bool(value.strip())
        if self._valid:
            self.remove_class("-invalid")
        else:
            self.add_class("-invalid")
        return value

    def action_submit(self) -> None:
        if self._valid:
            self.post_message(Input.Submitted(self, self.value))


class StatusToast(RichLog):
    """Transient toast messages at the bottom."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, max_lines=4, markup=True, auto_scroll=True, **kwargs)

    @staticmethod
    def _timestamp() -> str:
        """Return a dimmed HH:MM timestamp string."""
        return f"[dim]{datetime.now().strftime('%H:%M')}[/dim]"

    def success(self, message: str) -> None:
        self.write(f"{self._timestamp()} [green]✓[/green] {message}")

    def warning(self, message: str) -> None:
        self.write(f"{self._timestamp()} [yellow]⚠[/yellow] {message}")

    def error(self, message: str) -> None:
        self.write(f"{self._timestamp()} [red]✗[/red] {message}")

    def info(self, message: str) -> None:
        self.write(f"{self._timestamp()} [cyan]ℹ[/cyan] {message}")


class ModalDialog(Container):
    """Base modal dialog container."""

    def __init__(self, title: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.border_title = title
