"""Tests for config loading, validation, precedence, and paths."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from yoinktui.backend.config import (
    AppConfig,
    ConfigError,
    config_dir,
    config_to_dict,
    data_dir,
    default_config_path,
    load_config,
    load_last_url,
    save_last_url,
    state_dir,
    to_toml,
    write_default_config,
)


def test_defaults() -> None:
    config = load_config(Path("/nonexistent/config.toml"), env={})
    assert config.quality_cap == 1080
    assert config.container == "mkv"
    assert config.audio_format == "mp3"
    assert config.concurrent_fragments == 0
    assert config.embed_metadata is True
    assert config.merge_format == "mkv"
    assert config.download_dir == Path.home() / "Videos" / "yoinktui"


def test_file_values(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        """
[general]
theme = "light"
default_mode = "audio"

[download]
dir = "~/Downloads/yoinks"
quality_cap = 720
container = "mp4"
audio_format = "m4a"
audio_quality = "2"
concurrent_fragments = 4
rate_limit = "5M"
write_subtitles = true
embed_metadata = false
embed_thumbnail = true
keep_original = true

[network]
proxy = "socks5://127.0.0.1:1080"
cookies_from_browser = "firefox"

[ui]
ascii = true
no_color = true
show_preview = false
""",
        encoding="utf-8",
    )
    config = load_config(path, env={})
    assert config.theme == "light"
    assert config.default_mode == "audio"
    assert config.download_dir == Path("~/Downloads/yoinks").expanduser()
    assert config.quality_cap == 720
    assert config.container == "mp4"
    assert config.audio_format == "m4a"
    assert config.audio_quality == "2"
    assert config.concurrent_fragments == 4
    assert config.rate_limit == "5M"
    assert config.write_subtitles is True
    assert config.embed_metadata is False
    assert config.embed_thumbnail is True
    assert config.keep_original is True
    assert config.proxy == "socks5://127.0.0.1:1080"
    assert config.cookies_from_browser == "firefox"
    assert config.ascii is True
    assert config.no_color is True
    assert config.show_preview is False
    assert config.ytdlp_args[:2] == ["--cookies-from-browser", "firefox"]


def test_precedence_file_then_env_then_cli(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text('[download]\nquality_cap = 720\ncontainer = "mkv"\n', encoding="utf-8")

    from_file = load_config(path, env={})
    assert from_file.quality_cap == 720

    from_env = load_config(path, env={"YOINKTUI_QUALITY_CAP": "480"})
    assert from_env.quality_cap == 480

    from_cli = load_config(
        path,
        env={"YOINKTUI_QUALITY_CAP": "480"},
        cli={"quality_cap": 360, "container": "mp4"},
    )
    assert from_cli.quality_cap == 360
    assert from_cli.container == "mp4"


def test_invalid_values_warn_and_fall_back(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        """
[download]
quality_cap = -1
container = "avi"
audio_format = "ogg"
rate_limit = "as fast as possible"
concurrent_fragments = -2
""",
        encoding="utf-8",
    )
    config = load_config(path, env={})
    assert config.quality_cap == 1080
    assert config.container == "mkv"
    assert config.audio_format == "mp3"
    assert config.rate_limit == ""
    assert config.concurrent_fragments == 0
    assert config.warnings


def test_unknown_options_warn(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("[download]\nnope = true\n", encoding="utf-8")
    config = load_config(path, env={})
    assert any("nope" in warning for warning in config.warnings)


def test_invalid_toml_never_crashes(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("[download\nquality_cap = 720\n", encoding="utf-8")
    config = load_config(path, env={})
    assert config.quality_cap == 1080
    assert any("Invalid TOML" in warning for warning in config.warnings)


def test_strict_mode_raises(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text('[download]\ncontainer = "avi"\n', encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(path, env={}, strict=True)


def test_toml_roundtrip_and_default_file(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "config.toml"
    written = write_default_config(target)
    assert written == target
    assert target.is_file()

    with pytest.raises(FileExistsError):
        write_default_config(target)

    parsed = tomllib.loads(target.read_text(encoding="utf-8"))
    assert parsed["download"]["quality_cap"] == 1080

    config = load_config(target, env={})
    reparsed = tomllib.loads(to_toml(config))
    assert reparsed["download"]["container"] == "mkv"
    assert config_to_dict(config)["general"]["theme"] == "dark"


def test_xdg_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    assert config_dir() == tmp_path / "cfg" / "yoinktui"
    assert default_config_path() == tmp_path / "cfg" / "yoinktui" / "config.toml"
    assert data_dir() == tmp_path / "data" / "yoinktui"
    assert state_dir() == tmp_path / "state" / "yoinktui"


def test_last_url_roundtrip(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    assert load_last_url() == ""
    save_last_url("https://example.com/watch?v=1")
    assert load_last_url() == "https://example.com/watch?v=1"


def test_appconfig_merge_format_auto() -> None:
    config = AppConfig(container="auto")
    assert config.merge_format == ""
    config.container = "mp4"
    assert config.merge_format == "mp4"
