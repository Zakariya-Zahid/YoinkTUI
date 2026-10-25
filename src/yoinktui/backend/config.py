"""Configuration schema, loading, and precedence for YoinkTUI.

Precedence (highest wins)::

    CLI flags  >  environment variables  >  config.toml  >  built-in defaults

The config file lives at ``$XDG_CONFIG_HOME/yoinktui/config.toml`` (usually
``~/.config/yoinktui/config.toml``).  A small state file under
``$XDG_STATE_HOME/yoinktui/state.json`` remembers the last URL between runs
until the history module (08) grows a real store.
"""

from __future__ import annotations

import json
import os
import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from yoinktui.backend.presets import PRESET_KEYS, Preset, builtin_presets

APP_NAME = "yoinktui"

CONTAINERS = ("mkv", "mp4", "auto")
AUDIO_FORMATS = ("mp3", "m4a", "opus", "flac", "best")
MODES = ("video", "vonly", "audio")

_RATE_LIMIT = re.compile(r"^\d+(?:\.\d+)?[KMGkmg]?$")


class ConfigError(ValueError):
    """Raised when a configuration value cannot be used."""


def _xdg_dir(env_var: str, fallback: Path) -> Path:
    value = os.environ.get(env_var)
    return Path(value).expanduser() if value else fallback


def config_dir() -> Path:
    """Directory that holds ``config.toml``."""
    return _xdg_dir("XDG_CONFIG_HOME", Path.home() / ".config") / APP_NAME


def data_dir() -> Path:
    """Directory for durable app data (history, library, ...)."""
    return _xdg_dir("XDG_DATA_HOME", Path.home() / ".local" / "share") / APP_NAME


def state_dir() -> Path:
    """Directory for small, disposable UI state."""
    return _xdg_dir("XDG_STATE_HOME", Path.home() / ".local" / "state") / APP_NAME


def default_config_path() -> Path:
    return config_dir() / "config.toml"


def default_download_dir() -> Path:
    return Path.home() / "Videos" / APP_NAME


def state_file() -> Path:
    return state_dir() / "state.json"


@dataclass(slots=True)
class AppConfig:
    """Effective configuration for one app instance.

    ``warnings`` collects non-fatal problems found while loading so the app
    can surface them without crashing (module 07 robustness rule).
    """

    # [general]
    theme: str = "dark"
    default_mode: str = "video"
    confirm_quit: bool = True

    # [download]
    download_dir: Path = field(default_factory=default_download_dir)
    quality_cap: int = 1080  # 0 = best
    container: str = "mkv"
    audio_format: str = "mp3"
    audio_quality: str = "0"
    concurrent_fragments: int = 0  # 0 = leave yt-dlp's default alone
    rate_limit: str = ""
    write_subtitles: bool = False
    embed_metadata: bool = True
    embed_thumbnail: bool = False
    keep_original: bool = False

    # [network]
    proxy: str | None = None
    cookies_from_browser: str | None = None
    extra_args: tuple[str, ...] = ()

    # [ui]
    ascii: bool = False
    no_color: bool = False
    show_preview: bool = True

    # [presets.<name>] — built-ins are merged with user-defined overrides.
    presets: dict[str, Preset] = field(default_factory=builtin_presets)

    warnings: list[str] = field(default_factory=list, repr=False)

    @property
    def ytdlp_args(self) -> list[str]:
        """Extra yt-dlp flags shared by probe and download."""
        args: list[str] = []
        if self.cookies_from_browser:
            args += ["--cookies-from-browser", self.cookies_from_browser]
        if self.proxy:
            args += ["--proxy", self.proxy]
        args += list(self.extra_args)
        return args

    @property
    def merge_format(self) -> str:
        """``--merge-output-format`` value; empty means "let yt-dlp choose"."""
        return "" if self.container == "auto" else self.container


@dataclass(frozen=True, slots=True)
class _Setter:
    section: str
    key: str
    attr: str
    kind: type


_FILE_SETTERS: tuple[_Setter, ...] = (
    _Setter("general", "theme", "theme", str),
    _Setter("general", "default_mode", "default_mode", str),
    _Setter("general", "confirm_quit", "confirm_quit", bool),
    _Setter("download", "dir", "download_dir", Path),
    _Setter("download", "quality_cap", "quality_cap", int),
    _Setter("download", "container", "container", str),
    _Setter("download", "audio_format", "audio_format", str),
    _Setter("download", "audio_quality", "audio_quality", str),
    _Setter("download", "concurrent_fragments", "concurrent_fragments", int),
    _Setter("download", "rate_limit", "rate_limit", str),
    _Setter("download", "write_subtitles", "write_subtitles", bool),
    _Setter("download", "embed_metadata", "embed_metadata", bool),
    _Setter("download", "embed_thumbnail", "embed_thumbnail", bool),
    _Setter("download", "keep_original", "keep_original", bool),
    _Setter("network", "proxy", "proxy", str),
    _Setter("network", "cookies_from_browser", "cookies_from_browser", str),
    _Setter("ui", "ascii", "ascii", bool),
    _Setter("ui", "no_color", "no_color", bool),
    _Setter("ui", "show_preview", "show_preview", bool),
)

_ENV_SETTERS: dict[str, tuple[str, type]] = {
    "YOINKTUI_THEME": ("theme", str),
    "YOINKTUI_DEFAULT_MODE": ("default_mode", str),
    "YOINKTUI_CONFIRM_QUIT": ("confirm_quit", bool),
    "YOINKTUI_DOWNLOAD_DIR": ("download_dir", Path),
    "YOINKTUI_QUALITY_CAP": ("quality_cap", int),
    "YOINKTUI_CONTAINER": ("container", str),
    "YOINKTUI_AUDIO_FORMAT": ("audio_format", str),
    "YOINKTUI_AUDIO_QUALITY": ("audio_quality", str),
    "YOINKTUI_CONCURRENT_FRAGMENTS": ("concurrent_fragments", int),
    "YOINKTUI_RATE_LIMIT": ("rate_limit", str),
    "YOINKTUI_WRITE_SUBTITLES": ("write_subtitles", bool),
    "YOINKTUI_EMBED_METADATA": ("embed_metadata", bool),
    "YOINKTUI_EMBED_THUMBNAIL": ("embed_thumbnail", bool),
    "YOINKTUI_KEEP_ORIGINAL": ("keep_original", bool),
    "YOINKTUI_PROXY": ("proxy", str),
    "YOINKTUI_COOKIES_FROM_BROWSER": ("cookies_from_browser", str),
    "YOINKTUI_ASCII": ("ascii", bool),
    "YOINKTUI_NO_COLOR": ("no_color", bool),
    "YOINKTUI_SHOW_PREVIEW": ("show_preview", bool),
}


def _coerce(value: Any, kind: type, label: str, warnings: list[str]) -> Any:
    """Best-effort coercion; invalid values append a warning and return None."""
    if value is None:
        return None
    if kind is bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            low = value.strip().lower()
            if low in ("1", "true", "yes", "on"):
                return True
            if low in ("0", "false", "no", "off"):
                return False
        warnings.append(f"{label}: expected true/false, got {value!r}; keeping default")
        return None
    if kind is int:
        if isinstance(value, bool):
            warnings.append(f"{label}: expected a number, got {value!r}; keeping default")
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            warnings.append(f"{label}: expected a number, got {value!r}; keeping default")
            return None
    if kind is Path:
        if not isinstance(value, (str, os.PathLike)):
            warnings.append(f"{label}: expected a path, got {value!r}; keeping default")
            return None
        text = str(value).strip()
        return Path(text).expanduser() if text else None
    # str
    if isinstance(value, str):
        return value.strip()
    warnings.append(f"{label}: expected text, got {value!r}; keeping default")
    return None


def _apply_section(
    config: AppConfig,
    section: str,
    data: Any,
    warnings: list[str],
    *,
    strict: bool,
    source: str,
) -> None:
    if data is None:
        return
    if not isinstance(data, Mapping):
        message = f"{source}: [{section}] must be a table"
        if strict:
            raise ConfigError(message)
        warnings.append(message)
        return

    known = {setter.key for setter in _FILE_SETTERS if setter.section == section}
    for key in data:
        if key not in known:
            message = f"{source}: unknown option [{section}].{key}"
            if strict:
                raise ConfigError(message)
            warnings.append(message)

    for setter in _FILE_SETTERS:
        if setter.section != section or setter.key not in data:
            continue
        coerced = _coerce(
            data[setter.key],
            setter.kind,
            f"[{section}].{setter.key}",
            warnings,
        )
        if coerced is not None:
            setattr(config, setter.attr, coerced)


def _apply_presets(
    config: AppConfig,
    data: Any,
    warnings: list[str],
    *,
    strict: bool,
    source: str,
) -> None:
    """Merge ``[presets.<name>]`` tables over the shipped built-ins."""
    if data is None:
        return
    if not isinstance(data, Mapping):
        message = f"{source}: [presets] must be a table of named tables"
        if strict:
            raise ConfigError(message)
        warnings.append(message)
        return

    kinds: dict[str, type] = {
        "mode": str,
        "quality_cap": int,
        "container": str,
        "audio_format": str,
        "audio_quality": str,
        "write_subtitles": bool,
        "embed_metadata": bool,
        "embed_thumbnail": bool,
        "keep_original": bool,
        "description": str,
    }
    for raw_name, raw_values in data.items():
        name = str(raw_name).strip()
        if not name:
            message = f"{source}: preset names cannot be empty"
            if strict:
                raise ConfigError(message)
            warnings.append(message)
            continue
        if not isinstance(raw_values, Mapping):
            message = f"{source}: [presets.{name}] must be a table"
            if strict:
                raise ConfigError(message)
            warnings.append(message)
            continue

        base = config.presets.get(name) or Preset(name=name)
        values = base.to_dict()
        for key in raw_values:
            if key not in PRESET_KEYS:
                message = f"{source}: unknown option [presets.{name}].{key}"
                if strict:
                    raise ConfigError(message)
                warnings.append(message)

        for key, kind in kinds.items():
            if key not in raw_values:
                continue
            coerced = _coerce(
                raw_values[key],
                kind,
                f"[presets.{name}].{key}",
                warnings,
            )
            if coerced is not None:
                values[key] = coerced

        if values["mode"] not in MODES:
            message = f"[presets.{name}].mode must be one of {', '.join(MODES)}; ignoring"
            if strict:
                raise ConfigError(message)
            warnings.append(message)
            values["mode"] = base.mode
        if values["container"] not in CONTAINERS:
            message = f"[presets.{name}].container must be one of {', '.join(CONTAINERS)}; ignoring"
            if strict:
                raise ConfigError(message)
            warnings.append(message)
            values["container"] = base.container
        if values["audio_format"] not in AUDIO_FORMATS:
            message = (
                f"[presets.{name}].audio_format must be one of {', '.join(AUDIO_FORMATS)}; ignoring"
            )
            if strict:
                raise ConfigError(message)
            warnings.append(message)
            values["audio_format"] = base.audio_format
        if values["quality_cap"] < 0:
            message = f"[presets.{name}].quality_cap must be >= 0; ignoring"
            if strict:
                raise ConfigError(message)
            warnings.append(message)
            values["quality_cap"] = base.quality_cap

        config.presets[name] = Preset(name=name, **values)


def _apply_env(config: AppConfig, env: Mapping[str, str], warnings: list[str]) -> None:
    for env_name, (attr, kind) in _ENV_SETTERS.items():
        if env_name not in env:
            continue
        coerced = _coerce(env[env_name], kind, env_name, warnings)
        if coerced is not None:
            setattr(config, attr, coerced)


def _apply_cli(config: AppConfig, overrides: Mapping[str, Any], warnings: list[str]) -> None:
    for attr, value in overrides.items():
        if value is None or not hasattr(config, attr):
            continue
        setattr(config, attr, value)
        # Coerce strings that argparse kept as text for convenience.
        if attr == "download_dir" and isinstance(value, str):
            config.download_dir = Path(value).expanduser()
        elif attr in ("quality_cap", "concurrent_fragments") and isinstance(value, str):
            try:
                setattr(config, attr, int(value))
            except ValueError:
                warnings.append(f"--{attr.replace('_', '-')}: expected a number; keeping default")


def _validate(config: AppConfig, warnings: list[str], *, strict: bool) -> None:
    def fallback(message: str, attr: str, value: Any) -> None:
        if strict:
            raise ConfigError(message)
        warnings.append(message)
        setattr(config, attr, value)

    if config.quality_cap < 0:
        fallback("quality_cap must be >= 0 (0 = best); using 1080", "quality_cap", 1080)

    config.container = config.container.lower()
    if config.container not in CONTAINERS:
        fallback(
            f"container must be one of {', '.join(CONTAINERS)}; using mkv",
            "container",
            "mkv",
        )

    config.audio_format = config.audio_format.lower()
    if config.audio_format not in AUDIO_FORMATS:
        fallback(
            f"audio_format must be one of {', '.join(AUDIO_FORMATS)}; using mp3",
            "audio_format",
            "mp3",
        )

    config.default_mode = config.default_mode.lower()
    if config.default_mode not in MODES:
        fallback(
            f"default_mode must be one of {', '.join(MODES)}; using video",
            "default_mode",
            "video",
        )

    if config.concurrent_fragments < 0:
        fallback(
            "concurrent_fragments must be >= 0; using 0",
            "concurrent_fragments",
            0,
        )

    config.rate_limit = config.rate_limit.strip()
    if config.rate_limit and not _RATE_LIMIT.fullmatch(config.rate_limit):
        fallback(
            f"rate_limit {config.rate_limit!r} is not a yt-dlp rate (e.g. 5M); ignoring",
            "rate_limit",
            "",
        )

    config.download_dir = Path(config.download_dir).expanduser()


def load_config(
    path: Path | None = None,
    *,
    env: Mapping[str, str] | None = None,
    cli: Mapping[str, Any] | None = None,
    strict: bool = False,
) -> AppConfig:
    """Load configuration and apply file, environment, and CLI precedence.

    With ``strict=True`` invalid values raise :class:`ConfigError`; otherwise
    they produce a warning and the default is kept (the app must never crash
    because of a bad config file).
    """
    config = AppConfig()
    warnings: list[str] = []
    config_path = Path(path).expanduser() if path is not None else default_config_path()

    raw: dict[str, Any] = {}
    if config_path.is_file():
        try:
            raw = tomllib.loads(config_path.read_text(encoding="utf-8"))
        except OSError as exc:
            message = f"Could not read {config_path}: {exc}"
            if strict:
                raise ConfigError(message) from exc
            warnings.append(message)
        except tomllib.TOMLDecodeError as exc:
            message = f"Invalid TOML in {config_path}: {exc}"
            if strict:
                raise ConfigError(message) from exc
            warnings.append(message)

    for section in ("general", "download", "network", "ui"):
        _apply_section(
            config,
            section,
            raw.get(section),
            warnings,
            strict=strict,
            source=str(config_path),
        )
    _apply_presets(
        config,
        raw.get("presets"),
        warnings,
        strict=strict,
        source=str(config_path),
    )

    _apply_env(config, os.environ if env is None else env, warnings)
    _apply_cli(config, cli or {}, warnings)
    _validate(config, warnings, strict=strict)

    config.warnings = warnings
    return config


def config_to_dict(config: AppConfig) -> dict[str, Any]:
    """Nested, JSON-friendly representation used by ``--print-config``."""
    return {
        "general": {
            "theme": config.theme,
            "default_mode": config.default_mode,
            "confirm_quit": config.confirm_quit,
        },
        "download": {
            "dir": str(config.download_dir),
            "quality_cap": config.quality_cap,
            "container": config.container,
            "audio_format": config.audio_format,
            "audio_quality": config.audio_quality,
            "concurrent_fragments": config.concurrent_fragments,
            "rate_limit": config.rate_limit,
            "write_subtitles": config.write_subtitles,
            "embed_metadata": config.embed_metadata,
            "embed_thumbnail": config.embed_thumbnail,
            "keep_original": config.keep_original,
        },
        "network": {
            "proxy": config.proxy or "",
            "cookies_from_browser": config.cookies_from_browser or "",
        },
        "ui": {
            "ascii": config.ascii,
            "no_color": config.no_color,
            "show_preview": config.show_preview,
        },
        "presets": {name: preset.to_dict() for name, preset in config.presets.items()},
    }


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Path):
        return json.dumps(str(value))
    if isinstance(value, str):
        return json.dumps(value)
    return str(value)


def to_toml(config: AppConfig) -> str:
    """Serialise the effective config as a TOML document."""
    data = config_to_dict(config)
    lines: list[str] = []
    for section, values in data.items():
        if section == "presets":
            for name, preset_values in values.items():
                lines.append(f"[presets.{name}]")
                for key, value in preset_values.items():
                    lines.append(f"{key} = {_toml_value(value)}")
                lines.append("")
            continue
        lines.append(f"[{section}]")
        for key, value in values.items():
            lines.append(f"{key} = {_toml_value(value)}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_default_config(path: Path | None = None, *, overwrite: bool = False) -> Path:
    """Write a commented default config file and return its path."""
    target = Path(path).expanduser() if path is not None else default_config_path()
    if target.exists() and not overwrite:
        raise FileExistsError(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "# YoinkTUI configuration\n"
        "# Precedence: CLI flags > environment variables > this file > defaults.\n"
        "# Environment overrides use the YOINKTUI_ prefix, e.g. YOINKTUI_QUALITY_CAP=720.\n\n"
    )
    target.write_text(header + to_toml(AppConfig()), encoding="utf-8")
    return target


def load_last_url() -> str:
    """Return the last probed URL, or an empty string."""
    try:
        data = json.loads(state_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    if not isinstance(data, dict):
        return ""
    return str(data.get("last_url", ""))


def save_last_url(url: str) -> None:
    """Remember the last probed URL for the next launch (best effort)."""
    path = state_file()
    data: dict[str, Any] = {}
    try:
        existing = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(existing, dict):
            data = existing
    except (OSError, ValueError):
        data = {}
    data["last_url"] = url
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass
