"""Built-in presets and user-defined preset config."""

from __future__ import annotations

from pathlib import Path

import pytest

from yoinktui.backend.config import AppConfig, ConfigError, config_to_dict, load_config, to_toml
from yoinktui.backend.presets import Preset, builtin_presets


def test_builtin_presets_are_available_and_isolated() -> None:
    first = builtin_presets()
    second = builtin_presets()
    assert {"music", "archive", "mobile"} <= set(first)
    first["music"] = Preset(name="changed")
    assert second["music"].mode == "audio"


def test_user_preset_overrides_builtin(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        """
[presets.music]
quality_cap = 480
audio_format = "opus"
description = "small audio"

[presets.phone]
mode = "video"
quality_cap = 720
container = "mp4"
""",
        encoding="utf-8",
    )
    config = load_config(path, env={})
    assert config.presets["music"].quality_cap == 480
    assert config.presets["music"].audio_format == "opus"
    assert config.presets["music"].mode == "audio"
    assert config.presets["phone"].container == "mp4"


def test_invalid_preset_warns_or_raises(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        """
[presets.bad]
mode = "nope"
quality_cap = -2
""",
        encoding="utf-8",
    )
    config = load_config(path, env={})
    assert config.presets["bad"].mode == "video"
    assert config.presets["bad"].quality_cap == 1080
    assert config.warnings

    with pytest.raises(ConfigError):
        load_config(path, env={}, strict=True)


def test_toml_roundtrip_includes_presets(tmp_path: Path) -> None:
    config = AppConfig()
    text = to_toml(config)
    assert "[presets.music]" in text
    assert "[presets.archive]" in text
    path = tmp_path / "roundtrip.toml"
    path.write_text(text, encoding="utf-8")
    loaded = load_config(path, env={})
    assert loaded.presets["mobile"].quality_cap == config.presets["mobile"].quality_cap
    assert config_to_dict(config)["presets"]["music"]["mode"] == "audio"
