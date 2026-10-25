"""Screens: URL input, format picker, download progress, completion."""

from __future__ import annotations

import contextlib
import io
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, replace
from importlib.resources import files as resource_files
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from PIL import Image as PILImage
from textual import on, work
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen, Screen
from textual.timer import Timer
from textual.widgets import Button, DataTable, Footer, Header, Input, Select, Static, Switch
from textual_image.widget import AutoImage

from yoinktui.backend.config import AppConfig, load_last_url, save_last_url
from yoinktui.backend.errors import DownloadError
from yoinktui.backend.library import HistoryRecord, LibraryStore
from yoinktui.backend.models import FormatInfo, MediaInfo
from yoinktui.backend.presets import Preset
from yoinktui.backend.queue import DownloadPolicy, DownloadQueue, QueueItem, QueueStore
from yoinktui.backend.ytdlp import (
    DependencyReport,
    DownloadControl,
    PlaylistEntry,
    PlaylistInfo,
    ProgressEvent,
    Section,
    download,
    format_timecode,
    parse_timecode,
    probe,
    probe_playlist,
)
from yoinktui.tui.markup import escape_markup as escape
from yoinktui.tui.widgets import (
    DownloadDashboard,
    FormatTable,
    InfoPanel,
    SelectableTable,
    StatusToast,
    ThumbnailCard,
    UrlInput,
    human_size,
    human_time,
)

if TYPE_CHECKING:
    pass


_BANNER = (
    "[bold cyan]╔═══════════════════╗[/bold cyan]\n"
    "[bold cyan]║   YoinkTUI  ⬇     ║[/bold cyan]\n"
    "[bold cyan]╚═══════════════════╝[/bold cyan]"
)

# Matches $surface-raised in app.tcss so the flattened logo blends into the card.
_LOGO_BG = (0x1A, 0x22, 0x34)


def _brand_logo() -> AutoImage:
    """YoinkTUI wordmark for the dark UI (light-on-transparent variant).

    textual-image drops the alpha channel, so the transparent PNG is
    composited onto the card background first.
    """
    data = resource_files("yoinktui").joinpath("assets", "logo-dark.png").read_bytes()
    with PILImage.open(io.BytesIO(data)) as source:
        rgba = source.convert("RGBA")
        background = PILImage.new("RGBA", rgba.size, (*_LOGO_BG, 255))
        flat = PILImage.alpha_composite(background, rgba).convert("RGB")
    return AutoImage(
        flat,
        classes="logo",
        on_error=lambda _: Static(_BANNER, classes="title", markup=True),
    )


def clean_url(value: str) -> str:
    """Trim pasted text and reject obviously invalid URLs before probing."""
    url = value.strip().strip("<>\"'")
    if not url:
        raise ValueError("Paste a URL first.")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("URL must start with http:// or https://")
    if not parsed.netloc:
        raise ValueError("That doesn't look like a complete URL.")
    return url


class UrlScreen(Screen):
    """First screen: enter a URL, press Enter to probe."""

    BINDINGS = [
        ("escape", "quit", "Quit"),
        ("ctrl+c", "quit", "Quit"),
    ]

    def __init__(self, initial_url: str = "") -> None:
        super().__init__()
        self.initial_url = initial_url
        self._probing = False
        self._pushed = False
        self._cancel_probe = False
        self._spinner_timer: Timer | None = None

    def compose(self) -> ComposeResult:
        config = getattr(self.app, "config", None)
        with Container(classes="center-box"):
            with Container(classes="logo-wrap"):
                if config is not None and config.ascii:
                    yield Static(_BANNER, classes="title", markup=True)
                else:
                    try:
                        yield _brand_logo()
                    except (OSError, ModuleNotFoundError):
                        yield Static(_BANNER, classes="title", markup=True)
            yield Static(
                "[dim]Powered by yt-dlp  •  1000+ supported sites[/dim]",
                classes="version",
                markup=True,
            )
            yield Static("Paste a URL to discover available formats", classes="subtitle")
            yield UrlInput(id="url", classes="url-input")
            with Horizontal(classes="url-actions"):
                yield Button("Playlist", id="btn_playlist")
                yield Button("Queue", id="btn_queue")
                yield Button("Library", id="btn_library")
            # Inline probe status (hidden by default)
            yield Static("", id="probe-status", classes="probe-status hidden")
        yield Footer()

    def on_mount(self) -> None:
        last_url = (
            self.initial_url
            or getattr(getattr(self.app, "state", None), "last_url", "")
            or load_last_url()
        )
        if last_url:
            self.query_one("#url", UrlInput).value = last_url
        self._update_queue_button()
        self._fit_brand()
        self.query_one("#url", UrlInput).focus()

    def on_screen_resume(self) -> None:
        """Re-enable the input when a pushed screen pops back."""
        self._probing = False
        self._pushed = False
        self._cancel_probe = False
        with contextlib.suppress(Exception):
            url_input = self.query_one("#url", UrlInput)
            url_input.disabled = False
            last_url = getattr(getattr(self.app, "state", None), "last_url", "")
            if last_url:
                url_input.value = last_url
            url_input.focus()
            self._update_queue_button()

    def _update_queue_button(self) -> None:
        with contextlib.suppress(Exception):
            state = getattr(self.app, "state", None)
            count = len(state.queue.resumable()) if state is not None else 0
            self.query_one("#btn_queue", Button).label = f"Queue ({count})" if count else "Queue"

    def cancel_work(self) -> None:
        """Stop an in-flight probe so quitting never leaves yt-dlp behind."""
        self._cancel_probe = True
        if self._spinner_timer is not None:
            self._spinner_timer.stop()

    def on_unmount(self) -> None:
        self.cancel_work()

    def action_quit(self) -> None:
        self.cancel_work()
        self.app.exit()

    def on_resize(self) -> None:
        self._fit_brand()

    def _fit_brand(self) -> None:
        """Hide the wordmark on very short terminals so the input stays usable."""
        wraps = self.query(".logo-wrap")
        if wraps:
            wraps.first().set_class(self.size.height < 22, "hidden")

    @on(UrlInput.Submitted)
    def _on_submit(self, event: UrlInput.Submitted) -> None:
        if self._probing or self._pushed:
            return
        try:
            url = clean_url(event.value)
        except ValueError as exc:
            self._show_error(str(exc))
            return

        self._probing = True
        self.query_one("#url", UrlInput).disabled = True
        self._show_probe_status(url)
        self._run_probe(url)

    @on(Button.Pressed)
    def _on_button(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id == "btn_playlist":
            self.action_playlist()
        elif button_id == "btn_queue":
            self.action_queue()
        elif button_id == "btn_library":
            self.action_library()

    def action_queue(self) -> None:
        state = getattr(self.app, "state", None)
        queue = state.queue if state is not None else DownloadQueue()
        self._pushed = True
        self.app.push_screen(QueueScreen(queue=queue))

    def action_library(self) -> None:
        store = getattr(self.app, "library", None)
        if store is None:
            store = LibraryStore()
        self._pushed = True
        self.app.push_screen(LibraryScreen(store=store))

    def action_playlist(self) -> None:
        if self._probing or self._pushed:
            return
        try:
            url = clean_url(self.query_one("#url", UrlInput).value)
        except ValueError as exc:
            self._show_error(str(exc))
            return
        self._probing = True
        self.query_one("#url", UrlInput).disabled = True
        self._show_probe_status(url)
        self._run_playlist_probe(url)

    def _show_probe_status(self, url: str) -> None:
        """Show compact inline probing status."""
        status = self.query_one("#probe-status", Static)
        status.remove_class("hidden")
        status.update(f"[dim]⟳ Probing[/dim] [cyan]{escape(url)}[/cyan] [dim]...[/dim]")
        self._animate_probe_spinner(status, url)

    def _animate_probe_spinner(self, status: Static, url: str) -> None:
        frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        i = 0

        def tick() -> None:
            nonlocal i
            if status.has_class("hidden"):
                return
            status.update(
                f"[dim]{frames[i % len(frames)]} Probing[/dim] [cyan]{escape(url)}[/cyan] [dim]...[/dim]"
            )
            i += 1

        if self._spinner_timer is not None:
            self._spinner_timer.stop()
        self._spinner_timer = self.set_interval(0.08, tick)

    def _show_error(self, message: str) -> None:
        """Show an inline, auto-hiding error instead of stacking modals."""
        if self._spinner_timer is not None:
            self._spinner_timer.stop()
            self._spinner_timer = None
        status = self.query_one("#probe-status", Static)
        status.update(f"[red]✗[/red] {escape(message)}")
        status.remove_class("hidden")
        self.set_timer(4.0, lambda: status.add_class("hidden"))

    def _hide_probe_status(self) -> None:
        if self._spinner_timer is not None:
            self._spinner_timer.stop()
            self._spinner_timer = None
        status = self.query_one("#probe-status", Static)
        status.update("")
        status.add_class("hidden")

    @work(thread=True, exclusive=True, name="probe")
    def _run_probe(self, url: str) -> None:
        config = getattr(self.app, "config", AppConfig())
        try:
            info = probe(
                url,
                extra_args=config.ytdlp_args,
                cancel_check=lambda: self._cancel_probe,
            )
            if self._cancel_probe:
                return
            self.app.call_from_thread(self._on_probed, info, None, url)
        except DownloadError as exc:
            if self._cancel_probe:
                return
            self.app.call_from_thread(self._on_probed, None, str(exc), url)
        except Exception as exc:  # pragma: no cover - defensive
            if self._cancel_probe:
                return
            self.app.call_from_thread(self._on_probed, None, str(exc), url)

    def _on_probed(self, info: MediaInfo | None, error: str | None, url: str) -> None:
        self._probing = False
        with contextlib.suppress(Exception):
            self.query_one("#url", UrlInput).disabled = False

        if error:
            self._show_error(error)
            return
        if info is None:
            self._show_error("Could not read that URL")
            return
        if self._pushed:
            self._hide_probe_status()
            return

        self._pushed = True
        if not info.webpage_url:
            info.webpage_url = url
        save_last_url(url)
        app_state = getattr(self.app, "state", None)
        if app_state is not None:
            app_state.last_url = url
            app_state.current_url = url
            app_state.current_info = info
        self._hide_probe_status()
        self.app.push_screen(FormatScreen(info))

    @work(thread=True, exclusive=True, name="playlist-probe")
    def _run_playlist_probe(self, url: str) -> None:
        config = getattr(self.app, "config", AppConfig())
        try:
            playlist = probe_playlist(
                url,
                extra_args=config.ytdlp_args,
                cancel_check=lambda: self._cancel_probe,
            )
            if self._cancel_probe:
                return
            self.app.call_from_thread(self._on_playlist_probed, playlist, None, url)
        except DownloadError as exc:
            if self._cancel_probe:
                return
            self.app.call_from_thread(self._on_playlist_probed, None, str(exc), url)
        except Exception as exc:  # pragma: no cover - defensive
            if self._cancel_probe:
                return
            self.app.call_from_thread(self._on_playlist_probed, None, str(exc), url)

    def _on_playlist_probed(
        self,
        playlist: PlaylistInfo | None,
        error: str | None,
        url: str,
    ) -> None:
        self._probing = False
        with contextlib.suppress(Exception):
            self.query_one("#url", UrlInput).disabled = False
        if error:
            self._show_error(error)
            return
        if playlist is None:
            self._show_error("Could not read that playlist")
            return
        if self._pushed:
            self._hide_probe_status()
            return
        self._pushed = True
        save_last_url(url)
        app_state = getattr(self.app, "state", None)
        if app_state is not None:
            app_state.last_url = url
            app_state.current_url = url
        self._hide_probe_status()
        self.app.push_screen(PlaylistScreen(playlist, url=url))


@dataclass(frozen=True, slots=True)
class ClipChoice:
    """Result of the clip dialog. ``section=None`` means the full video."""

    section: Section | None


class ClipModal(ModalScreen[ClipChoice]):
    """Dialog for choosing an optional start/end range."""

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, duration: float | None, current: Section | None = None) -> None:
        super().__init__()
        self.duration = duration
        self.current = current

    def compose(self) -> ComposeResult:
        start_value = format_timecode(self.current.start) if self.current else ""
        end_value = (
            format_timecode(self.current.end)
            if self.current and self.current.end is not None
            else ""
        )
        duration_text = (
            f"Video length: {human_time(self.duration)}"
            if self.duration
            else "Video length: unknown"
        )
        with Container(classes="dialog clip-dialog"):
            yield Static("✂ Download a clip", classes="title")
            yield Static(duration_text, classes="clip-hint")
            yield Static(
                "Use HH:MM:SS, MM:SS, seconds, or 1h2m3s. Leave end blank to go to the end.",
                classes="clip-hint",
            )
            with Horizontal(classes="clip-row"):
                with Vertical(classes="clip-field"):
                    yield Static("Start", classes="clip-label")
                    yield Input(value=start_value, placeholder="00:00:00", id="clip-start")
                with Vertical(classes="clip-field"):
                    yield Static("End", classes="clip-label")
                    yield Input(value=end_value, placeholder="00:05:00", id="clip-end")
            with Horizontal(classes="clip-presets"):
                yield Button("Full video", id="preset-full")
                yield Button("First 5m", id="preset-first")
                yield Button("Last 5m", id="preset-last", disabled=not self.duration)
            with Horizontal(classes="clip-precise"):
                yield Switch(
                    value=self.current.precise if self.current else True,
                    id="clip-precise",
                )
                yield Static(
                    "Precise cut (slower, re-encodes at the cut points)",
                    classes="clip-hint",
                )
            yield Static("", id="clip-error", classes="clip-error", markup=False)
            with Horizontal(classes="clip-actions"):
                yield Button("Cancel", id="clip-cancel")
                yield Button("Apply", variant="success", id="clip-apply")

    def on_mount(self) -> None:
        self.query_one("#clip-start", Input).focus()

    @on(Input.Changed)
    def _clear_error(self, _: Input.Changed) -> None:
        self.query_one("#clip-error", Static).update("")

    @on(Input.Submitted)
    def _on_submitted(self, event: Input.Submitted) -> None:
        end = self.query_one("#clip-end", Input)
        if event.input.id == "clip-start" and not end.value.strip():
            end.focus()
        else:
            self._apply()

    @on(Button.Pressed, "#preset-full")
    def _preset_full(self, _: Button.Pressed) -> None:
        self.dismiss(ClipChoice(None))

    @on(Button.Pressed, "#preset-first")
    def _preset_first(self, _: Button.Pressed) -> None:
        end = 300.0 if not self.duration else min(300.0, self.duration)
        self.query_one("#clip-start", Input).value = "00:00:00"
        self.query_one("#clip-end", Input).value = format_timecode(end)
        self.query_one("#clip-error", Static).update("")

    @on(Button.Pressed, "#preset-last")
    def _preset_last(self, _: Button.Pressed) -> None:
        if not self.duration:
            return
        start = max(0.0, self.duration - 300.0)
        self.query_one("#clip-start", Input).value = format_timecode(start)
        self.query_one("#clip-end", Input).value = format_timecode(self.duration)
        self.query_one("#clip-error", Static).update("")

    @on(Button.Pressed, "#clip-cancel")
    def _cancel(self, _: Button.Pressed) -> None:
        self.dismiss()

    @on(Button.Pressed, "#clip-apply")
    def _apply_pressed(self, _: Button.Pressed) -> None:
        self._apply()

    def _error(self, message: str) -> None:
        self.query_one("#clip-error", Static).update(message)

    def _apply(self) -> None:
        start_text = self.query_one("#clip-start", Input).value.strip()
        end_text = self.query_one("#clip-end", Input).value.strip()

        try:
            start = parse_timecode(start_text) if start_text else 0.0
            end = parse_timecode(end_text) if end_text else None
        except ValueError as exc:
            self._error(str(exc))
            return

        if end is not None and end <= start:
            self._error("End time must be after start time.")
            return
        if start == 0 and end is None:
            self.dismiss(ClipChoice(None))
            return
        if self.duration:
            if start >= self.duration:
                self._error(f"Start is past the end of the video ({human_time(self.duration)}).")
                return
            if end is not None and end > self.duration:
                self._error(f"Video is only {human_time(self.duration)} long.")
                return

        precise = self.query_one("#clip-precise", Switch).value
        self.dismiss(ClipChoice(Section(start=start, end=end, precise=precise)))

    def action_cancel(self) -> None:
        self.dismiss()


class PresetModal(ModalScreen[str | None]):
    """Choose a built-in or user-defined download preset."""

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        ("enter", "apply", "Apply"),
    ]

    def __init__(self, presets: dict[str, Preset]) -> None:
        super().__init__()
        self.presets = presets
        self._names = sorted(presets)
        self._selected = self._names[0] if self._names else ""

    def compose(self) -> ComposeResult:
        with Container(classes="dialog preset-dialog"):
            yield Static("⚡ Download preset", classes="title")
            yield Static(
                "Presets bundle mode, quality, container, and post-processing. "
                "You can still tweak the format after applying one.",
                classes="clip-hint",
            )
            table: DataTable[str] = DataTable(id="preset-table", cursor_type="row")
            yield table
            with Horizontal(classes="clip-actions"):
                yield Button("Cancel", id="preset-cancel")
                yield Button("Apply", variant="success", id="preset-apply")

    def on_mount(self) -> None:
        table = self.query_one("#preset-table", DataTable)
        table.add_columns("Name", "Mode", "Container", "Cap", "Description")
        for name in self._names:
            preset = self.presets[name]
            table.add_row(
                escape(name),
                preset.mode,
                preset.container,
                "best" if not preset.quality_cap else f"{preset.quality_cap}p",
                escape(preset.description),
                key=name,
            )
        if self._names:
            table.focus()
            table.move_cursor(row=0)

    @on(DataTable.RowSelected)
    def _on_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.row_key.value:
            self._selected = str(event.row_key.value)
            self.dismiss(self._selected)

    @on(Button.Pressed, "#preset-cancel")
    def _cancel_pressed(self, _: Button.Pressed) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#preset-apply")
    def _apply_pressed(self, _: Button.Pressed) -> None:
        self.action_apply()

    def action_apply(self) -> None:
        table = self.query_one("#preset-table", DataTable)
        if self._names and 0 <= table.cursor_row < len(self._names):
            self._selected = self._names[table.cursor_row]
        self.dismiss(self._selected or None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class ConfirmModal(ModalScreen[bool]):
    """Small confirmation dialog for destructive actions."""

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        ("n", "cancel", "Cancel"),
        ("y", "confirm", "Confirm"),
    ]

    def __init__(
        self,
        title: str,
        message: str,
        *,
        confirm_label: str = "Confirm",
        danger: bool = False,
    ) -> None:
        super().__init__()
        self._title = title
        self.message = message
        self.confirm_label = confirm_label
        self.danger = danger

    def compose(self) -> ComposeResult:
        with Container(classes="dialog"):
            yield Static(self._title, classes="title")
            yield Static(self.message, classes="message", markup=False)
            with Horizontal(classes="confirm-actions"):
                yield Button("Cancel", id="confirm-cancel")
                yield Button(
                    self.confirm_label,
                    variant="error" if self.danger else "primary",
                    id="confirm-ok",
                )

    @on(Button.Pressed, "#confirm-cancel")
    def _cancel_pressed(self, _: Button.Pressed) -> None:
        self.dismiss(False)

    @on(Button.Pressed, "#confirm-ok")
    def _confirm_pressed(self, _: Button.Pressed) -> None:
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)

    def action_confirm(self) -> None:
        self.dismiss(True)


class PlaylistScreen(Screen):
    """Preview a flat playlist, then enqueue every entry."""

    BINDINGS = [
        ("escape", "back", "Back"),
        ("v", "mode_video", "Video+Audio"),
        ("o", "mode_vonly", "Video Only"),
        ("a", "mode_audio", "Audio Only"),
    ]

    _MODE_LABELS = {
        "video": "Video+Audio",
        "vonly": "Video Only",
        "audio": "Audio Only",
    }
    _QUALITY_STEPS = (2160, 1440, 1080, 720, 480, 360, 240)

    def __init__(self, playlist: PlaylistInfo, url: str = "") -> None:
        super().__init__()
        self.playlist = playlist
        self.url = url
        self._mode = "video"
        self._quality_cap = 1080
        self._queued = False

    @classmethod
    def _quality_options(cls, cap: int) -> list[tuple[str, int]]:
        steps = list(cls._QUALITY_STEPS)
        if cap and cap not in steps:
            steps.append(cap)
        options: list[tuple[str, int]] = [("Best available", 0)]
        options.extend((f"{value}p", value) for value in sorted(steps, reverse=True))
        return options

    def compose(self) -> ComposeResult:
        config = getattr(self.app, "config", AppConfig())
        self._quality_cap = config.quality_cap
        yield Header(show_clock=True)
        with Container(classes="page playlist-page"):
            yield Static("PLAYLIST", classes="page-kicker")
            yield Static(escape(self.playlist.title), classes="page-title")
            yield Static("", id="playlist-summary", classes="page-subtitle")
            yield SelectableTable(id="playlist-table", cursor_type="row")
            with Horizontal(classes="playlist-controls"):
                yield Static("Mode", classes="control-label")
                yield Button(
                    "▶ Video+Audio",
                    variant="success",
                    id="playlist-mode-video",
                )
                yield Button("📹 Video", id="playlist-mode-vonly")
                yield Button("🎵 Audio", id="playlist-mode-audio")
                yield Static("Quality", classes="control-label")
                yield Select(
                    self._quality_options(self._quality_cap),
                    value=self._quality_cap,
                    allow_blank=False,
                    id="playlist-quality",
                )
            with Horizontal(classes="selection-actions"):
                yield Static("Selection", classes="control-label")
                yield Button("Select all", id="playlist-select-all")
                yield Button("Clear selection", id="playlist-select-none")
            with Horizontal(classes="page-actions"):
                yield Button("← Back", id="playlist-back")
                yield Button(
                    "＋ Queue selected",
                    id="playlist-queue-selected",
                    disabled=True,
                )
                yield Button(
                    f"＋ Queue all ({len(self.playlist.entries)})",
                    variant="primary",
                    id="playlist-queue",
                )
        yield Footer()

    def on_mount(self) -> None:
        config = getattr(self.app, "config", AppConfig())
        if config.default_mode in self._MODE_LABELS:
            self._mode = config.default_mode

        table = self.query_one("#playlist-table", SelectableTable)
        table.add_column("Sel", width=3)
        table.add_columns("#", "Title", "Duration", "Channel")
        for index, entry in enumerate(self.playlist.entries, start=1):
            table.add_selectable_row(
                str(index),
                escape(entry.title),
                human_time(entry.duration),
                escape(entry.uploader or "—"),
                key=str(index),
            )
        table.focus()
        self._update_mode_buttons()
        self._update_quality_control()
        self._update_summary()
        self._update_action_buttons()

    def _update_mode_buttons(self) -> None:
        for button_id, mode in (
            ("playlist-mode-video", "video"),
            ("playlist-mode-vonly", "vonly"),
            ("playlist-mode-audio", "audio"),
        ):
            button = self.query_one(f"#{button_id}", Button)
            button.variant = "success" if self._mode == mode else "default"
            button.refresh()

    def _update_quality_control(self) -> None:
        quality = self.query_one("#playlist-quality", Select)
        quality.disabled = self._mode == "audio"

    def _quality_label(self) -> str:
        return "best available" if not self._quality_cap else f"≤{self._quality_cap}p"

    def _selected_entries(self) -> list[PlaylistEntry]:
        table = self.query_one("#playlist-table", SelectableTable)
        entries: list[PlaylistEntry] = []
        for key in table.selected_keys():
            try:
                index = int(key) - 1
            except ValueError:
                continue
            if 0 <= index < len(self.playlist.entries):
                entries.append(self.playlist.entries[index])
        return entries

    def _update_summary(self) -> None:
        label = self._MODE_LABELS[self._mode]
        detail = "audio extraction" if self._mode == "audio" else f"quality {self._quality_label()}"
        summary = f"{len(self.playlist.entries)} entries • {label} • {detail}"
        selected = self.query_one("#playlist-table", SelectableTable).selected_count
        if selected:
            summary += f" • {selected} selected"
        self.query_one("#playlist-summary", Static).update(summary)

    def _update_action_buttons(self) -> None:
        table = self.query_one("#playlist-table", SelectableTable)
        selected = table.selected_count
        queue_selected = self.query_one("#playlist-queue-selected", Button)
        queue_selected.label = (
            f"＋ Queue selected ({selected})" if selected else "＋ Queue selected"
        )
        queue_selected.disabled = self._queued or selected == 0
        self.query_one("#playlist-queue", Button).disabled = self._queued
        select_all = self.query_one("#playlist-select-all", Button)
        select_all.disabled = (
            self._queued or not self.playlist.entries or selected == len(self.playlist.entries)
        )
        self.query_one("#playlist-select-none", Button).disabled = self._queued or selected == 0

    def _set_mode(self, mode: str) -> None:
        self._mode = mode
        self._update_mode_buttons()
        self._update_quality_control()
        self._update_summary()

    @on(Select.Changed, "#playlist-quality")
    def _quality_changed(self, event: Select.Changed) -> None:
        if isinstance(event.value, int):
            self._quality_cap = event.value
            self._update_summary()

    @on(SelectableTable.SelectionChanged)
    def _selection_changed(self, _: SelectableTable.SelectionChanged) -> None:
        self._update_summary()
        self._update_action_buttons()

    @on(Button.Pressed, "#playlist-back")
    def _back_pressed(self, _: Button.Pressed) -> None:
        self.action_back()

    @on(Button.Pressed, "#playlist-select-all")
    def _select_all_pressed(self, _: Button.Pressed) -> None:
        self.query_one("#playlist-table", SelectableTable).select_all()

    @on(Button.Pressed, "#playlist-select-none")
    def _select_none_pressed(self, _: Button.Pressed) -> None:
        self.query_one("#playlist-table", SelectableTable).clear_selection()

    @on(Button.Pressed)
    def _mode_pressed(self, event: Button.Pressed) -> None:
        mode = {
            "playlist-mode-video": "video",
            "playlist-mode-vonly": "vonly",
            "playlist-mode-audio": "audio",
        }.get(event.button.id or "")
        if mode is not None:
            self._set_mode(mode)

    @on(Button.Pressed, "#playlist-queue-selected")
    def _queue_selected_pressed(self, _: Button.Pressed) -> None:
        self.action_queue_selected()

    @on(Button.Pressed, "#playlist-queue")
    def _queue_pressed(self, _: Button.Pressed) -> None:
        self.action_queue_all()

    def action_mode_video(self) -> None:
        self._set_mode("video")

    def action_mode_vonly(self) -> None:
        self._set_mode("vonly")

    def action_mode_audio(self) -> None:
        self._set_mode("audio")

    def action_queue_selected(self) -> None:
        if self._queued:
            return
        entries = self._selected_entries()
        if not entries:
            self.notify("Select at least one playlist entry first.", severity="warning")
            return
        self._queue_entries(entries)

    def action_queue_all(self) -> None:
        self._queue_entries(self.playlist.entries)

    def _queue_entries(self, entries: list[PlaylistEntry]) -> None:
        if self._queued:
            return
        config = getattr(self.app, "config", AppConfig())
        policy = replace(
            DownloadPolicy.from_config(config),
            mode=self._mode,
            quality_cap=self._quality_cap,
        )
        state = getattr(self.app, "state", None)
        queue = state.queue if state is not None else DownloadQueue()
        for entry in entries:
            queue.add(QueueItem.from_entry(entry, policy))
        store = getattr(self.app, "queue_store", None)
        if store is not None:
            store.save(queue)
        self._queued = True
        self.app.switch_screen(QueueScreen(queue=queue))

    def action_back(self) -> None:
        self.app.pop_screen()


class QueueScreen(Screen):
    """Review, resume, and start the persistent download queue."""

    BINDINGS = [("escape", "back", "Back")]

    def __init__(self, queue: DownloadQueue | None = None) -> None:
        super().__init__()
        self.queue = queue or DownloadQueue()
        self._started = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Container(classes="page queue-page"):
            yield Static("DOWNLOAD QUEUE", classes="page-kicker")
            yield Static("Power-user queue", classes="page-title")
            yield Static("", id="queue-summary", classes="page-subtitle")
            yield SelectableTable(id="queue-table", cursor_type="row")
            with Horizontal(classes="selection-actions"):
                yield Static("Selection", classes="control-label")
                yield Button("Select all", id="queue-select-all")
                yield Button("Clear selection", id="queue-select-none")
            with Horizontal(classes="page-actions"):
                yield Button("← Add URL", id="queue-add")
                yield Button("Remove selected", id="queue-remove")
                yield Button("Clear finished", id="queue-clear")
                yield Button("Remove all", variant="error", id="queue-remove-all")
                yield Button("Start queue", variant="warning", id="queue-start")
        yield Footer()

    def on_mount(self) -> None:
        state = getattr(self.app, "state", None)
        if state is not None:
            state.queue = self.queue
        self._refresh()

    def on_screen_resume(self) -> None:
        self._started = False
        self._refresh()

    def _refresh(self) -> None:
        table = self.query_one("#queue-table", SelectableTable)
        table.clear(columns=True)
        # Explicit widths keep the table readable at the 100-column minimum;
        # DataTable's content-width cache otherwise renders the first frame
        # with header-only widths.
        table.add_column("Sel", width=3)
        table.add_column("#", width=3)
        table.add_column("Title", width=28)
        table.add_column("Mode", width=7)
        table.add_column("Status", width=14)
        table.add_column("URL", width=28)
        for index, item in enumerate(self.queue.items, start=1):
            table.add_selectable_row(
                str(index),
                escape(item.display_title),
                escape(item.mode),
                self._status_text(item.status),
                escape(item.url),
                key=str(index),
            )
        table.focus()
        self._update_summary()
        self._update_action_buttons()

    def _update_summary(self) -> None:
        table = self.query_one("#queue-table", SelectableTable)
        resumable = self.queue.resumable()
        interrupted = sum(1 for item in self.queue.items if item.status == "interrupted")
        summary = f"{len(self.queue.items)} total • {len(resumable)} ready" + (
            f" • {interrupted} interrupted" if interrupted else ""
        )
        if table.selected_count:
            summary += f" • {table.selected_count} selected"
        self.query_one("#queue-summary", Static).update(summary)

    def _items_for_keys(self, keys: list[str]) -> list[QueueItem]:
        items: list[QueueItem] = []
        for key in keys:
            try:
                index = int(key) - 1
            except ValueError:
                continue
            if 0 <= index < len(self.queue.items):
                items.append(self.queue.items[index])
        return items

    def _selected_queue_items(self) -> list[QueueItem]:
        """Return explicitly selected rows, or the cursor row when none are selected."""
        table = self.query_one("#queue-table", SelectableTable)
        if table.selected_count:
            return self._items_for_keys(table.selected_keys())
        if 0 <= table.cursor_row < len(self.queue.items):
            return [self.queue.items[table.cursor_row]]
        return []

    def _update_action_buttons(self) -> None:
        table = self.query_one("#queue-table", SelectableTable)
        selected_keys = table.selected_keys()
        selected_items = (
            self._items_for_keys(selected_keys) if selected_keys else self._selected_queue_items()
        )
        selected_resumable = [item for item in selected_items if item.resumable]
        interrupted = sum(1 for item in self.queue.items if item.status == "interrupted")
        start = self.query_one("#queue-start", Button)
        if selected_keys:
            start.label = f"Start selected ({len(selected_resumable)})"
            start.disabled = not selected_resumable
        else:
            start.label = "Resume queue" if interrupted else "Start queue"
            start.disabled = not self.queue.resumable()

        remove = self.query_one("#queue-remove", Button)
        remove.label = (
            f"Remove selected ({len(selected_items)})" if selected_keys else "Remove selected"
        )
        remove.disabled = not selected_items
        self.query_one("#queue-remove-all", Button).disabled = not self.queue.items
        self.query_one("#queue-clear", Button).disabled = not any(
            not item.resumable for item in self.queue.items
        )
        select_all = self.query_one("#queue-select-all", Button)
        select_all.disabled = not self.queue.items or table.selected_count == len(self.queue.items)
        self.query_one("#queue-select-none", Button).disabled = table.selected_count == 0

    @staticmethod
    def _status_text(status: str) -> str:
        return {
            "pending": "· Queued",
            "running": "↓ Running",
            "done": "✓ Done",
            "failed": "✗ Failed",
            "cancelled": "× Cancelled",
            "interrupted": "⏸ Interrupted",
        }.get(status, status)

    def _save(self) -> None:
        store = getattr(self.app, "queue_store", None)
        if store is not None:
            store.save(self.queue)

    @on(Button.Pressed, "#queue-add")
    def _add_pressed(self, _: Button.Pressed) -> None:
        self.app.pop_screen()

    @on(Button.Pressed, "#queue-clear")
    def _clear_pressed(self, _: Button.Pressed) -> None:
        self.queue.clear_finished()
        self._save()
        self._refresh()

    @on(Button.Pressed, "#queue-select-all")
    def _select_all_pressed(self, _: Button.Pressed) -> None:
        self.query_one("#queue-table", SelectableTable).select_all()

    @on(Button.Pressed, "#queue-select-none")
    def _select_none_pressed(self, _: Button.Pressed) -> None:
        self.query_one("#queue-table", SelectableTable).clear_selection()

    @on(SelectableTable.SelectionChanged)
    def _selection_changed(self, _: SelectableTable.SelectionChanged) -> None:
        self._update_summary()
        self._update_action_buttons()

    @on(Button.Pressed, "#queue-remove")
    def _remove_pressed(self, _: Button.Pressed) -> None:
        items = self._selected_queue_items()
        if not items:
            return
        if any(item.status == "running" for item in items):
            self.notify("Stop the active download before removing it.", severity="warning")
            return
        for item in items:
            self.queue.items.remove(item)
        self._save()
        self._refresh()

    @on(Button.Pressed, "#queue-remove-all")
    def _remove_all_pressed(self, _: Button.Pressed) -> None:
        if not self.queue.items:
            return
        if any(item.status == "running" for item in self.queue.items):
            self.notify("Stop the active download before removing all items.", severity="warning")
            return
        self.app.push_screen(
            ConfirmModal(
                "Remove all queue items?",
                f"Remove {len(self.queue.items)} item(s) from the queue?\n\nThis cannot be undone.",
                confirm_label="Remove all",
                danger=True,
            ),
            callback=self._remove_all_result,
        )

    def _remove_all_result(self, confirmed: bool | None) -> None:
        if not confirmed:
            return
        if any(item.status == "running" for item in self.queue.items):
            self.notify("Stop the active download before removing all items.", severity="warning")
            return
        removed = self.queue.clear_all()
        self._save()
        self._refresh()
        self.notify(f"Removed {removed} queue item(s).")

    @on(Button.Pressed, "#queue-start")
    def _start_pressed(self, _: Button.Pressed) -> None:
        self.action_start()

    def action_start(self) -> None:
        if self._started:
            return
        table = self.query_one("#queue-table", SelectableTable)
        if table.selected_count:
            items = [item for item in self._items_for_keys(table.selected_keys()) if item.resumable]
            if not items:
                self.notify(
                    "Select at least one queue item that can be started.",
                    severity="warning",
                )
                return
        else:
            items = self.queue.resumable()
        if not items:
            return
        for item in items:
            item.status = "pending"
            item.error = ""
        self._save()
        self._started = True
        self.app.push_screen(
            DownloadScreen(
                items=items,
                queue_store=getattr(self.app, "queue_store", None),
                library=getattr(self.app, "library", None),
            )
        )

    def action_back(self) -> None:
        self.app.pop_screen()


class LibraryScreen(Screen):
    """Browse download history and reopen files or URLs."""

    BINDINGS = [("escape", "back", "Back")]

    def __init__(self, store: LibraryStore | None = None) -> None:
        super().__init__()
        self.store = store or LibraryStore()
        self._records: list[HistoryRecord] = []

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Container(classes="page library-page"):
            yield Static("LIBRARY", classes="page-kicker")
            yield Static("Download history", classes="page-title")
            yield Input(placeholder="Search title, channel, or URL…", id="library-search")
            yield DataTable(id="library-table", cursor_type="row")
            yield Static("", id="library-detail", classes="library-detail")
            with Horizontal(classes="page-actions"):
                yield Button("← Back", id="library-back")
                yield Button("Open file", id="library-open")
                yield Button("Open folder", id="library-folder")
                yield Button("Copy URL", id="library-copy")
                yield Button("Re-download", id="library-redownload")
                yield Button("Delete", variant="error", id="library-delete")
        yield Footer()

    def on_mount(self) -> None:
        self._refresh()

    def _refresh(self) -> None:
        query = self.query_one("#library-search", Input).value
        self._records = self.store.list_records(query)
        table = self.query_one("#library-table", DataTable)
        table.clear(columns=True)
        # Explicit widths keep the 100-column layout free of a horizontal
        # scrollbar; the detail pane shows the full path for truncated cells.
        table.add_column("Title", width=23)
        table.add_column("Status", width=13)
        table.add_column("Size", width=8)
        table.add_column("Started", width=10)
        table.add_column("Path", width=24)
        for record in self._records:
            table.add_row(
                escape(record.display_title),
                self._status_text(record.status),
                human_size(record.size) if record.size else "—",
                record.started_at[:10] or "—",
                escape(record.path or record.url),
                key=str(record.id),
            )
        if self._records:
            table.move_cursor(row=0)
            self._show_detail(self._records[0])
        else:
            self.query_one("#library-detail", Static).update(
                "[dim]No downloads yet. Your completed and interrupted downloads appear here.[/dim]"
            )

    @staticmethod
    def _status_text(status: str) -> str:
        return {
            "running": "↓ Running",
            "done": "✓ Done",
            "failed": "✗ Failed",
            "cancelled": "× Cancelled",
            "interrupted": "⏸ Interrupted",
        }.get(status, status)

    def _selected(self) -> HistoryRecord | None:
        table = self.query_one("#library-table", DataTable)
        if 0 <= table.cursor_row < len(self._records):
            return self._records[table.cursor_row]
        return None

    def _show_detail(self, record: HistoryRecord) -> None:
        details = [f"[bold]{escape(record.display_title)}[/bold]"]
        details.append(f"[dim]{escape(record.url)}[/dim]")
        if record.path:
            details.append(f"Path: {escape(record.path)}")
            if not Path(record.path).exists():
                details.append("[yellow]File is missing on disk[/yellow]")
        if record.error_reason:
            details.append(f"[red]{escape(record.error_reason)}[/red]")
        if record.section:
            details.append(f"Clip: {record.section}")
        self.query_one("#library-detail", Static).update("\n".join(details))

    @on(Input.Changed, "#library-search")
    def _search_changed(self, _: Input.Changed) -> None:
        self._refresh()

    @on(DataTable.RowHighlighted)
    @on(DataTable.RowSelected)
    def _row_selected(self, event: DataTable.RowSelected) -> None:
        if event.row_key.value is None:
            return
        record_id = int(event.row_key.value)
        record = next((r for r in self._records if r.id == record_id), None)
        if record is not None:
            self._show_detail(record)

    @on(Button.Pressed, "#library-back")
    def _back_pressed(self, _: Button.Pressed) -> None:
        self.action_back()

    @on(Button.Pressed, "#library-open")
    def _open_pressed(self, _: Button.Pressed) -> None:
        record = self._selected()
        if record is None or not record.path:
            self.notify("No saved file for this record.", severity="warning")
            return
        if not Path(record.path).exists():
            self.notify("That file is missing on disk.", severity="warning")
            return
        self._open_path(Path(record.path))

    @on(Button.Pressed, "#library-folder")
    def _folder_pressed(self, _: Button.Pressed) -> None:
        record = self._selected()
        if record is None or not record.path:
            self.notify("No saved file for this record.", severity="warning")
            return
        folder = Path(record.path).parent
        if not folder.exists():
            self.notify("That folder is missing on disk.", severity="warning")
            return
        self._open_path(folder)

    @on(Button.Pressed, "#library-copy")
    def _copy_pressed(self, _: Button.Pressed) -> None:
        record = self._selected()
        if record is None:
            return
        copy = getattr(self.app, "copy_to_clipboard", None)
        if callable(copy):
            copy(record.url)
            self.notify("URL copied to clipboard.")
        else:
            self.notify(record.url, timeout=10, markup=False)

    @on(Button.Pressed, "#library-redownload")
    def _redownload_pressed(self, _: Button.Pressed) -> None:
        record = self._selected()
        if record is None:
            return
        state = getattr(self.app, "state", None)
        if state is not None:
            state.last_url = record.url
        self.app.pop_screen()

    @on(Button.Pressed, "#library-delete")
    def _delete_pressed(self, _: Button.Pressed) -> None:
        record = self._selected()
        if record is None:
            return
        self.store.delete(record.id)
        self._refresh()

    @staticmethod
    def _open_path(path: Path) -> None:
        if sys.platform == "darwin":
            cmd = ["open", str(path)]
        elif sys.platform.startswith("win"):
            with contextlib.suppress(Exception):
                import os

                os.startfile(str(path))  # type: ignore[attr-defined]
            return
        else:
            cmd = ["xdg-open", str(path)]
        with contextlib.suppress(OSError):
            subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )

    def action_back(self) -> None:
        self.app.pop_screen()


class FormatScreen(Screen):
    """Format selection + thumbnail + metadata."""

    BINDINGS = [
        ("d", "download", "Download"),
        ("c", "clip", "Clip range"),
        ("C", "clip", "Clip range"),
        ("v", "mode_video", "Video+Audio"),
        ("o", "mode_vonly", "Video Only"),
        ("a", "mode_audio", "Audio Only"),
        ("p", "preset", "Preset"),
        ("q", "queue", "Add to queue"),
        ("escape", "back", "Back"),
        ("ctrl+c", "quit", "Quit"),
    ]

    def __init__(self, info: MediaInfo) -> None:
        super().__init__()
        self.info = info
        self._selected_format: FormatInfo | None = None
        self._mode: str = "video"  # video | audio | vonly
        self._section: Section | None = None
        self._download_started = False
        self._preset: Preset | None = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Container(classes="top-row"):
            with Vertical(classes="left-pane"):
                yield FormatTable(id="table")
            with Vertical(classes="right-pane"):
                yield ThumbnailCard(id="thumb")
                yield InfoPanel(id="info")
        with Horizontal(classes="ActionBar"):
            yield Button("▶ Video+Audio", variant="success", id="btn_video")
            yield Button("📹 Video", variant="default", id="btn_vonly")
            yield Button("🎵 Audio", variant="default", id="btn_audio")
            yield Button("✂ Clip: Full", variant="default", id="btn_clip")
            yield Button("Preset", variant="default", id="btn_preset")
            yield Static("", classes="action-spacer")
            yield Button("＋ Queue", variant="primary", id="btn_queue")
            yield Button("⬇ Download", variant="warning", id="btn_download")
        yield StatusToast(id="toast")
        yield Footer()

    def on_mount(self) -> None:
        config = getattr(self.app, "config", AppConfig())
        if config.default_mode in ("video", "vonly", "audio"):
            self._mode = config.default_mode
        if not config.show_preview:
            with contextlib.suppress(Exception):
                self.query_one("#thumb", ThumbnailCard).display = False

        table = self.query_one("#table", FormatTable)
        table.load(self.info.video_formats, self.info.audio_formats)

        thumb = self.query_one("#thumb", ThumbnailCard)
        thumb.image_url = self.info.thumbnail_url

        info_panel = self.query_one("#info", InfoPanel)
        info_panel.load(self.info)

        # Pre-select first format by default if available
        if self.info.video_formats:
            self._selected_format = self.info.video_formats[0]
        elif self.info.audio_formats:
            self._selected_format = self.info.audio_formats[0]
            self._mode = "audio"

        self._update_mode_buttons()
        self._update_preset_button()

        toast = self.query_one("#toast", StatusToast)
        if self._selected_format:
            toast.info(
                f"Default: {self._selected_format.label} • 'd' or Enter to download "
                "• 'c' for a clip"
            )

    @on(FormatTable.FormatSelected)
    def _on_format_selected(self, event: FormatTable.FormatSelected) -> None:
        if self._selected_format == event.fmt:
            # Selected the same format again -> start download immediately
            self._start_download()
            return

        self._selected_format = event.fmt
        if event.fmt.has_audio and not event.fmt.has_video:
            self._mode = "audio"
        elif self._mode == "audio":
            self._mode = "video"

        # Visually highlight the chosen row in the table
        table = self.query_one("#table", FormatTable)
        cursor_row = getattr(event, "cursor_row", table.cursor_row)
        table.set_selected(cursor_row)

        self._update_mode_buttons()

        toast = self.query_one("#toast", StatusToast)
        toast.success(f"Selected: {event.fmt.label} • Press 'd' or Enter again to Download")

    @on(Button.Pressed)
    def _on_button(self, event: Button.Pressed) -> None:
        btn_id = event.button.id
        if btn_id == "btn_video":
            self._mode = "video"
        elif btn_id == "btn_vonly":
            self._mode = "vonly"
        elif btn_id == "btn_audio":
            self._mode = "audio"
        elif btn_id == "btn_clip":
            self.action_clip()
            return
        elif btn_id == "btn_preset":
            self.action_preset()
            return
        elif btn_id == "btn_queue":
            self.action_queue()
            return
        elif btn_id == "btn_download":
            self._start_download()
            return
        self._update_mode_buttons()

    def action_download(self) -> None:
        self._start_download()

    def action_clip(self) -> None:
        self.app.push_screen(
            ClipModal(duration=self.info.duration, current=self._section),
            callback=self._on_clip_result,
        )

    def action_preset(self) -> None:
        config = getattr(self.app, "config", AppConfig())
        self.app.push_screen(
            PresetModal(config.presets),
            callback=self._on_preset_result,
        )

    def _on_preset_result(self, name: str | None) -> None:
        if not name:
            return
        config = getattr(self.app, "config", AppConfig())
        preset = config.presets.get(name)
        if preset is None:
            return
        self._preset = preset
        self._mode = preset.mode
        self._update_mode_buttons()
        self._update_preset_button()
        self.query_one("#toast", StatusToast).success(
            f"Preset: {preset.name} • {preset.description or preset.mode}"
        )

    def _update_preset_button(self) -> None:
        button = self.query_one("#btn_preset", Button)
        button.label = f"Preset: {escape(self._preset.name)}" if self._preset else "Preset"
        button.variant = "primary" if self._preset else "default"
        button.refresh()

    def _policy(self) -> DownloadPolicy:
        config = getattr(self.app, "config", AppConfig())
        policy = DownloadPolicy.from_config(config, self._preset)
        if policy.mode != self._mode:
            policy = replace(policy, mode=self._mode)
        return policy

    def _active_format(self) -> FormatInfo | None:
        """Return the row under the cursor, falling back to the confirmed format.

        A single click or arrow key only moves the table cursor; it does not
        emit ``RowSelected``. Queue/download actions should still honor the
        format the user is looking at instead of silently using the initial
        default.
        """
        table = self.query_one("#table", FormatTable)
        return table.format_at(table.cursor_row) or self._selected_format

    def _build_item(self) -> QueueItem:
        return QueueItem.from_media(
            self.info,
            self._policy(),
            selected_format=self._active_format(),
            section=self._section,
            expected_bytes=self._estimated_section_bytes(),
        )

    def action_queue(self) -> None:
        item = self._build_item()
        if not item.url:
            self.query_one("#toast", StatusToast).error("No URL to queue.")
            return
        state = getattr(self.app, "state", None)
        if state is None:
            self.query_one("#toast", StatusToast).error("Queue is unavailable.")
            return
        state.queue.add(item)
        store = getattr(self.app, "queue_store", None)
        if store is not None:
            store.save(state.queue)
        self.query_one("#toast", StatusToast).success(
            f"Queued: {item.display_title} ({len(state.queue.resumable())} waiting)"
        )

    def _on_clip_result(self, choice: ClipChoice | None) -> None:
        if choice is None:
            return
        self._section = choice.section
        self._update_clip_button()
        toast = self.query_one("#toast", StatusToast)
        if self._section is None:
            toast.info("Clip: full video")
        else:
            end = format_timecode(self._section.end) if self._section.end is not None else "end"
            toast.success(f"Clip: {format_timecode(self._section.start)} → {end}")

    def _update_clip_button(self) -> None:
        button = self.query_one("#btn_clip", Button)
        if self._section is None:
            button.label = "✂ Clip: Full"
            button.variant = "default"
        else:
            end = format_timecode(self._section.end) if self._section.end is not None else "end"
            button.label = f"✂ {format_timecode(self._section.start)}–{end}"
            button.variant = "primary"
        button.refresh()

    def action_mode_video(self) -> None:
        self._mode = "video"
        self._update_mode_buttons()
        toast = self.query_one("#toast", StatusToast)
        toast.info("Mode: Video + Audio")

    def action_mode_vonly(self) -> None:
        self._mode = "vonly"
        self._update_mode_buttons()
        toast = self.query_one("#toast", StatusToast)
        toast.info("Mode: Video Only")

    def action_mode_audio(self) -> None:
        self._mode = "audio"
        self._update_mode_buttons()
        toast = self.query_one("#toast", StatusToast)
        toast.info("Mode: Audio Only")

    def _update_mode_buttons(self) -> None:
        """Highlight the active mode button."""
        for btn_id, mode in [
            ("btn_video", "video"),
            ("btn_vonly", "vonly"),
            ("btn_audio", "audio"),
        ]:
            btn = self.query_one(f"#{btn_id}", Button)
            btn.variant = "success" if self._mode == mode else "default"
            btn.refresh()

    @staticmethod
    def _format_full_size(fmt: FormatInfo | None, duration: float | None) -> float | None:
        if fmt is None:
            return None
        if fmt.size:
            return fmt.size
        rate = fmt.tbr or fmt.vbr or fmt.abr
        if rate and duration:
            return rate * 1000 / 8 * duration
        return None

    def _estimated_section_bytes(self) -> float | None:
        """Rough output size for a section; used only for the dashboard ETA."""
        section = self._section
        duration = self.info.duration
        if section is None or not duration or duration <= 0:
            return None
        end = section.end if section.end is not None else duration
        length = max(0.0, min(end, duration) - max(0.0, section.start))
        if length <= 0:
            return None
        fraction = length / duration

        active = self._active_format()
        if self._mode == "audio":
            fmt = active
            if fmt is None or fmt.has_video or not fmt.has_audio:
                fmt = self.info.audio_formats[0] if self.info.audio_formats else None
            full = self._format_full_size(fmt, duration)
            return full * fraction if full else None

        if self._mode == "vonly":
            fmt = active if active and active.has_video else None
            full = self._format_full_size(fmt, duration)
            return full * fraction if full else None

        fmt = active if active and active.has_video else None
        if fmt is None:
            cap = self._policy().quality_cap or None
            fmt = next(
                (f for f in self.info.video_formats if cap is None or (f.height or 0) <= cap),
                self.info.video_formats[0] if self.info.video_formats else None,
            )
        video_full = self._format_full_size(fmt, duration)
        if not video_full:
            return None

        audio_full = 0.0
        if fmt is not None and not fmt.has_audio:
            audio = self.info.audio_formats[0] if self.info.audio_formats else None
            audio_full = self._format_full_size(audio, duration) or 0.0
        return (video_full + audio_full) * fraction

    def _start_download(self) -> None:
        if self._download_started:
            return
        policy = self._policy()
        try:
            policy.download_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self.query_one("#toast", StatusToast).error(f"Cannot create download directory: {exc}")
            return
        item = self._build_item()
        if not item.url:
            self.query_one("#toast", StatusToast).error("No URL to download.")
            return

        app_state = getattr(self.app, "state", None)
        if app_state is not None:
            app_state.current_info = self.info
            app_state.selected_format = self._active_format()
            app_state.mode = self._mode

        self._download_started = True
        self.app.push_screen(
            DownloadScreen(
                items=[item],
                queue_store=getattr(self.app, "queue_store", None),
                library=getattr(self.app, "library", None),
            )
        )

    def on_screen_resume(self) -> None:
        """Allow another download when the dashboard pops back."""
        self._download_started = False

    def action_back(self) -> None:
        self.app.pop_screen()

    def action_quit(self) -> None:
        self.app.exit()


class DownloadScreen(Screen):
    """Steam-style download manager: queue, live stats, and activity log."""

    BINDINGS = [
        ("p", "toggle_pause", "Pause/Resume"),
        ("space", "toggle_pause", "Pause/Resume"),
        ("escape", "cancel", "Cancel"),
        ("ctrl+c", "cancel", "Cancel"),
    ]

    def __init__(
        self,
        *,
        url: str = "",
        selector: str = "bv*+ba/b",
        out_template: str = "",
        extract_audio: bool = False,
        title: str = "",
        extra_args: list[str] | None = None,
        section: Section | None = None,
        expected_bytes: float | None = None,
        merge_format: str = "mkv",
        audio_format: str = "mp3",
        audio_quality: str = "0",
        concurrent_fragments: int = 0,
        rate_limit: str = "",
        write_subtitles: bool = False,
        embed_metadata: bool = False,
        embed_thumbnail: bool = False,
        keep_original: bool = False,
        items: list[QueueItem] | None = None,
        queue_store: QueueStore | None = None,
        library: LibraryStore | None = None,
    ) -> None:
        super().__init__()
        if items:
            self.items = list(items)
        else:
            self.items = [
                QueueItem(
                    url=url,
                    title=title,
                    selector=selector,
                    out_template=out_template,
                    extract_audio=extract_audio,
                    section=section,
                    expected_bytes=expected_bytes,
                    merge_format=merge_format,
                    audio_format=audio_format,
                    audio_quality=audio_quality,
                    concurrent_fragments=concurrent_fragments,
                    rate_limit=rate_limit,
                    write_subtitles=write_subtitles,
                    embed_metadata=embed_metadata,
                    embed_thumbnail=embed_thumbnail,
                    keep_original=keep_original,
                    extra_args=list(extra_args or []),
                )
            ]
        self._queue_store = queue_store
        self._library = library
        self._control = DownloadControl()
        self._cancelled = False
        self._paused = False
        self._finished = False
        # Don't call this `_closed`: MessagePump uses that attribute internally,
        # and shadowing it makes Textual drop the screen's Prune message on pop.
        self._dismissed = False
        # 0-indexed current download pass (video then audio for merged files).
        self._dl_pass = 0
        self._logged_pass: int | None = None
        self._pp_logged = False
        self._started = time.monotonic()
        self._elapsed_base = 0.0
        self._paused_at: float | None = None
        self._current_index = 0
        self._completed = 0
        self._failed = 0
        self._apply_item_attrs(0)

    # -- item helpers -----------------------------------------------------

    def _apply_item_attrs(self, index: int) -> None:
        item = self.items[index]
        self._current_index = index
        self.url = item.url
        self.selector = item.selector
        self.out_template = item.out_template
        self.extract_audio = item.extract_audio
        self.title = item.title
        self.extra_args = list(item.extra_args)
        self.section = item.section
        self.expected_bytes = item.expected_bytes
        self.merge_format = item.merge_format
        self.audio_format = item.audio_format
        self.audio_quality = item.audio_quality
        self.concurrent_fragments = item.concurrent_fragments
        self.rate_limit = item.rate_limit
        self.write_subtitles = item.write_subtitles
        self.embed_metadata = item.embed_metadata
        self.embed_thumbnail = item.embed_thumbnail
        self.keep_original = item.keep_original
        if item.section is None:
            self._clip_label = ""
        else:
            end = format_timecode(item.section.end) if item.section.end is not None else "end"
            self._clip_label = f"{format_timecode(item.section.start)} → {end}"

    @property
    def _is_multi(self) -> bool:
        return len(self.items) > 1

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Container(classes="download-manager"):
            yield DownloadDashboard(
                title=self.title or "video",
                extract_audio=self.extract_audio,
                disk_free=self._disk_free(),
                single_pass=self.section is not None,
                queue_titles=[item.display_title for item in self.items]
                if self._is_multi
                else None,
                id="dashboard",
            )
            with Horizontal(classes="dl-actions"):
                yield Button("⏸ Pause", id="btn_pause")
                yield Static("", classes="action-spacer")
                yield Button("✗ Cancel", variant="error", id="btn_cancel")
        yield Footer()

    def on_mount(self) -> None:
        self._started = time.monotonic()
        self.set_interval(1.0, self._tick)
        self._update_phase_label()
        if self.section is not None:
            note = f"Clip: {self._clip_label}"
            if self.section.precise:
                note += " (precise cut)"
            self._dashboard().add_event(note)
        if self._is_multi:
            self._dashboard().set_queue_position(0, len(self.items))
        self._dl()

    # -- convenience ------------------------------------------------------

    def _disk_free(self) -> str:
        """Free space on the destination volume (best effort)."""
        try:
            parent = Path(self.out_template).parent
            if not parent.exists():
                parent = parent.parent
            return human_size(shutil.disk_usage(parent).free)
        except OSError:
            return "—"

    def _dashboard(self) -> DownloadDashboard:
        return self.query_one("#dashboard", DownloadDashboard)

    def _elapsed(self) -> float:
        """Wall-clock download time, excluding time spent paused."""
        if self._paused_at is not None:
            return self._elapsed_base
        return self._elapsed_base + max(time.monotonic() - self._started, 0.0)

    def _tick(self) -> None:
        if self._dismissed or not self.is_attached:
            return
        if self._started and not self._finished and not self._paused:
            self._dashboard().set_elapsed(self._elapsed())

    def _save_queue(self) -> None:
        state = getattr(self.app, "state", None)
        store = self._queue_store or getattr(self.app, "queue_store", None)
        if state is not None and store is not None:
            store.save(state.queue)

    def _safe_record_start(self, item: QueueItem) -> int | None:
        if self._library is None:
            return None
        try:
            return self._library.record_start(item)
        except Exception:
            return None

    def _safe_record_finish(
        self,
        record_id: int | None,
        *,
        status: str,
        path: str,
        size: float | None,
        error: str,
        duration_s: float,
        avg_speed: float | None,
    ) -> None:
        if self._library is None or record_id is None:
            return
        with contextlib.suppress(Exception):
            self._library.record_finish(
                record_id,
                status=status,  # type: ignore[arg-type]
                path=path,
                size=size,
                error=error,
                duration_s=duration_s,
                avg_speed=avg_speed,
            )

    # -- download worker --------------------------------------------------

    @work(thread=True, exclusive=True, name="download", exit_on_error=False)
    def _dl(self) -> None:
        for index, item in enumerate(self.items):
            if self._cancelled or self._dismissed:
                return
            self.app.call_from_thread(self._begin_item, index)
            record_id = self._safe_record_start(item)
            item.status = "running"
            self._save_queue()
            done_path = ""
            last_size: float | None = None
            failed = False
            error = ""
            try:
                for event in download(
                    item.url,
                    selector=item.selector,
                    out_template=item.out_template,
                    extract_audio=item.extract_audio,
                    extra_args=item.extra_args,
                    section=item.section,
                    expected_bytes=item.expected_bytes,
                    control=self._control,
                    merge_format=item.merge_format,
                    audio_format=item.audio_format,
                    audio_quality=item.audio_quality,
                    concurrent_fragments=item.concurrent_fragments,
                    rate_limit=item.rate_limit,
                    write_subtitles=item.write_subtitles,
                    embed_metadata=item.embed_metadata,
                    embed_thumbnail=item.embed_thumbnail,
                    keep_original=item.keep_original,
                ):
                    if event.kind == "done":
                        done_path = event.filename
                    elif event.kind == "download":
                        if event.total:
                            last_size = event.total
                    elif event.kind == "error" and not self._cancelled:
                        error = event.text
                        failed = True
                    self.app.call_from_thread(self._handle_event, event, index)
            except DownloadError as exc:
                failed = True
                error = str(exc)
                if not self._cancelled:
                    self.app.call_from_thread(self._handle_error, str(exc), index, exc.reason)
            except Exception as exc:  # pragma: no cover - defensive
                failed = True
                error = str(exc)
                if not self._cancelled:
                    self.app.call_from_thread(self._handle_error, str(exc), index, None)
            finally:
                elapsed = max(self._elapsed(), 0.001)
                if self._cancelled:
                    # The user pressed Cancel -> keep "cancelled"; quitting the
                    # app (cancel_work) leaves the item resumable.
                    if item.status != "cancelled":
                        item.status = "interrupted"
                elif failed:
                    item.status = "failed"
                    item.error = error
                else:
                    item.status = "done"
                    item.output_path = done_path
                size = last_size
                if done_path:
                    with contextlib.suppress(OSError):
                        size = Path(done_path).stat().st_size
                avg_speed = (size / elapsed) if size else None
                self._save_queue()
                self._safe_record_finish(
                    record_id,
                    status=(
                        "cancelled"
                        if self._cancelled and item.status == "cancelled"
                        else (
                            "interrupted" if self._cancelled else ("failed" if failed else "done")
                        )
                    ),
                    path=done_path,
                    size=size,
                    error=error,
                    duration_s=elapsed,
                    avg_speed=avg_speed,
                )
            if self._cancelled or self._dismissed:
                return
            if failed:
                self._failed += 1
            else:
                self._completed += 1
        self.app.call_from_thread(self._queue_finished)

    def _begin_item(self, index: int) -> None:
        if self._dismissed:
            return
        self._apply_item_attrs(index)
        self._dl_pass = 0
        self._logged_pass = None
        self._pp_logged = False
        self._started = time.monotonic()
        self._elapsed_base = 0.0
        self._paused_at = None
        if self._paused:
            self._paused = False
            self._control.resume()
        with contextlib.suppress(Exception):
            self.query_one("#btn_pause", Button).disabled = False
        dash = self._dashboard()
        dash.begin_item(
            self.title or "video",
            extract_audio=self.extract_audio,
            single_pass=self.section is not None,
            index=index,
            total=len(self.items),
        )
        self._update_phase_label()
        dash.add_event(f"Starting item {index + 1}/{len(self.items)}: {self.title or self.url}")
        if self.section is not None:
            note = f"Clip: {self._clip_label}"
            if self.section.precise:
                note += " (precise cut)"
            dash.add_event(note)

    def _handle_event(self, event: ProgressEvent, index: int | None = None) -> None:
        if self._dismissed:
            return
        if index is None:
            index = self._current_index
        dash = self._dashboard()

        if event.kind == "download":
            if self._paused and event.status != "finished":
                return
            if event.status == "finished":
                dash.update_download(
                    event.downloaded, event.total, event.speed, event.eta, self._dl_pass
                )
                finished_pass = self._dl_pass
                dash.mark_done(finished_pass, event.total or event.downloaded)
                if self.section is not None:
                    stream = "Clip"
                else:
                    stream = "Audio" if (self.extract_audio or finished_pass > 0) else "Video"
                dash.add_event(f"{stream} stream complete", "ok")
                self._dl_pass += 1
                self._update_phase_label()
                return

            dash.update_download(
                event.downloaded, event.total, event.speed, event.eta, self._dl_pass
            )
            if not self._paused:
                dash.set_status("● DOWNLOADING", "downloading")
            if self._logged_pass != self._dl_pass:
                self._logged_pass = self._dl_pass
                if self.section is not None:
                    stream = "clip"
                else:
                    stream = "audio" if (self.extract_audio or self._dl_pass > 0) else "video"
                dash.add_event(f"Downloading {stream} stream…")

        elif event.kind == "postprocess":
            section = event.section or event.filename or "processing"
            dash.update_postprocess(section)
            with contextlib.suppress(Exception):
                self.query_one("#btn_pause", Button).disabled = True
            if not self._pp_logged:
                self._pp_logged = True
                dash.add_event(f"Post-processing ({section})", "warn")

        elif event.kind == "done":
            self.items[index].status = "done"
            self.items[index].output_path = event.filename
            self._save_queue()
            dash.mark_item_done(index)
            if index >= len(self.items) - 1:
                self._finished = True
                failed = sum(1 for item in self.items if item.status == "failed")
                dash.set_elapsed(self._elapsed())
                dash.finish(event.filename)
                if failed:
                    dash.set_status(f"⚠ FINISHED WITH {failed} FAILURE(S)", "error")
                    dash.set_phase("Queue finished — review the log")
                self._set_finished_controls()
                self.set_timer(6.0, self._finish)
            else:
                dash.set_status(f"✓ ITEM {index + 1}/{len(self.items)} COMPLETE", "complete")
                dash.add_event(f"Finished item {index + 1}/{len(self.items)}", "ok")

        elif event.kind == "error":
            if not self._cancelled:
                self._handle_error(event.text, index, None)

    def _queue_finished(self) -> None:
        if self._dismissed or self._finished:
            return
        self._finished = True
        dash = self._dashboard()
        dash.finish("")
        if self._failed:
            dash.set_status(f"⚠ FINISHED WITH {self._failed} FAILURE(S)", "error")
            dash.set_phase("Queue finished — review the log")
        else:
            dash.set_status("✓ QUEUE COMPLETE", "complete")
            dash.set_phase("All queued downloads finished")
        dash.set_elapsed(self._elapsed())
        self._set_finished_controls()
        self.set_timer(6.0, self._finish)

    def _update_phase_label(self) -> None:
        if self.section is not None:
            label = "Downloading clip"
        elif self.extract_audio:
            label = "Audio stream  •  extracting audio"
        elif self._dl_pass == 0:
            label = "Stream 1 of 2  •  video"
        elif self._dl_pass == 1:
            label = "Stream 2 of 2  •  audio"
        else:
            label = "Merging audio + video…"
        if self.section is not None:
            label += f"  •  {self._clip_label}"
        with contextlib.suppress(Exception):
            self._dashboard().set_phase(label)

    def _set_finished_controls(self) -> None:
        try:
            self.query_one("#btn_pause", Button).disabled = True
            close = self.query_one("#btn_cancel", Button)
            close.label = "Close"
            close.variant = "default"
        except Exception:  # pragma: no cover - screen may be closing
            pass

    def _handle_error(
        self,
        message: str,
        index: int | None = None,
        reason: object | None = None,
    ) -> None:
        if self._dismissed:
            return
        if index is None:
            index = self._current_index
        self.items[index].status = "failed"
        self.items[index].error = message
        self._save_queue()
        dash = self._dashboard()
        dash.fail_item(index, message)
        if index >= len(self.items) - 1:
            self._finished = True
            dash.error(message)
            self._set_finished_controls()
            self.set_timer(8.0, self._finish)
        else:
            dash.add_event(message, "err")
            dash.set_status(f"⚠ ITEM {index + 1} FAILED", "error")
            dash.set_phase("Continuing with the next queue item…")

    def _finish(self) -> None:
        if self._dismissed:
            return
        self._dismissed = True
        self.app.pop_screen()

    def cancel_work(self) -> None:
        """Cancel any running download (safe to call more than once)."""
        if self._finished or self._dismissed:
            return
        self._dismissed = True
        self._cancelled = True
        self._control.cancel()
        item = self.items[self._current_index]
        if item.status == "running":
            item.status = "interrupted"
            self._save_queue()

    def on_unmount(self) -> None:
        """Don't let a stray yt-dlp/ffmpeg process outlive the screen."""
        if not self._finished and not self._dismissed:
            self.cancel_work()
        else:
            self._control.cancel()

    # -- actions ----------------------------------------------------------

    def action_toggle_pause(self) -> None:
        if self._finished or self._cancelled or self._dismissed:
            return
        dash = self._dashboard()
        button = self.query_one("#btn_pause", Button)
        if button.disabled:
            return
        if self._paused:
            if self._control.resume():
                self._paused = False
                self._paused_at = None
                self._started = time.monotonic()
                dash.set_paused(False)
                dash.add_event("Download resumed", "info")
                button.label = "⏸ Pause"
        else:
            if self._control.pause():
                now = time.monotonic()
                self._elapsed_base += max(now - self._started, 0.0)
                self._paused_at = now
                self._paused = True
                dash.set_paused(True)
                dash.add_event("Download paused", "warn")
                button.label = "▶ Resume"
            else:
                dash.add_event("Pause is not supported on this platform", "err")

    def action_cancel(self) -> None:
        if self._dismissed:
            return
        if self._finished or self._cancelled:
            self._finish()
            return
        self._cancelled = True
        self._control.cancel()
        item = self.items[self._current_index]
        if item.status == "running":
            item.status = "cancelled"
            self._save_queue()
        dash = self._dashboard()
        dash.set_status("✗ CANCELLING", "error")
        dash.add_event("Cancelling download…", "warn")
        self.query_one("#btn_pause", Button).disabled = True
        self.set_timer(1.5, self._finish)

    @on(Button.Pressed, "#btn_pause")
    def _on_pause_pressed(self, _: Button.Pressed) -> None:
        self.action_toggle_pause()

    @on(Button.Pressed, "#btn_cancel")
    def _on_cancel_pressed(self, _: Button.Pressed) -> None:
        if self._finished:
            self._finish()
        else:
            self.action_cancel()


class StartupErrorScreen(Screen):
    """Shown when a required external tool is missing."""

    BINDINGS = [("escape", "quit", "Quit"), ("ctrl+c", "quit", "Quit")]

    def __init__(self, report: DependencyReport) -> None:
        super().__init__()
        self.report = report

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Container(classes="center-box"):
            yield Static("Missing dependencies", classes="title")
            yield Static(self.report.as_text(), classes="message", markup=False)
            yield Static(
                "Install yt-dlp and ffmpeg, then restart YoinkTUI. "
                "Run 'yoinktui --doctor' for a full check.",
                classes="subtitle",
            )
        yield Footer()

    def action_quit(self) -> None:
        self.app.exit()


class ErrorModal(ModalScreen):
    """Simple error modal with dismiss."""

    def __init__(self, message: str) -> None:
        super().__init__()
        self.message = message

    def compose(self) -> ComposeResult:
        with Container(classes="dialog"):
            yield Static("✗ Error", classes="title")
            yield Static(self.message, classes="message", markup=False)
            yield Button("Dismiss", variant="error", id="dismiss")

    @on(Button.Pressed, "#dismiss")
    def _on_dismiss(self, _: Button.Pressed) -> None:
        self.dismiss()
