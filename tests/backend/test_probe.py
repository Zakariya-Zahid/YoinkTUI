"""Tests for probe parsing, typed failures, timeout, and cancellation."""

from __future__ import annotations

import json
import sys

import pytest

from yoinktui.backend import ytdlp
from yoinktui.backend.errors import DownloadError, ErrorReason


def _payload(*formats: dict) -> str:
    return json.dumps(
        {
            "id": "abc",
            "title": "Demo",
            "webpage_url": "https://example.com/v",
            "formats": list(formats),
        }
    )


def test_probe_parses_media_info(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _payload(
        {"format_id": "137", "vcodec": "avc1", "acodec": "none", "height": 1080},
        {"format_id": "140", "vcodec": "none", "acodec": "mp4a", "abr": 128},
    )
    monkeypatch.setattr(ytdlp, "_capture", lambda *args, **kwargs: (0, payload, ""))
    info = ytdlp.probe("https://example.com/v")
    assert info.title == "Demo"
    assert len(info.video_formats) == 1
    assert len(info.audio_formats) == 1


def test_probe_raises_typed_unsupported_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        ytdlp,
        "_capture",
        lambda *args, **kwargs: (1, "", "ERROR: Unsupported URL: https://example.com/v"),
    )
    with pytest.raises(DownloadError) as caught:
        ytdlp.probe("https://example.com/v")
    assert caught.value.reason is ErrorReason.UNSUPPORTED


def test_probe_raises_no_streams_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ytdlp, "_capture", lambda *args, **kwargs: (0, _payload(), ""))
    with pytest.raises(DownloadError) as caught:
        ytdlp.probe("https://example.com/v")
    assert caught.value.reason is ErrorReason.NO_STREAMS


def test_probe_raises_not_found_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        ytdlp,
        "_capture",
        lambda *args, **kwargs: (1, "", "ERROR: Video unavailable"),
    )
    with pytest.raises(DownloadError) as caught:
        ytdlp.probe("https://example.com/v")
    assert caught.value.reason is ErrorReason.NOT_FOUND


def test_probe_command_has_safety_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[list[str]] = []

    def fake_capture(cmd, **kwargs):
        seen.append(cmd)
        return 0, _payload({"format_id": "1", "vcodec": "avc1", "height": 720}), ""

    monkeypatch.setattr(ytdlp, "_capture", fake_capture)
    ytdlp.probe("https://example.com/v", ["--proxy", "http://localhost:1"])
    assert "--no-config-locations" in seen[0]
    assert "--no-exec" in seen[0]
    assert seen[0][-3:] == ["--proxy", "http://localhost:1", "https://example.com/v"]


@pytest.mark.skipif(sys.platform == "win32", reason="process groups are POSIX-only")
def test_capture_honours_cancel() -> None:
    with pytest.raises(DownloadError) as caught:
        ytdlp._capture(
            [sys.executable, "-c", "import time; time.sleep(5)"],
            timeout=10,
            cancel_check=lambda: True,
        )
    assert caught.value.reason is ErrorReason.CANCELLED


@pytest.mark.skipif(sys.platform == "win32", reason="process groups are POSIX-only")
def test_capture_honours_timeout() -> None:
    with pytest.raises(DownloadError) as caught:
        ytdlp._capture(
            [sys.executable, "-c", "import time; time.sleep(5)"],
            timeout=0.2,
        )
    assert caught.value.reason is ErrorReason.NETWORK


def test_missing_ytdlp_is_typed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ytdlp, "_capture", lambda *args, **kwargs: (1, "", "no yt-dlp"))
    # Probe classifications still work without requiring a real binary.
    with pytest.raises(DownloadError):
        ytdlp.probe("https://example.com/v")
