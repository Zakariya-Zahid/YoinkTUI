"""Screens: URL input, format picker, download progress, completion."""

from __future__ import annotations

import contextlib
import io
import shutil
import time
from dataclasses import dataclass
from importlib.resources import files as resource_files
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from PIL import Image as PILImage
from rich.markup import escape
from textual import on, work
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen, Screen
from textual.timer import Timer
from textual.widgets import Button, Footer, Header, Input, Static, Switch
from textual_image.widget import AutoImage

from yoinktui.backend.config import AppConfig, load_last_url, save_last_url
from yoinktui.backend.errors import DownloadError
from yoinktui.backend.models import FormatInfo, MediaInfo
from yoinktui.backend.ytdlp import (
    DependencyReport,
    DownloadControl,
    ProgressEvent,
    Section,
    audio_selector,
    download,
    format_timecode,
    parse_timecode,
    probe,
    resolve_merge_format,
    section_slug,
    video_selector,
)
from yoinktui.tui.widgets import (
    DownloadDashboard,
    FormatTable,
    InfoPanel,
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

    def __init__(self) -> None:
        super().__init__()
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
            # Inline probe status (hidden by default)
            yield Static("", id="probe-status", classes="probe-status hidden")
        yield Footer()

    def on_mount(self) -> None:
        last_url = getattr(getattr(self.app, "state", None), "last_url", "") or load_last_url()
        if last_url:
            self.query_one("#url", UrlInput).value = last_url
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
            url_input.focus()

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

    def _show_probe_status(self, url: str) -> None:
        """Show compact inline probing status."""
        status = self.query_one("#probe-status", Static)
        status.remove_class("hidden")
        status.update(f"[dim]⟳ Probing[/dim] [cyan]{url}[/cyan] [dim]...[/dim]")
        self._animate_probe_spinner(status, url)

    def _animate_probe_spinner(self, status: Static, url: str) -> None:
        frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        i = 0

        def tick() -> None:
            nonlocal i
            if status.has_class("hidden"):
                return
            status.update(
                f"[dim]{frames[i % len(frames)]} Probing[/dim] [cyan]{url}[/cyan] [dim]...[/dim]"
            )
            i += 1

        if self._spinner_timer is not None:
            self._spinner_timer.stop()
        self._spinner_timer = self.set_interval(0.08, tick)

    def _show_error(self, message: str) -> None:
        """Show an inline, auto-hiding error instead of stacking modals."""
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


class FormatScreen(Screen):
    """Format selection + thumbnail + metadata."""

    BINDINGS = [
        ("d", "download", "Download"),
        ("c", "clip", "Clip range"),
        ("C", "clip", "Clip range"),
        ("v", "mode_video", "Video+Audio"),
        ("o", "mode_vonly", "Video Only"),
        ("a", "mode_audio", "Audio Only"),
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
            yield Static("", classes="action-spacer")
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

        toast = self.query_one("#toast", StatusToast)
        if self._selected_format:
            toast.info(
                f"Default: {self._selected_format.label} • Press 'd' or Enter on row to Download "
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

        if self._mode == "audio":
            fmt = self._selected_format
            if fmt is None or fmt.has_video or not fmt.has_audio:
                fmt = self.info.audio_formats[0] if self.info.audio_formats else None
            full = self._format_full_size(fmt, duration)
            return full * fraction if full else None

        if self._mode == "vonly":
            fmt = (
                self._selected_format
                if self._selected_format and self._selected_format.has_video
                else None
            )
            full = self._format_full_size(fmt, duration)
            return full * fraction if full else None

        fmt = (
            self._selected_format
            if self._selected_format and self._selected_format.has_video
            else None
        )
        if fmt is None:
            config = getattr(self.app, "config", AppConfig())
            cap = config.quality_cap or None
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
        config = getattr(self.app, "config", AppConfig())
        if self._mode == "audio":
            if (
                self._selected_format
                and self._selected_format.has_audio
                and not self._selected_format.has_video
            ):
                selector = self._selected_format.format_id
            else:
                selector = audio_selector()
            extract_audio = True
        elif self._mode == "vonly":
            format_id = self._selected_format.format_id if self._selected_format else None
            selector = format_id if format_id else "bv*"
            extract_audio = False
        else:  # video (video + audio)
            format_id = self._selected_format.format_id if self._selected_format else None
            cap = config.quality_cap if not format_id else None
            selector = video_selector(format_id, cap)
            extract_audio = False

        merge_format = config.merge_format
        if self._mode == "video":
            video_format = self._selected_format
            audio_format = (
                self.info.audio_formats[0]
                if video_format is not None and not video_format.has_audio
                else None
            )
            merge_format = resolve_merge_format(config.merge_format, video_format, audio_format)

        out_dir = config.download_dir
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self.query_one("#toast", StatusToast).error(f"Cannot create download directory: {exc}")
            return
        safe_title = (
            "".join(c for c in self.info.title if c.isalnum() or c in " -_.").strip()[:80]
            or "video"
        )
        clip_suffix = f" [clip {section_slug(self._section)}]" if self._section is not None else ""
        out_template = str(out_dir / f"{safe_title}{clip_suffix}.%(ext)s")

        url = self.info.webpage_url
        if not url and self.info.id:
            url = f"https://www.youtube.com/watch?v={self.info.id}"

        app_state = getattr(self.app, "state", None)
        if app_state is not None:
            app_state.current_info = self.info
            app_state.selected_format = self._selected_format
            app_state.mode = self._mode

        self._download_started = True
        self.app.push_screen(
            DownloadScreen(
                url=url,
                selector=selector,
                out_template=out_template,
                extract_audio=extract_audio,
                title=self.info.title or "video",
                extra_args=config.ytdlp_args,
                section=self._section,
                expected_bytes=self._estimated_section_bytes(),
                merge_format=merge_format,
                audio_format=config.audio_format,
                audio_quality=config.audio_quality,
                concurrent_fragments=config.concurrent_fragments,
                rate_limit=config.rate_limit,
                write_subtitles=config.write_subtitles,
                embed_metadata=config.embed_metadata,
                embed_thumbnail=config.embed_thumbnail,
                keep_original=config.keep_original,
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
        url: str,
        selector: str,
        out_template: str,
        extract_audio: bool,
        title: str,
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
    ) -> None:
        super().__init__()
        self.url = url
        self.selector = selector
        self.out_template = out_template
        self.extract_audio = extract_audio
        self.title = title
        self.extra_args = list(extra_args or [])
        self.section = section
        self.expected_bytes = expected_bytes
        self.merge_format = merge_format
        self.audio_format = audio_format
        self.audio_quality = audio_quality
        self.concurrent_fragments = concurrent_fragments
        self.rate_limit = rate_limit
        self.write_subtitles = write_subtitles
        self.embed_metadata = embed_metadata
        self.embed_thumbnail = embed_thumbnail
        self.keep_original = keep_original
        if section is None:
            self._clip_label = ""
        else:
            end = format_timecode(section.end) if section.end is not None else "end"
            self._clip_label = f"{format_timecode(section.start)} → {end}"

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
        self._started = 0.0

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Container(classes="download-manager"):
            yield DownloadDashboard(
                title=self.title or "video",
                extract_audio=self.extract_audio,
                disk_free=self._disk_free(),
                single_pass=self.section is not None,
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

    def _tick(self) -> None:
        if self._dismissed or not self.is_attached:
            return
        if self._started and not self._finished:
            self._dashboard().set_elapsed(time.monotonic() - self._started)

    # -- download worker --------------------------------------------------

    @work(thread=True, exclusive=True, name="download", exit_on_error=False)
    def _dl(self) -> None:
        try:
            for event in download(
                self.url,
                selector=self.selector,
                out_template=self.out_template,
                extract_audio=self.extract_audio,
                extra_args=self.extra_args,
                section=self.section,
                expected_bytes=self.expected_bytes,
                control=self._control,
                merge_format=self.merge_format,
                audio_format=self.audio_format,
                audio_quality=self.audio_quality,
                concurrent_fragments=self.concurrent_fragments,
                rate_limit=self.rate_limit,
                write_subtitles=self.write_subtitles,
                embed_metadata=self.embed_metadata,
                embed_thumbnail=self.embed_thumbnail,
                keep_original=self.keep_original,
            ):
                self.app.call_from_thread(self._handle_event, event)
        except DownloadError as exc:
            if not self._cancelled:
                self.app.call_from_thread(self._handle_error, str(exc))
        except Exception as exc:  # pragma: no cover - defensive
            if not self._cancelled:
                self.app.call_from_thread(self._handle_error, str(exc))

    def _handle_event(self, event: ProgressEvent) -> None:
        if self._dismissed:
            return
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
            if not self._pp_logged:
                self._pp_logged = True
                dash.add_event(f"Post-processing ({section})", "warn")

        elif event.kind == "done":
            self._finished = True
            dash.set_elapsed(time.monotonic() - self._started)
            dash.finish(event.filename)
            self._set_finished_controls()

        elif event.kind == "error":
            if not self._cancelled:
                self._handle_error(event.text)

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

    def _handle_error(self, message: str) -> None:
        if self._dismissed:
            return
        self._finished = True
        dash = self._dashboard()
        dash.error(message)
        self._set_finished_controls()
        self.set_timer(5.0, self._finish)

    def _finish(self) -> None:
        if self._dismissed:
            return
        self._dismissed = True
        self.app.pop_screen()

    def cancel_work(self) -> None:
        """Cancel any running download (safe to call more than once)."""
        self._dismissed = True
        self._cancelled = True
        self._control.cancel()

    def on_unmount(self) -> None:
        """Don't let a stray yt-dlp/ffmpeg process outlive the screen."""
        self.cancel_work()

    # -- actions ----------------------------------------------------------

    def action_toggle_pause(self) -> None:
        if self._finished or self._cancelled or self._dismissed:
            return
        dash = self._dashboard()
        button = self.query_one("#btn_pause", Button)
        if self._paused:
            if self._control.resume():
                self._paused = False
                dash.set_paused(False)
                dash.add_event("Download resumed", "info")
                button.label = "⏸ Pause"
        else:
            if self._control.pause():
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
