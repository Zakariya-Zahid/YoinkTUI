"""Main application class."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding

from yoinktui.tui.screens import UrlScreen


@dataclass
class AppConfig:
    download_dir: Path = Path.home() / "Videos" / "yoinktui"


class YoinkTUIApp(App):
    """YoinkTUI — animated TUI for downloading media with yt-dlp."""

    TITLE = "YoinkTUI"
    SUB_TITLE = "Snatch media from 1000+ sites"
    CSS_PATH = "tui/app.tcss"
    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit", show=True),
        Binding("ctrl+d", "toggle_dark", "Toggle theme", show=True),
    ]

    config: AppConfig = AppConfig()

    def __init__(self) -> None:
        super().__init__()
        self.config.download_dir.mkdir(parents=True, exist_ok=True)

    def on_mount(self) -> None:
        self.push_screen(UrlScreen())

    def action_toggle_dark(self) -> None:
        self.dark = not self.dark