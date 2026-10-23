"""Main application class."""

from __future__ import annotations

import contextlib
import os
from dataclasses import dataclass

from textual.app import App
from textual.binding import Binding

from yoinktui.backend.config import AppConfig, load_config, load_last_url
from yoinktui.backend.models import FormatInfo, MediaInfo
from yoinktui.backend.ytdlp import DependencyReport, check_dependencies
from yoinktui.tui.screens import StartupErrorScreen, UrlScreen

__all__ = ["AppConfig", "AppState", "YoinkTUIApp", "load_config"]


@dataclass(slots=True)
class AppState:
    """Runtime state shared between screens.

    Kept per app instance so tests (and future windows) never share mutable
    globals.  Durable history lives in module 08; the last URL is the one
    small piece persisted today.
    """

    last_url: str = ""
    current_url: str = ""
    current_info: MediaInfo | None = None
    selected_format: FormatInfo | None = None
    mode: str = "video"


class YoinkTUIApp(App):
    """YoinkTUI — Steam-style TUI for downloading media with yt-dlp."""

    TITLE = "YoinkTUI"
    SUB_TITLE = "Snatch media from 1000+ sites"
    CSS_PATH = "tui/app.tcss"
    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit", show=True),
        Binding("ctrl+d", "toggle_dark", "Toggle theme", show=True),
    ]

    config: AppConfig

    def __init__(self, config: AppConfig | None = None, *, state: AppState | None = None) -> None:
        resolved = config or load_config()
        # Textual reads NO_COLOR in App.__init__ and installs its monochrome
        # line filter.  Bridge our config value to it without leaking the env
        # var into child processes or later App instances.
        previous_no_color = os.environ.get("NO_COLOR")
        if resolved.no_color:
            os.environ["NO_COLOR"] = "1"
        try:
            super().__init__()
        finally:
            if resolved.no_color:
                if previous_no_color is None:
                    os.environ.pop("NO_COLOR", None)
                else:
                    os.environ["NO_COLOR"] = previous_no_color
        self.config = resolved
        self.state = state or AppState(last_url=load_last_url())
        self.dependency_report: DependencyReport | None = None
        try:
            self.config.download_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self.config.warnings.append(f"Could not create download directory: {exc}")

    def on_mount(self) -> None:
        self._apply_theme()
        report = check_dependencies()
        self.dependency_report = report
        if not report.ok:
            self.push_screen(StartupErrorScreen(report))
            return
        for warning in (*report.warnings, *self.config.warnings):
            self.notify(warning, severity="warning", timeout=10)
        self.push_screen(UrlScreen())

    def _apply_theme(self) -> None:
        theme = (self.config.theme or "").strip()
        lowered = theme.lower()
        if lowered in ("dark", "textual-dark"):
            self.theme = "textual-dark"
            self.dark = True
        elif lowered in ("light", "textual-light"):
            self.theme = "textual-light"
            self.dark = False
        elif theme:
            try:
                self.theme = theme
            except Exception:
                self.notify(
                    f"Unknown theme {theme!r}; keeping the default.",
                    severity="warning",
                )

    def action_toggle_dark(self) -> None:
        self.dark = not self.dark

    async def action_quit(self) -> None:
        """Cancel workers before exiting so external tools don't become orphans."""
        for screen in list(self.screen_stack):
            cancel = getattr(screen, "cancel_work", None)
            if callable(cancel):
                with contextlib.suppress(Exception):
                    cancel()
        self.exit()
