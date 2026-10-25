"""Built-in download presets and the data type used by config/UI.

A preset is a small bundle of download policy values.  It is deliberately
separate from :class:`~yoinktui.backend.config.AppConfig`: presets are applied
to one download at a time from the format screen, while the config remains the
global default.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

PRESET_KEYS = (
    "mode",
    "quality_cap",
    "container",
    "audio_format",
    "audio_quality",
    "write_subtitles",
    "embed_metadata",
    "embed_thumbnail",
    "keep_original",
    "description",
)


@dataclass(frozen=True, slots=True)
class Preset:
    """A reusable bundle of download policy."""

    name: str
    mode: str = "video"
    quality_cap: int = 1080
    container: str = "mkv"
    audio_format: str = "mp3"
    audio_quality: str = "0"
    write_subtitles: bool = False
    embed_metadata: bool = True
    embed_thumbnail: bool = False
    keep_original: bool = False
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "quality_cap": self.quality_cap,
            "container": self.container,
            "audio_format": self.audio_format,
            "audio_quality": self.audio_quality,
            "write_subtitles": self.write_subtitles,
            "embed_metadata": self.embed_metadata,
            "embed_thumbnail": self.embed_thumbnail,
            "keep_original": self.keep_original,
            "description": self.description,
        }


def builtin_presets() -> dict[str, Preset]:
    """Fresh dict of the presets shipped with YoinkTUI."""
    return {
        "music": Preset(
            name="music",
            mode="audio",
            quality_cap=0,
            audio_format="mp3",
            embed_metadata=True,
            embed_thumbnail=True,
            description="Audio only, tagged and ready for a music player",
        ),
        "archive": Preset(
            name="archive",
            mode="video",
            quality_cap=0,
            container="mkv",
            write_subtitles=True,
            embed_metadata=True,
            embed_thumbnail=True,
            description="Best quality, lossless container, subtitles kept",
        ),
        "mobile": Preset(
            name="mobile",
            mode="video",
            quality_cap=720,
            container="mp4",
            audio_format="m4a",
            embed_metadata=True,
            description="720p MP4/AAC for phones and tablets",
        ),
    }


# A mutable-looking default is a common dataclass trap; config uses a factory.
DEFAULT_PRESETS: dict[str, Preset] = builtin_presets()


def preset_field_defaults(name: str) -> Preset:
    """Return a preset with only ``name`` filled in (used for user presets)."""
    return Preset(name=name)


__all__ = [
    "DEFAULT_PRESETS",
    "PRESET_KEYS",
    "Preset",
    "builtin_presets",
    "preset_field_defaults",
]
