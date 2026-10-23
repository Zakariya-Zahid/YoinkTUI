"""Clip/timecode contract tests."""

from __future__ import annotations

import pytest

from yoinktui.backend.ytdlp import (
    Section,
    format_timecode,
    parse_timecode,
    section_slug,
    section_spec,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("90", 90.0),
        ("90.5", 90.5),
        ("1:30", 90.0),
        ("01:02:03", 3723.0),
        ("1h2m3s", 3723.0),
        ("2m", 120.0),
        ("45s", 45.0),
        (" 1:30 ", 90.0),
    ],
)
def test_parse_timecode(text: str, expected: float) -> None:
    assert parse_timecode(text) == expected


@pytest.mark.parametrize("text", ["", "abc", "1:99", "1:2:99", "-5", "1h2x"])
def test_parse_timecode_rejects_invalid(text: str) -> None:
    with pytest.raises(ValueError):
        parse_timecode(text)


def test_format_timecode() -> None:
    assert format_timecode(None) == "—"
    assert format_timecode(0) == "00:00"
    assert format_timecode(65) == "01:05"
    assert format_timecode(3725) == "1:02:05"
    assert format_timecode(65, force_hours=True) == "0:01:05"
    assert format_timecode(-3) == "00:00"


def test_section_spec_and_slug() -> None:
    full_tail = Section(start=30, end=None)
    assert section_spec(full_tail) == "*00:00:30-"
    assert section_slug(full_tail) == "00-00-30_end"

    bounded = Section(start=30, end=90, precise=True)
    assert section_spec(bounded) == "*00:00:30-00:01:30"
    assert section_slug(bounded) == "00-00-30_00-01-30"


def test_section_spec_rejects_bad_ranges() -> None:
    with pytest.raises(ValueError):
        section_spec(Section(start=-1))
    with pytest.raises(ValueError):
        section_spec(Section(start=10, end=10))
