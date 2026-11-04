"""CLI surface tests: version, config actions, and doctor."""

from __future__ import annotations

from pathlib import Path

import pytest

from yoinktui import __version__
from yoinktui.__main__ import main
from yoinktui.backend.ytdlp import DependencyReport, DependencyStatus


@pytest.fixture(autouse=True)
def _isolate_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))


def test_version_flag(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])
    assert excinfo.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_print_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    assert main(["--print-config"]) == 0
    output = capsys.readouterr().out
    assert "[download]" in output
    assert "quality_cap = 1080" in output


def test_print_config_with_cookies_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    cookies = tmp_path / "cookies.txt"
    cookies.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")

    assert main(["--print-config", "--cookies", str(cookies)]) == 0
    output = capsys.readouterr().out
    assert f'cookies_file = "{cookies}"' in output


def test_print_config_with_impersonate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))

    assert main(["--print-config", "--impersonate", "chrome"]) == 0
    output = capsys.readouterr().out
    assert 'impersonate = "chrome"' in output


def test_write_default_config(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    target = tmp_path / "config.toml"
    assert main(["--config", str(target), "--write-default-config"]) == 0
    assert target.is_file()
    assert "Wrote" in capsys.readouterr().out

    # Never clobber an existing file.
    assert main(["--config", str(target), "--write-default-config"]) == 1
    assert "already exists" in capsys.readouterr().out


def test_doctor_reports_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    report = DependencyReport(
        (
            DependencyStatus("yt-dlp", "/usr/bin/yt-dlp", "2026.08.19", True),
            DependencyStatus("ffmpeg", "/usr/bin/ffmpeg", "7.1", True),
        )
    )
    monkeypatch.setattr("yoinktui.__main__.check_dependencies", lambda: report)
    config = tmp_path / "config.toml"
    download_dir = tmp_path / "downloads"
    config.write_text(f'[download]\ndir = "{download_dir}"\n', encoding="utf-8")

    assert main(["--config", str(config), "--doctor"]) == 0
    output = capsys.readouterr().out
    assert "yt-dlp" in output
    assert "download dir is writable" in output
    assert download_dir.is_dir()


def _mock_media_info(url: str = "https://example.com/watch?v=123", title: str = "Test Video"):
    from yoinktui.backend.models import FormatInfo, MediaInfo

    video_fmt = FormatInfo(
        format_id="137",
        ext="mp4",
        height=1080,
        fps=30,
        vcodec="avc1",
        acodec="none",
        filesize=10_000_000,
    )
    audio_fmt = FormatInfo(
        format_id="140",
        ext="m4a",
        height=0,
        fps=None,
        vcodec="none",
        acodec="mp4a",
        filesize=2_000_000,
    )
    return MediaInfo(
        id="123",
        title=title,
        uploader="Test Channel",
        channel="Test Channel",
        duration=120.0,
        webpage_url=url,
        video_formats=[video_fmt],
        audio_formats=[audio_fmt],
    )


def test_parse_playlist_items() -> None:
    from yoinktui.cli import parse_playlist_items

    assert parse_playlist_items("1,3,5") == [1, 3, 5]
    assert parse_playlist_items("1-3,5") == [1, 2, 3, 5]
    assert parse_playlist_items("-3", max_items=10) == [1, 2, 3]
    assert parse_playlist_items("8-", max_items=10) == [8, 9, 10]
    assert parse_playlist_items("2,2,3") == [2, 3]


def test_headless_dry_run(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from yoinktui import cli

    monkeypatch.setattr(cli, "probe", lambda url, **kw: _mock_media_info(url))
    assert main(["https://example.com/watch?v=123", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "[dry-run] URL:" in out
    assert "[dry-run] Title:    Test Video" in out
    assert "https://example.com/watch?v=123" in out


def test_headless_print_command(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from yoinktui import cli

    monkeypatch.setattr(cli, "probe", lambda url, **kw: _mock_media_info(url))
    assert main(["https://example.com/watch?v=123", "--dry-run", "--print-command"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("yt-dlp ")
    assert "https://example.com/watch?v=123" in out


def test_headless_format_and_mode_overrides(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from yoinktui import cli

    monkeypatch.setattr(cli, "probe", lambda url, **kw: _mock_media_info(url))
    assert (
        main(
            [
                "https://example.com/watch?v=123",
                "--dry-run",
                "-f",
                "custom_fmt",
                "-m",
                "audio",
                "--output-template",
                "/tmp/%(id)s.%(ext)s",
            ]
        )
        == 0
    )
    out = capsys.readouterr().out
    assert "[dry-run] Format:   custom_fmt" in out
    assert "[dry-run] Output:   /tmp/%(id)s.%(ext)s" in out


def test_headless_preset_applied(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from yoinktui import cli

    monkeypatch.setattr(cli, "probe", lambda url, **kw: _mock_media_info(url))
    assert (
        main(
            [
                "https://example.com/watch?v=123",
                "--dry-run",
                "--preset",
                "music",
                "--print-command",
            ]
        )
        == 0
    )
    out = capsys.readouterr().out
    assert "-x" in out
    assert "--audio-format" in out
    assert "mp3" in out


def test_headless_unknown_preset(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["https://example.com/watch?v=123", "--preset", "unknown_preset_xyz"]) == 2
    err = capsys.readouterr().err
    assert "Unknown preset 'unknown_preset_xyz'" in err


def test_headless_json_stream(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import json

    from yoinktui import cli
    from yoinktui.backend.ytdlp import ProgressEvent

    monkeypatch.setattr(cli, "probe", lambda url, **kw: _mock_media_info(url))

    def _fake_download(url, **kw):
        yield ProgressEvent(
            kind="download",
            status="downloading",
            downloaded=500,
            total=1000,
            speed=100,
            eta=5,
        )
        yield ProgressEvent(kind="done", filename="/tmp/out.mkv")

    monkeypatch.setattr(cli, "download", _fake_download)

    assert main(["https://example.com/watch?v=123", "--json", "--no-history"]) == 0
    lines = [json.loads(line) for line in capsys.readouterr().out.strip().splitlines()]
    events = [item["event"] for item in lines]
    assert "start" in events
    assert "download" in events
    assert "done" in events
    done_ev = next(ev for ev in lines if ev["event"] == "done")
    assert done_ev["path"] == "/tmp/out.mkv"


def test_headless_quiet_mode(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from yoinktui import cli
    from yoinktui.backend.ytdlp import ProgressEvent

    monkeypatch.setattr(cli, "probe", lambda url, **kw: _mock_media_info(url))
    monkeypatch.setattr(
        cli,
        "download",
        lambda url, **kw: iter([ProgressEvent(kind="done", filename="/tmp/out.mkv")]),
    )

    assert main(["https://example.com/watch?v=123", "-q", "--no-history"]) == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_headless_batch_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from yoinktui import cli

    batch = tmp_path / "urls.txt"
    batch.write_text(
        "# comment\nhttps://example.com/v1\n\nhttps://example.com/v2\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(cli, "probe", lambda url, **kw: _mock_media_info(url, title=f"Title {url}"))

    assert main(["--batch-file", str(batch), "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "Title https://example.com/v1" in out
    assert "Title https://example.com/v2" in out


def test_headless_playlist_expansion(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from yoinktui import cli
    from yoinktui.backend.ytdlp import PlaylistEntry, PlaylistInfo

    entries = [
        PlaylistEntry(url="https://example.com/v1", title="Episode 1", id="1"),
        PlaylistEntry(url="https://example.com/v2", title="Episode 2", id="2"),
        PlaylistEntry(url="https://example.com/v3", title="Episode 3", id="3"),
    ]
    monkeypatch.setattr(
        cli,
        "probe_playlist",
        lambda url, **kw: PlaylistInfo(title="Series", entries=entries),
    )

    # Filter with --playlist-items 1,3
    assert (
        main(
            [
                "https://example.com/playlist",
                "--yes-playlist",
                "--playlist-items",
                "1,3",
                "--dry-run",
            ]
        )
        == 0
    )
    out = capsys.readouterr().out
    assert "Episode 1" in out
    assert "Episode 3" in out
    assert "Episode 2" not in out


def test_headless_exit_codes(monkeypatch: pytest.MonkeyPatch) -> None:
    from yoinktui import cli
    from yoinktui.backend.errors import DownloadError, ErrorReason

    # Network error -> 10
    monkeypatch.setattr(
        cli,
        "probe",
        lambda *args, **kw: (_ for _ in ()).throw(DownloadError("net down", ErrorReason.NETWORK)),
    )
    assert main(["https://example.com/v", "--dry-run"]) == 10

    # Auth error -> 11
    monkeypatch.setattr(
        cli,
        "probe",
        lambda *args, **kw: (_ for _ in ()).throw(DownloadError("403", ErrorReason.AUTH)),
    )
    assert main(["https://example.com/v", "--dry-run"]) == 11

    # Not found -> 13
    monkeypatch.setattr(
        cli,
        "probe",
        lambda *args, **kw: (_ for _ in ()).throw(DownloadError("404", ErrorReason.NOT_FOUND)),
    )
    assert main(["https://example.com/v", "--dry-run"]) == 13

    # Geo blocked -> 12
    monkeypatch.setattr(
        cli,
        "probe",
        lambda *args, **kw: (_ for _ in ()).throw(DownloadError("geo", ErrorReason.GEO)),
    )
    assert main(["https://example.com/v", "--dry-run"]) == 12

    # Unsupported -> 16
    monkeypatch.setattr(
        cli,
        "probe",
        lambda *args, **kw: (_ for _ in ()).throw(DownloadError("unsup", ErrorReason.UNSUPPORTED)),
    )
    assert main(["https://example.com/v", "--dry-run"]) == 16

    # Cancelled -> 130
    monkeypatch.setattr(
        cli,
        "probe",
        lambda *args, **kw: (_ for _ in ()).throw(KeyboardInterrupt()),
    )
    assert main(["https://example.com/v", "--dry-run"]) == 130
