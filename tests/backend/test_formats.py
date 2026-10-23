"""Tests for metadata coercion and display labels."""

from __future__ import annotations

import math

from yoinktui.backend.models import FormatInfo, MediaInfo, _num


def test_num_rejects_na_none_bool_and_non_finite() -> None:
    assert _num("NA") is None
    assert _num(None) is None
    assert _num(True) is None
    assert _num(float("nan")) is None
    assert _num(float("inf")) is None
    assert _num("12.5") == 12.5
    assert _num(0) == 0.0


def _raw_info() -> dict:
    return {
        "id": "abc123",
        "title": "Demo video",
        "uploader": "Zak",
        "duration": 125,
        "upload_date": "20261023",
        "is_live": False,
        "thumbnail": "https://example.com/thumb.jpg",
        "webpage_url": "https://example.com/watch?v=abc123",
        "formats": [
            {
                "format_id": "137",
                "ext": "mp4",
                "vcodec": "avc1.640028",
                "acodec": "none",
                "width": "1920",
                "height": "1080",
                "fps": "NA",
                "tbr": "4000",
                "filesize": 10_000_000,
            },
            {
                "format_id": "140",
                "ext": "m4a",
                "vcodec": "none",
                "acodec": "mp4a.40.2",
                "abr": 128,
                "filesize_approx": 2_000_000,
            },
            {"format_id": "sb0", "ext": "mhtml", "format_note": "storyboard"},
            {"format_id": "bad", "vcodec": "avc1", "height": "NA"},
            None,
        ],
    }


def test_media_info_from_dict_coerces_and_classifies_formats() -> None:
    info = MediaInfo.from_dict(_raw_info())
    assert info.id == "abc123"
    assert info.title == "Demo video"
    assert info.display_channel == "Zak"
    assert info.thumbnail_url == "https://example.com/thumb.jpg"
    assert len(info.video_formats) == 1
    assert len(info.audio_formats) == 1
    video = info.video_formats[0]
    assert video.format_id == "137"
    assert video.width == 1920
    assert video.height == 1080
    assert video.fps is None
    assert video.size == 10_000_000


def test_media_info_handles_missing_or_malformed_formats() -> None:
    info = MediaInfo.from_dict({"title": "x", "formats": None})
    assert info.video_formats == []
    assert info.audio_formats == []
    assert info.max_video_height == 0


def test_media_info_display_labels() -> None:
    info = MediaInfo.from_dict(_raw_info())
    assert info.duration_label == "2:05"
    assert info.upload_date_label == "2026-10-23"
    assert info.live_label == ""

    live = MediaInfo.from_dict({"title": "live", "is_live": True, "duration": 3725})
    assert live.live_label == "LIVE"
    assert live.duration_label == "1:02:05"


def test_media_info_unknown_labels() -> None:
    info = MediaInfo.from_dict({})
    assert info.duration_label == "—"
    assert info.upload_date_label == "—"


def test_format_info_labels_and_fallbacks() -> None:
    fmt = FormatInfo.from_dict(
        {
            "format_id": "22",
            "ext": "mp4",
            "vcodec": "avc1",
            "acodec": "mp4a",
            "width": 1280,
            "height": 720,
            "fps": 30,
            "tbr": 2500,
            "filesize_approx": 5_000_000,
            "resolution": "1280x720",
        }
    )
    assert fmt.has_video is True
    assert fmt.has_audio is True
    assert fmt.size == 5_000_000
    assert "720p" in fmt.label
    assert fmt.resolution == "720p"
    assert fmt.codec_label == "avc1"
    assert fmt.fps_label == "30"


def test_format_info_ignores_non_finite_size() -> None:
    fmt = FormatInfo.from_dict({"format_id": "x", "vcodec": "avc1", "filesize": math.inf})
    assert fmt.size is None
