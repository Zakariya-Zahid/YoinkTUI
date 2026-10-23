"""Typed error taxonomy shared by the probe and download paths.

Every failure the backend reports carries a :class:`ErrorReason`, a short
user-facing ``hint``, and a suggested ``action``.  The TUI renders the
``user_message`` property; scripts can branch on ``reason``.
"""

from __future__ import annotations

from enum import StrEnum


class ErrorReason(StrEnum):
    """Coarse buckets for backend failures."""

    NETWORK = "network"
    GEO = "geo"
    AUTH = "auth"
    NOT_FOUND = "not_found"
    DISK = "disk"
    FFMPEG_MISSING = "ffmpeg_missing"
    CANCELLED = "cancelled"
    UNSUPPORTED = "unsupported"
    NO_STREAMS = "no_streams"
    UNKNOWN = "unknown"


_HINTS: dict[ErrorReason, str] = {
    ErrorReason.NETWORK: "Check your connection and try again.",
    ErrorReason.GEO: "This media is blocked in your region.",
    ErrorReason.AUTH: "The site needs a logged-in session or fresh cookies.",
    ErrorReason.NOT_FOUND: "The URL may be private, deleted, or mistyped.",
    ErrorReason.DISK: "There is not enough free space on the destination drive.",
    ErrorReason.FFMPEG_MISSING: "ffmpeg is required to merge or post-process media.",
    ErrorReason.CANCELLED: "The operation was cancelled.",
    ErrorReason.UNSUPPORTED: "yt-dlp does not have an extractor for this URL.",
    ErrorReason.NO_STREAMS: "The site returned metadata but no downloadable streams.",
    ErrorReason.UNKNOWN: "The backend could not classify this failure.",
}

_ACTIONS: dict[ErrorReason, str] = {
    ErrorReason.NETWORK: "Retry in a moment.",
    ErrorReason.GEO: "Try --proxy or a VPN, then retry.",
    ErrorReason.AUTH: "Try --cookies-from-browser firefox (or chrome/brave).",
    ErrorReason.NOT_FOUND: "Check the URL in a browser, then retry.",
    ErrorReason.DISK: "Free some space or pass --download-dir DIR.",
    ErrorReason.FFMPEG_MISSING: "Install ffmpeg and make sure it is on PATH.",
    ErrorReason.CANCELLED: "Retry when ready.",
    ErrorReason.UNSUPPORTED: "Update yt-dlp (yt-dlp -U) and retry.",
    ErrorReason.NO_STREAMS: "Update yt-dlp and try cookies/proxy if the site is restricted.",
    ErrorReason.UNKNOWN: "Retry, or run 'yoinktui --doctor' to check dependencies.",
}


class DownloadError(RuntimeError):
    """A backend failure with a typed reason and user-facing guidance."""

    def __init__(
        self,
        message: str,
        reason: ErrorReason = ErrorReason.UNKNOWN,
        *,
        hint: str | None = None,
        action: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.reason = reason
        self.hint = _HINTS.get(reason, "") if hint is None else hint
        self.action = _ACTIONS.get(reason, "") if action is None else action

    @property
    def user_message(self) -> str:
        """Message plus hint/action, ready to show in the UI."""
        parts = [self.message]
        if self.hint:
            parts.append(f"Hint: {self.hint}")
        if self.action:
            parts.append(f"Next: {self.action}")
        return "\n\n".join(parts)

    def __str__(self) -> str:  # noqa: D105 - inherit docstring from RuntimeError
        return self.user_message


# Historical name kept so older imports keep working.
BackendError = DownloadError


# Checked in order: the first matching pattern wins.
_PATTERNS: tuple[tuple[ErrorReason, tuple[str, ...]], ...] = (
    (ErrorReason.CANCELLED, ("cancelled", "canceled")),
    (
        ErrorReason.FFMPEG_MISSING,
        ("ffmpeg not found", "ffmpeg: not found", "ffmpeg is not installed"),
    ),
    (ErrorReason.UNSUPPORTED, ("unsupported url", "unsupported site", "no suitable extractor")),
    (
        ErrorReason.NO_STREAMS,
        (
            "no downloadable streams",
            "no video formats found",
            "requested format is not available",
        ),
    ),
    (
        ErrorReason.AUTH,
        (
            "login",
            "log in",
            "sign in",
            "sign-in",
            "cookies",
            "private video",
            "private content",
            "members-only",
            "members only",
            "authentication",
            "401",
            "403",
            "forbidden",
            "age-restricted",
            "confirm your age",
        ),
    ),
    (
        ErrorReason.GEO,
        (
            "not available in your country",
            "blocked in your country",
            "geo restricted",
            "geo-restricted",
            "region locked",
        ),
    ),
    (
        ErrorReason.NOT_FOUND,
        (
            "404",
            "not found",
            "does not exist",
            "no longer available",
            "unavailable",
            "deleted",
            "removed",
        ),
    ),
    (
        ErrorReason.DISK,
        (
            "no space left",
            "disk full",
            "not enough space",
            "read-only file system",
            "permission denied",
        ),
    ),
    (
        ErrorReason.NETWORK,
        (
            "timed out",
            "timeout",
            "connection",
            "network",
            "temporary failure",
            "name resolution",
            "dns",
            "ssl",
            "http error 5",
            "unable to download webpage",
            "remote end closed",
            "reset by peer",
        ),
    ),
)


def classify_error(message: str) -> ErrorReason:
    """Map a raw yt-dlp/ffmpeg message onto the typed taxonomy."""
    text = (message or "").lower()
    for reason, needles in _PATTERNS:
        if any(needle in text for needle in needles):
            return reason
    return ErrorReason.UNKNOWN
