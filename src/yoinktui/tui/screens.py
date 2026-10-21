"""Screens: URL input, format picker, download progress, completion."""

from __future__ import annotations

import io
import shutil
import time
from importlib.resources import files as resource_files
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image as PILImage
from rich.markup import escape
from textual import on, work
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, Footer, Header, Static
from textual_image.widget import AutoImage

from yoinktui.backend.models import FormatInfo, MediaInfo
from yoinktui.backend.ytdlp import (
    BackendError,
    DownloadControl,
    ProgressEvent,
    audio_selector,
    download,
    probe,
    video_selector,
)
from yoinktui.tui.widgets import (
    DownloadDashboard,
    FormatTable,
    InfoPanel,
    ModalDialog,
    StatusToast,
    ThumbnailCard,
    UrlInput,
    human_size,
)

if TYPE_CHECKING:
    from yoinktui.app import YoinkTUIApp


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


class UrlScreen(Screen):
    """First screen: enter a URL, press Enter to probe."""

    BINDINGS = [
        ("escape", "quit", "Quit"),
        ("ctrl+c", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        with Container(classes="center-box"):
            with Container(classes="logo-wrap"):
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
        self._fit_brand()
        self.query_one("#url", UrlInput).focus()

    def on_resize(self) -> None:
        self._fit_brand()

    def _fit_brand(self) -> None:
        """Hide the wordmark on very short terminals so the input stays usable."""
        wraps = self.query(".logo-wrap")
        if wraps:
            wraps.first().set_class(self.size.height < 22, "hidden")

    @on(UrlInput.Submitted)
    def _on_submit(self, event: UrlInput.Submitted) -> None:
        url = event.value.strip()
        if not url:
            return

        # Show inline probing status
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
            status.update(f"[dim]{frames[i % len(frames)]} Probing[/dim] [cyan]{url}[/cyan] [dim]...[/dim]")
            i += 1

        self.set_interval(0.08, tick)

    def _hide_probe_status(self, error: str | None = None) -> None:
        """Hide probe status, optionally show error."""
        status = self.query_one("#probe-status", Static)
        status.add_class("hidden")
        if error:
            status.update(f"[red]✗[/red] {escape(error)}")
            status.remove_class("hidden")
            # Auto-hide error after 3 seconds
            self.set_timer(3.0, lambda: status.add_class("hidden"))

    @work(thread=True, exclusive=True, name="probe")
    def _run_probe(self, url: str) -> None:
        from yoinktui.app import AppConfig

        config = getattr(self.app, "config", AppConfig())
        try:
            info = probe(url, extra_args=config.ytdlp_args)
            self.app.call_from_thread(self._on_probed, info, None, url)
        except BackendError as e:
            self.app.call_from_thread(self._on_probed, None, str(e), url)
        except Exception as e:
            self.app.call_from_thread(self._on_probed, None, str(e), url)

    def _on_probed(self, info: MediaInfo | None, error: str | None, url: str) -> None:
        if error:
            self._hide_probe_status(error)
            self.app.push_screen(ErrorModal(error))
            return
        if info and not info.webpage_url:
            info.webpage_url = url
        self._hide_probe_status()
        self.app.push_screen(FormatScreen(info))

    def action_quit(self) -> None:
        self.app.exit()


class FormatScreen(Screen):
    """Format selection + thumbnail + metadata."""

    BINDINGS = [
        ("d", "download", "Download"),
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

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Container(classes="top-row"):
            with Vertical(classes="left-pane"):
                yield FormatTable(id="table")
            with Vertical(classes="right-pane"):
                yield ThumbnailCard(id="thumb")
                yield InfoPanel(id="info")
        with Horizontal(classes="ActionBar"):
            yield Button("▶ Video + Audio", variant="success", id="btn_video")
            yield Button("📹 Video Only", variant="default", id="btn_vonly")
            yield Button("🎵 Audio Only", variant="default", id="btn_audio")
            yield Static("", classes="action-spacer")
            yield Button("⬇ Download", variant="warning", id="btn_download")
        yield StatusToast(id="toast")
        yield Footer()

    def on_mount(self) -> None:
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
            toast.info(f"Default: {self._selected_format.label} • Press 'd' or Enter on row to Download")

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
        elif btn_id == "btn_download":
            self._start_download()
            return
        self._update_mode_buttons()

    def action_download(self) -> None:
        self._start_download()

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
        for btn_id, mode in [("btn_video", "video"), ("btn_vonly", "vonly"), ("btn_audio", "audio")]:
            btn = self.query_one(f"#{btn_id}", Button)
            btn.variant = "success" if self._mode == mode else "default"
            btn.refresh()

    def _start_download(self) -> None:
        if self._mode == "audio":
            if self._selected_format and self._selected_format.has_audio and not self._selected_format.has_video:
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
            cap = 1080 if not format_id else None
            selector = video_selector(format_id, cap)
            extract_audio = False

        from yoinktui.app import AppConfig
        config = getattr(self.app, "config", AppConfig())
        out_dir = config.download_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        safe_title = "".join(c for c in self.info.title if c.isalnum() or c in " -_.").strip()[:80] or "video"
        out_template = str(out_dir / f"{safe_title}.%(ext)s")

        url = self.info.webpage_url
        if not url and self.info.id:
            url = f"https://www.youtube.com/watch?v={self.info.id}"

        self.app.push_screen(DownloadScreen(
            url=url,
            selector=selector,
            out_template=out_template,
            extract_audio=extract_audio,
            title=self.info.title or "video",
            extra_args=config.ytdlp_args,
        ))

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
    ) -> None:
        super().__init__()
        self.url = url
        self.selector = selector
        self.out_template = out_template
        self.extract_audio = extract_audio
        self.title = title
        self.extra_args = list(extra_args or [])

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
                title=self.title,
                extract_audio=self.extract_audio,
                disk_free=self._disk_free(),
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
                control=self._control,
            ):
                self.app.call_from_thread(self._handle_event, event)
        except BackendError as exc:
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
            if event.status == "finished":
                dash.update_download(
                    event.downloaded, event.total, event.speed, event.eta, self._dl_pass
                )
                finished_pass = self._dl_pass
                dash.mark_done(finished_pass, event.total or event.downloaded)
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
        if self.extract_audio:
            label = "Audio stream  •  extracting audio"
        elif self._dl_pass == 0:
            label = "Stream 1 of 2  •  video"
        elif self._dl_pass == 1:
            label = "Stream 2 of 2  •  audio"
        else:
            label = "Merging audio + video…"
        try:
            self._dashboard().set_phase(label)
        except Exception:  # pragma: no cover - screen may be closing
            pass

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

    def on_unmount(self) -> None:
        """Don't let a stray yt-dlp/ffmpeg process outlive the screen."""
        self._dismissed = True
        self._cancelled = True
        self._control.cancel()

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
