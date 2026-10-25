"""Flat playlist probing and entry normalization."""

from __future__ import annotations

import json

import pytest

from yoinktui.backend import ytdlp
from yoinktui.backend.errors import DownloadError, ErrorReason


def _payload() -> str:
    return json.dumps(
        {
            "_type": "playlist",
            "title": "Demo playlist",
            "entries": [
                {
                    "id": "one",
                    "title": "Episode One",
                    "url": "https://example.com/watch?v=one",
                    "uploader": "Channel",
                    "duration": 125,
                },
                {
                    "id": "two",
                    "title": "Episode Two",
                    "webpage_url": "https://example.com/watch?v=two",
                    "channel": "Channel",
                },
            ],
        }
    )


def test_probe_playlist_parses_flat_entries(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ytdlp, "_capture", lambda *args, **kwargs: (0, _payload(), ""))
    playlist = ytdlp.probe_playlist("https://example.com/playlist")
    assert playlist.title == "Demo playlist"
    assert [entry.title for entry in playlist.entries] == ["Episode One", "Episode Two"]
    assert playlist.entries[0].duration == 125
    assert playlist.entries[1].url.endswith("two")
    assert playlist.entries[1].uploader == "Channel"


def test_probe_playlist_builds_youtube_url_from_id(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = json.dumps({"title": "P", "entries": [{"id": "abc", "title": "Only ID"}]})
    monkeypatch.setattr(ytdlp, "_capture", lambda *args, **kwargs: (0, payload, ""))
    playlist = ytdlp.probe_playlist("https://example.com/playlist")
    assert playlist.entries[0].url == "https://www.youtube.com/watch?v=abc"


def test_probe_playlist_raises_for_non_playlist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ytdlp, "_capture", lambda *args, **kwargs: (0, "{}", ""))
    with pytest.raises(DownloadError) as excinfo:
        ytdlp.probe_playlist("https://example.com/v")
    assert excinfo.value.reason == ErrorReason.NO_STREAMS


def test_probe_playlist_surfaces_ytdlp_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        ytdlp,
        "_capture",
        lambda *args, **kwargs: (1, "", "ERROR: This playlist is private"),
    )
    with pytest.raises(DownloadError):
        ytdlp.probe_playlist("https://example.com/playlist")
