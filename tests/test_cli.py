"""CLI surface tests: version, config actions, and doctor."""

from __future__ import annotations

from pathlib import Path

import pytest

from yoinktui import __version__
from yoinktui.__main__ import main
from yoinktui.backend.ytdlp import DependencyReport, DependencyStatus


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
