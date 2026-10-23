"""Tests for format selectors."""

from __future__ import annotations

from yoinktui.backend.models import FormatInfo
from yoinktui.backend.ytdlp import audio_selector, resolve_merge_format, video_selector


def test_explicit_format_wins() -> None:
    assert video_selector("137", 1080) == "137+ba/137/b"


def test_quality_cap_expression() -> None:
    assert video_selector(None, 720) == "bv*[height<=720]+ba/b[height<=720]/bv*+ba/b"


def test_best_when_no_cap() -> None:
    assert video_selector(None, None) == "bv*+ba/b"


def test_zero_cap_means_best() -> None:
    assert video_selector(None, 0) == "bv*+ba/b"


def test_audio_selector() -> None:
    assert audio_selector() == "ba/b/bv*"


def test_merge_format_prefers_mp4_for_mp4_aac_streams() -> None:
    video = FormatInfo(format_id="137", ext="mp4", vcodec="avc1.640028", acodec="none", height=1080)
    audio = FormatInfo(format_id="140", ext="m4a", vcodec="none", acodec="mp4a.40.2")
    assert resolve_merge_format("mkv", video, audio) == "mp4"


def test_merge_format_keeps_mkv_for_webm_opus_streams() -> None:
    video = FormatInfo(format_id="248", ext="webm", vcodec="vp9", acodec="none")
    audio = FormatInfo(format_id="251", ext="webm", vcodec="none", acodec="opus")
    assert resolve_merge_format("mkv", video, audio) == "mkv"


def test_merge_format_respects_explicit_preference() -> None:
    video = FormatInfo(format_id="137", ext="mp4", vcodec="avc1", acodec="none")
    audio = FormatInfo(format_id="140", ext="m4a", vcodec="none", acodec="mp4a")
    assert resolve_merge_format("mp4", video, audio) == "mp4"
    assert resolve_merge_format("", video, audio) == ""


def test_merge_format_no_video_returns_preference() -> None:
    assert resolve_merge_format("mkv", None, None) == "mkv"
