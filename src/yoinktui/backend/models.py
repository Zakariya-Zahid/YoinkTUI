"""Domain models for probed media and its available formats."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _num(value: Any) -> float | None:
    """Coerce yt-dlp's occasionally-``None``/``"NA"`` numerics to float."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


@dataclass(slots=True)
class FormatInfo:
    """One selectable stream from yt-dlp's format list."""

    format_id: str
    ext: str = ""
    vcodec: str = "none"
    acodec: str = "none"
    width: int | None = None
    height: int | None = None
    fps: float | None = None
    tbr: float | None = None
    vbr: float | None = None
    abr: float | None = None
    filesize: float | None = None
    filesize_approx: float | None = None
    format_note: str = ""
    dynamic_range: str = ""
    protocol: str = ""
    language: str = ""
    quality: float | None = None

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> FormatInfo:
        return cls(
            format_id=_text(raw.get("format_id")),
            ext=_text(raw.get("ext")),
            vcodec=_text(raw.get("vcodec")) or "none",
            acodec=_text(raw.get("acodec")) or "none",
            width=int(raw["width"]) if _num(raw.get("width")) else None,
            height=int(raw["height"]) if _num(raw.get("height")) else None,
            fps=_num(raw.get("fps")),
            tbr=_num(raw.get("tbr")),
            vbr=_num(raw.get("vbr")),
            abr=_num(raw.get("abr")),
            filesize=_num(raw.get("filesize")),
            filesize_approx=_num(raw.get("filesize_approx")),
            format_note=_text(raw.get("format_note")),
            dynamic_range=_text(raw.get("dynamic_range")),
            protocol=_text(raw.get("protocol")),
            language=_text(raw.get("language")),
            quality=_num(raw.get("quality")),
        )

    @property
    def has_video(self) -> bool:
        return self.vcodec not in ("", "none")

    @property
    def has_audio(self) -> bool:
        return self.acodec not in ("", "none")

    @property
    def is_storyboard(self) -> bool:
        return self.ext == "mhtml" or self.format_note == "storyboard"

    @property
    def size(self) -> float | None:
        """Best available size estimate in bytes."""
        return self.filesize or self.filesize_approx

    @property
    def codec_label(self) -> str:
        """Short human codec name (``avc1.640028`` -> ``avc1``)."""
        for codec in (self.vcodec, self.acodec):
            if codec and codec != "none":
                return codec.split(".")[0]
        return "-"

    @property
    def resolution(self) -> str:
        if self.height:
            return f"{self.height}p"
        return "-"

    @property
    def fps_label(self) -> str:
        if self.fps and self.fps > 1:
            return f"{int(round(self.fps))}"
        return "-"

    @property
    def label(self) -> str:
        """Human label used in the picker."""
        if self.has_video and self.height:
            fps = f"{int(round(self.fps))}fps" if self.fps and self.fps > 1 else ""
            return f"{self.height}p {fps} {self.codec_label} {self.ext}".strip()
        if self.has_audio:
            return f"{self.codec_label} {self.ext}".strip()
        return self.format_id


@dataclass(slots=True)
class MediaInfo:
    """Everything we know about a probed URL."""

    id: str = ""
    title: str = ""
    uploader: str = ""
    channel: str = ""
    duration: float | None = None
    view_count: float | None = None
    like_count: float | None = None
    upload_date: str = ""
    webpage_url: str = ""
    thumbnail_url: str = ""
    description: str = ""
    categories: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    is_live: bool = False
    video_formats: list[FormatInfo] = field(default_factory=list)
    audio_formats: list[FormatInfo] = field(default_factory=list)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> MediaInfo:
        video: list[FormatInfo] = []
        audio: list[FormatInfo] = []
        for entry in raw.get("formats") or []:
            fmt = FormatInfo.from_dict(entry)
            if fmt.is_storyboard:
                continue
            # Video side: anything with a picture and a stated height.
            if fmt.has_video and fmt.height:
                video.append(fmt)
            elif fmt.has_audio and not fmt.has_video:
                audio.append(fmt)

        # Highest resolution first, then highest bitrate.
        video.sort(key=lambda f: (f.height or 0, f.tbr or 0), reverse=True)
        audio.sort(key=lambda f: (f.abr or f.tbr or 0), reverse=True)

        return cls(
            id=_text(raw.get("id")),
            title=_text(raw.get("title")),
            uploader=_text(raw.get("uploader") or raw.get("channel")),
            channel=_text(raw.get("channel")),
            duration=_num(raw.get("duration")),
            view_count=_num(raw.get("view_count")),
            like_count=_num(raw.get("like_count")),
            upload_date=_text(raw.get("upload_date")),
            webpage_url=_text(raw.get("webpage_url")),
            thumbnail_url=_text(raw.get("thumbnail")),
            description=_text(raw.get("description")),
            categories=[str(c) for c in (raw.get("categories") or [])],
            tags=[str(t) for t in (raw.get("tags") or [])],
            is_live=bool(raw.get("is_live")),
            video_formats=video,
            audio_formats=audio,
        )

    @property
    def display_channel(self) -> str:
        return self.uploader or self.channel or "Unknown"

    @property
    def max_video_height(self) -> int:
        return max((f.height or 0) for f in self.video_formats) if self.video_formats else 0
