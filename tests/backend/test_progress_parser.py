"""Tests for the yt-dlp progress-template parser contract."""

from __future__ import annotations

import pytest

from yoinktui.backend.ytdlp import _parse_line, _to_float


def test_parse_download_line_with_all_fields() -> None:
    event = _parse_line("DL|downloading|1024|2048|4096|512.5|3")
    assert event is not None
    assert event.kind == "download"
    assert event.status == "downloading"
    assert event.downloaded == 1024
    assert event.total == 2048
    assert event.speed == 512.5
    assert event.eta == 3


def test_parse_download_line_falls_back_to_estimate() -> None:
    event = _parse_line("DL|downloading|0|NA|1000|NA|NA")
    assert event is not None
    assert event.downloaded == 0
    assert event.total == 1000
    assert event.speed is None
    assert event.eta is None


def test_parse_download_line_prefers_exact_total() -> None:
    event = _parse_line("DL|downloading|10|2000|9999|50|10")
    assert event is not None
    assert event.total == 2000


def test_parse_download_line_zero_total_and_zero_speed() -> None:
    event = _parse_line("DL|downloading|0|0|0|0|0")
    assert event is not None
    assert event.downloaded == 0
    assert event.total is None
    assert event.speed == 0
    assert event.eta == 0


def test_parse_finished_line() -> None:
    event = _parse_line("DL|finished|2048|2048|NA|NA|NA")
    assert event is not None
    assert event.status == "finished"
    assert event.downloaded == 2048


def test_parse_short_download_line_is_ignored() -> None:
    assert _parse_line("DL|downloading") is None


def test_parse_postprocess_line() -> None:
    event = _parse_line("PP|started|Merger|/tmp/demo.mkv")
    assert event is not None
    assert event.kind == "postprocess"
    assert event.status == "started"
    assert event.section == "Merger"
    assert event.filename == "/tmp/demo.mkv"


def test_parse_final_line() -> None:
    event = _parse_line("FINAL|/tmp/demo.mkv")
    assert event is not None
    assert event.kind == "done"
    assert event.filename == "/tmp/demo.mkv"


def test_parse_log_and_blank_lines() -> None:
    event = _parse_line("[info] something")
    assert event is not None
    assert event.kind == "log"
    assert event.text == "[info] something"
    assert _parse_line("   ") is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("12", 12.0),
        ("12.5", 12.5),
        ("NA", None),
        ("", None),
        ("None", None),
        ("abc", None),
    ],
)
def test_to_float(raw: str, expected: float | None) -> None:
    assert _to_float(raw) == expected
