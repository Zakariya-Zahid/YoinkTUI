"""TUI package."""

from yoinktui.tui.screens import (
    DownloadScreen,
    ErrorModal,
    FormatScreen,
    StartupErrorScreen,
    UrlScreen,
    clean_url,
)
from yoinktui.tui.widgets import (
    DownloadDashboard,
    DownloadQueueItem,
    FormatTable,
    InfoPanel,
    ModalDialog,
    StatTile,
    StatusToast,
    ThumbnailCard,
    UrlInput,
)

__all__ = [
    "DownloadDashboard",
    "DownloadQueueItem",
    "DownloadScreen",
    "ErrorModal",
    "FormatScreen",
    "FormatTable",
    "InfoPanel",
    "ModalDialog",
    "StartupErrorScreen",
    "StatTile",
    "StatusToast",
    "ThumbnailCard",
    "UrlInput",
    "UrlScreen",
    "clean_url",
]
