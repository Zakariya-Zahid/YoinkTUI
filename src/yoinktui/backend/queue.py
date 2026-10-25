"""Persistent download queue and the policy snapshot for each item.

The queue is intentionally backend-only: screens render it, but the state and
JSON format live here so the queue survives restarts and can be tested without
Textual.
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from yoinktui.backend.config import AppConfig, data_dir
from yoinktui.backend.presets import Preset
from yoinktui.backend.ytdlp import (
    PlaylistEntry,
    Section,
    audio_selector,
    resolve_merge_format,
    section_slug,
    video_selector,
)

QueueStatus = Literal["pending", "running", "done", "failed", "cancelled", "interrupted"]
_RESUMABLE = ("pending", "interrupted", "failed")


def safe_filename(value: str, *, fallback: str = "video") -> str:
    """Make a title safe for a filename template."""
    cleaned = "".join(c for c in value if c.isalnum() or c in " -_.").strip()[:80]
    return cleaned or fallback


@dataclass(frozen=True, slots=True)
class DownloadPolicy:
    """The subset of config/preset values needed to start one download."""

    mode: str = "video"
    download_dir: Path = Path(".")
    quality_cap: int = 1080
    container: str = "mkv"
    audio_format: str = "mp3"
    audio_quality: str = "0"
    concurrent_fragments: int = 0
    rate_limit: str = ""
    write_subtitles: bool = False
    embed_metadata: bool = True
    embed_thumbnail: bool = False
    keep_original: bool = False
    extra_args: tuple[str, ...] = ()

    @classmethod
    def from_config(cls, config: AppConfig, preset: Preset | None = None) -> DownloadPolicy:
        if preset is not None:
            return cls(
                mode=preset.mode,
                download_dir=config.download_dir,
                quality_cap=preset.quality_cap,
                container=preset.container,
                audio_format=preset.audio_format,
                audio_quality=preset.audio_quality,
                concurrent_fragments=config.concurrent_fragments,
                rate_limit=config.rate_limit,
                write_subtitles=preset.write_subtitles,
                embed_metadata=preset.embed_metadata,
                embed_thumbnail=preset.embed_thumbnail,
                keep_original=preset.keep_original,
                extra_args=tuple(config.ytdlp_args),
            )
        return cls(
            mode=config.default_mode,
            download_dir=config.download_dir,
            quality_cap=config.quality_cap,
            container=config.container,
            audio_format=config.audio_format,
            audio_quality=config.audio_quality,
            concurrent_fragments=config.concurrent_fragments,
            rate_limit=config.rate_limit,
            write_subtitles=config.write_subtitles,
            embed_metadata=config.embed_metadata,
            embed_thumbnail=config.embed_thumbnail,
            keep_original=config.keep_original,
            extra_args=tuple(config.ytdlp_args),
        )

    @property
    def merge_format(self) -> str:
        return "" if self.container == "auto" else self.container

    def default_selector(self) -> str:
        if self.mode == "audio":
            return audio_selector()
        if self.mode == "vonly":
            return f"bv*[height<={self.quality_cap}]/bv*" if self.quality_cap else "bv*"
        return video_selector(None, self.quality_cap or None)


@dataclass(slots=True)
class QueueItem:
    """One URL waiting to download, with all policy frozen at enqueue time."""

    url: str
    title: str = ""
    uploader: str = ""
    selector: str = "bv*+ba/b"
    out_template: str = ""
    extract_audio: bool = False
    mode: str = "video"
    section: Section | None = None
    expected_bytes: float | None = None
    merge_format: str = "mkv"
    audio_format: str = "mp3"
    audio_quality: str = "0"
    concurrent_fragments: int = 0
    rate_limit: str = ""
    write_subtitles: bool = False
    embed_metadata: bool = True
    embed_thumbnail: bool = False
    keep_original: bool = False
    extra_args: list[str] = field(default_factory=list)
    status: QueueStatus = "pending"
    error: str = ""
    output_path: str = ""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    @classmethod
    def from_media(
        cls,
        info: Any,
        policy: DownloadPolicy,
        *,
        selected_format: Any = None,
        section: Section | None = None,
        expected_bytes: float | None = None,
        title: str | None = None,
        unique_id: str = "",
    ) -> QueueItem:
        """Build an item from probed metadata and a policy snapshot."""
        url = info.webpage_url or (f"https://www.youtube.com/watch?v={info.id}" if info.id else "")
        mode = policy.mode
        video_format = selected_format
        audio_format = info.audio_formats[0] if info.audio_formats else None
        if video_format is not None and not getattr(video_format, "has_video", False):
            video_format = None

        if mode == "audio":
            selector = (
                selected_format.format_id
                if selected_format is not None
                and getattr(selected_format, "has_audio", False)
                and not getattr(selected_format, "has_video", False)
                else audio_selector()
            )
            extract_audio = True
        elif mode == "vonly":
            selector = (
                selected_format.format_id
                if selected_format is not None and getattr(selected_format, "has_video", False)
                else policy.default_selector()
            )
            extract_audio = False
        else:
            if video_format is None:
                selector = video_selector(None, policy.quality_cap or None)
            elif getattr(video_format, "has_audio", False):
                # A muxed format already contains audio; use it as-is.
                selector = video_format.format_id
            else:
                # The format table usually lists video-only streams. In
                # Video+Audio mode, pair the selected stream with best audio
                # instead of downloading a silent file.
                selector = video_selector(video_format.format_id, policy.quality_cap or None)
            extract_audio = False

        merge_format = policy.merge_format
        if mode == "video":
            merge_format = resolve_merge_format(
                policy.merge_format,
                video_format,
                audio_format if video_format is not None and not video_format.has_audio else None,
            )

        base = safe_filename(title if title is not None else info.title)
        if unique_id:
            base = f"{base} [{unique_id}]"
        clip_suffix = f" [clip {section_slug(section)}]" if section is not None else ""
        out_template = str(policy.download_dir / f"{base}{clip_suffix}.%(ext)s")

        return cls(
            url=url,
            title=title if title is not None else info.title,
            uploader=info.uploader or info.channel,
            selector=selector,
            out_template=out_template,
            extract_audio=extract_audio,
            mode=mode,
            section=section,
            expected_bytes=expected_bytes,
            merge_format=merge_format,
            audio_format=policy.audio_format,
            audio_quality=policy.audio_quality,
            concurrent_fragments=policy.concurrent_fragments,
            rate_limit=policy.rate_limit,
            write_subtitles=policy.write_subtitles,
            embed_metadata=policy.embed_metadata,
            embed_thumbnail=policy.embed_thumbnail,
            keep_original=policy.keep_original,
            extra_args=list(policy.extra_args),
        )

    @classmethod
    def from_entry(
        cls,
        entry: PlaylistEntry,
        policy: DownloadPolicy,
        *,
        title: str | None = None,
    ) -> QueueItem:
        """Build a queue item from a flat playlist entry.

        Flat entries have no format table, so the item uses the policy's
        default selector.  The worker probes again only if yt-dlp needs it;
        downloading directly is faster and works for normal playlist entries.
        """
        base = safe_filename(title if title is not None else entry.title)
        unique = entry.id or ""
        if unique:
            base = f"{base} [{unique}]"
        return cls(
            url=entry.url,
            title=title if title is not None else entry.title,
            uploader=entry.uploader,
            selector=policy.default_selector(),
            out_template=str(policy.download_dir / f"{base}.%(ext)s"),
            extract_audio=policy.mode == "audio",
            mode=policy.mode,
            merge_format=policy.merge_format,
            audio_format=policy.audio_format,
            audio_quality=policy.audio_quality,
            concurrent_fragments=policy.concurrent_fragments,
            rate_limit=policy.rate_limit,
            write_subtitles=policy.write_subtitles,
            embed_metadata=policy.embed_metadata,
            embed_thumbnail=policy.embed_thumbnail,
            keep_original=policy.keep_original,
            extra_args=list(policy.extra_args),
        )

    @property
    def resumable(self) -> bool:
        return self.status in _RESUMABLE

    @property
    def display_title(self) -> str:
        return self.title or self.url or "Untitled"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "url": self.url,
            "title": self.title,
            "uploader": self.uploader,
            "selector": self.selector,
            "out_template": self.out_template,
            "extract_audio": self.extract_audio,
            "mode": self.mode,
            "section": (
                None
                if self.section is None
                else {
                    "start": self.section.start,
                    "end": self.section.end,
                    "precise": self.section.precise,
                }
            ),
            "expected_bytes": self.expected_bytes,
            "merge_format": self.merge_format,
            "audio_format": self.audio_format,
            "audio_quality": self.audio_quality,
            "concurrent_fragments": self.concurrent_fragments,
            "rate_limit": self.rate_limit,
            "write_subtitles": self.write_subtitles,
            "embed_metadata": self.embed_metadata,
            "embed_thumbnail": self.embed_thumbnail,
            "keep_original": self.keep_original,
            "extra_args": list(self.extra_args),
            "status": self.status,
            "error": self.error,
            "output_path": self.output_path,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> QueueItem:
        section_raw = raw.get("section")
        section = None
        if isinstance(section_raw, dict):
            section = Section(
                start=float(section_raw.get("start") or 0.0),
                end=(float(section_raw["end"]) if section_raw.get("end") is not None else None),
                precise=bool(section_raw.get("precise", False)),
            )
        status = str(raw.get("status") or "pending")
        if status not in ("pending", "running", "done", "failed", "cancelled", "interrupted"):
            status = "pending"
        raw_args = raw.get("extra_args") or []
        extra_args = [str(arg) for arg in raw_args] if isinstance(raw_args, list) else []
        expected_bytes: float | None = None
        if raw.get("expected_bytes") is not None:
            try:
                expected_bytes = float(raw["expected_bytes"])
            except (TypeError, ValueError):
                expected_bytes = None
        try:
            concurrent_fragments = int(raw.get("concurrent_fragments") or 0)
        except (TypeError, ValueError):
            concurrent_fragments = 0
        return cls(
            id=str(raw.get("id") or uuid.uuid4().hex[:12]),
            url=str(raw.get("url") or ""),
            title=str(raw.get("title") or ""),
            uploader=str(raw.get("uploader") or ""),
            selector=str(raw.get("selector") or "bv*+ba/b"),
            out_template=str(raw.get("out_template") or ""),
            extract_audio=bool(raw.get("extract_audio", False)),
            mode=str(raw.get("mode") or "video"),
            section=section,
            expected_bytes=expected_bytes,
            merge_format=str(raw.get("merge_format") or ""),
            audio_format=str(raw.get("audio_format") or "mp3"),
            audio_quality=str(raw.get("audio_quality") or "0"),
            concurrent_fragments=concurrent_fragments,
            rate_limit=str(raw.get("rate_limit") or ""),
            write_subtitles=bool(raw.get("write_subtitles", False)),
            embed_metadata=bool(raw.get("embed_metadata", True)),
            embed_thumbnail=bool(raw.get("embed_thumbnail", False)),
            keep_original=bool(raw.get("keep_original", False)),
            extra_args=extra_args,
            status=status,  # type: ignore[arg-type]
            error=str(raw.get("error") or ""),
            output_path=str(raw.get("output_path") or ""),
        )


@dataclass(slots=True)
class DownloadQueue:
    """Ordered collection of queue items."""

    items: list[QueueItem] = field(default_factory=list)

    def add(self, item: QueueItem) -> QueueItem:
        self.items.append(item)
        return item

    def resumable(self) -> list[QueueItem]:
        return [item for item in self.items if item.resumable]

    def has_resumable(self) -> bool:
        return any(item.resumable for item in self.items)

    def pending_count(self) -> int:
        return sum(1 for item in self.items if item.status == "pending")

    def clear_finished(self) -> int:
        before = len(self.items)
        self.items = [item for item in self.items if item.resumable]
        return before - len(self.items)

    def to_dict(self) -> dict[str, Any]:
        return {"version": 1, "items": [item.to_dict() for item in self.items]}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> DownloadQueue:
        items = raw.get("items")
        if not isinstance(items, list):
            return cls()
        queue = cls()
        for entry in items:
            if not isinstance(entry, dict):
                continue
            try:
                item = QueueItem.from_dict(entry)
            except (TypeError, ValueError):
                # A single malformed item must not make the whole queue
                # unreadable after an upgrade or hand edit.
                continue
            if item.url:
                queue.items.append(item)
        return queue


class QueueStore:
    """JSON persistence for the download queue.

    Writes are atomic (temp file + replace) so a crash cannot leave a partial
    queue.  Running items become ``interrupted`` on the next load; the UI then
    offers to resume them.
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path = (path or data_dir() / "queue.json").expanduser()
        self._lock = threading.RLock()

    def load(self) -> DownloadQueue:
        with self._lock:
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, ValueError, UnicodeError):
                return DownloadQueue()
        if not isinstance(raw, dict):
            return DownloadQueue()
        queue = DownloadQueue.from_dict(raw)
        for item in queue.items:
            if item.status == "running":
                item.status = "interrupted"
        return queue

    def save(self, queue: DownloadQueue) -> None:
        with self._lock:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                tmp = self.path.with_suffix(self.path.suffix + ".tmp")
                tmp.write_text(json.dumps(queue.to_dict(), indent=2), encoding="utf-8")
                os.replace(tmp, self.path)
            except (OSError, TypeError, ValueError):
                # Persistence is best effort; a read-only data dir must not
                # break the download itself.
                pass


__all__ = [
    "DownloadPolicy",
    "DownloadQueue",
    "QueueItem",
    "QueueStatus",
    "QueueStore",
    "safe_filename",
]
