"""Tests for the typed error taxonomy."""

from __future__ import annotations

import pytest

from yoinktui.backend.errors import DownloadError, ErrorReason, classify_error


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("ERROR: Connection timed out", ErrorReason.NETWORK),
        ("Unable to download webpage: HTTP Error 503", ErrorReason.NETWORK),
        ("ERROR: This video is not available in your country", ErrorReason.GEO),
        ("ERROR: Sign in to confirm your age", ErrorReason.AUTH),
        ("ERROR: HTTP Error 403: Forbidden", ErrorReason.AUTH),
        ("ERROR: [youtube] abc: Video unavailable", ErrorReason.NOT_FOUND),
        ("ERROR: Unsupported URL: https://example.com", ErrorReason.UNSUPPORTED),
        ("No downloadable streams were found", ErrorReason.NO_STREAMS),
        ("OSError: [Errno 28] No space left on device", ErrorReason.DISK),
        ("Postprocessing: ffmpeg not found", ErrorReason.FFMPEG_MISSING),
        ("Cancelled", ErrorReason.CANCELLED),
        ("something odd happened", ErrorReason.UNKNOWN),
    ],
)
def test_classify_error(message: str, expected: ErrorReason) -> None:
    assert classify_error(message) is expected


def test_classify_is_case_insensitive() -> None:
    assert classify_error("CONNECTION RESET") is ErrorReason.NETWORK


def test_download_error_includes_hint_and_action() -> None:
    error = DownloadError("boom", ErrorReason.NETWORK)
    text = str(error)
    assert "boom" in text
    assert "Check your connection" in text
    assert "Retry" in text
    assert error.user_message == text


def test_download_error_allows_custom_guidance() -> None:
    error = DownloadError("blocked", ErrorReason.AUTH, hint="cookies?", action="use firefox")
    assert "cookies?" in error.user_message
    assert "use firefox" in error.user_message
