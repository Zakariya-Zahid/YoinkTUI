"""Main application class."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding

from yoinktui.tui.screens import UrlScreen


@dataclass(slots=True)
class AppConfig:
    download_dir: Path = field(default_factory=lambda: Path.home() / "Videos" / "yoinktui")
    cookies_from_browser: str | None = None
    proxy: str | None = None
    extra_args: tuple[str, ...] = ()

    @property
    def ytdlp_args(self) -> list[str]:
        """Extra yt-dlp flags shared by probe and download."""
        args: list[str] = []
        if self.cookies_from_browser:
            args += ["--cookies-from-browser", self.cookies_from_browser]
        if self.proxy:
            args += ["--proxy", self.proxy]
        args += list(self.extra_args)
        return args


class YoinkTUIApp(App):
    """YoinkTUI — animated TUI for downloading media with yt-dlp."""

    TITLE = "YoinkTUI"
    SUB_TITLE = "Snatch media from 1000+ sites"
    CSS_PATH = "tui/app.tcss"
    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit", show=True),
        Binding("ctrl+d", "toggle_dark", "Toggle theme", show=True),
    ]

    config: AppConfig

    def __init__(self, config: AppConfig | None = None) -> None:
        super().__init__()
        self.config = config or AppConfig()
        self.config.download_dir.mkdir(parents=True, exist_ok=True)

    def on_mount(self) -> None:
        self.push_screen(UrlScreen())

    def action_toggle_dark(self) -> None:
        self.dark = not self.dark