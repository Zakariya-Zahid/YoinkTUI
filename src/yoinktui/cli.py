"""Headless CLI mode for YoinkTUI automation and scripting.

Enables non-interactive downloading, NDJSON event streaming, batch processing,
dry-run command printing, and structured exit codes without launching the TUI.
"""

from __future__ import annotations

import argparse
import json
import shlex
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any, TextIO

from yoinktui.backend.config import AppConfig
from yoinktui.backend.errors import DownloadError, ErrorReason
from yoinktui.backend.library import LibraryStore
from yoinktui.backend.queue import DownloadPolicy, QueueItem
from yoinktui.backend.ytdlp import (
    _build_cmd,
    check_dependencies,
    download,
    probe,
    probe_playlist,
)

# Stable exit codes per failure category (Module 01 / 09 specification)
EXIT_SUCCESS: int = 0
EXIT_GENERAL: int = 1
EXIT_USAGE: int = 2
EXIT_NETWORK: int = 10
EXIT_AUTH: int = 11
EXIT_GEO: int = 12
EXIT_NOT_FOUND: int = 13
EXIT_DISK: int = 14
EXIT_DEPENDENCY: int = 15
EXIT_UNSUPPORTED: int = 16
EXIT_NO_STREAMS: int = 17
EXIT_CANCELLED: int = 130

EXIT_CODE_MAP: dict[ErrorReason, int] = {
    ErrorReason.NETWORK: EXIT_NETWORK,
    ErrorReason.AUTH: EXIT_AUTH,
    ErrorReason.GEO: EXIT_GEO,
    ErrorReason.NOT_FOUND: EXIT_NOT_FOUND,
    ErrorReason.DISK: EXIT_DISK,
    ErrorReason.FFMPEG_MISSING: EXIT_DEPENDENCY,
    ErrorReason.UNSUPPORTED: EXIT_UNSUPPORTED,
    ErrorReason.NO_STREAMS: EXIT_NO_STREAMS,
    ErrorReason.CANCELLED: EXIT_CANCELLED,
    ErrorReason.UNKNOWN: EXIT_GENERAL,
}


def exit_code_for_error(exc: Exception) -> int:
    """Return the stable integer exit code for a given exception."""
    if isinstance(exc, DownloadError):
        return EXIT_CODE_MAP.get(exc.reason, EXIT_GENERAL)
    if isinstance(exc, KeyboardInterrupt):
        return EXIT_CANCELLED
    return EXIT_GENERAL


def parse_playlist_items(spec: str, max_items: int | None = None) -> list[int]:
    """Parse a yt-dlp style playlist items specification into 1-based indices.

    Examples:
        '1,2,5' -> [1, 2, 5]
        '1-3,5' -> [1, 2, 3, 5]
        '-3'    -> [1, 2, 3]
        '5-'    -> [5, 6, ..., max_items]
    """
    indices: set[int] = set()
    parts = [p.strip() for p in spec.split(",") if p.strip()]
    for part in parts:
        if "-" in part:
            start_s, end_s = part.split("-", 1)
            start_val = int(start_s) if start_s.strip() else 1
            if end_s.strip():
                end_val = int(end_s)
            elif max_items is not None:
                end_val = max_items
            else:
                end_val = start_val
            if start_val <= end_val:
                for i in range(start_val, end_val + 1):
                    if max_items is None or i <= max_items:
                        indices.add(i)
        else:
            val = int(part)
            if max_items is None or val <= max_items:
                indices.add(val)
    return sorted(indices)


def collect_urls(
    positional_urls: Sequence[str],
    batch_file: Path | str | None = None,
    stdin_stream: TextIO | None = None,
) -> list[str]:
    """Collect URLs from positional CLI arguments and/or a batch file or stdin."""
    urls: list[str] = []
    stream = stdin_stream if stdin_stream is not None else sys.stdin

    if batch_file:
        if str(batch_file) == "-":
            for line in stream:
                line = line.strip()
                if line and not line.startswith("#"):
                    urls.append(line)
        else:
            path = Path(batch_file).expanduser()
            if not path.is_file():
                raise FileNotFoundError(f"Batch file does not exist: {path}")
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    urls.append(line)

    for raw in positional_urls:
        raw = raw.strip()
        if not raw:
            continue
        if raw == "-":
            for line in stream:
                line = line.strip()
                if line and not line.startswith("#"):
                    urls.append(line)
        else:
            urls.append(raw)

    return urls


def _fmt_bytes(b: float | None) -> str:
    """Format byte size as human-readable string."""
    if b is None or b < 0:
        return "N/A"
    size = float(b)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if size < 1024.0:
            return f"{size:.1f}{unit}"
        size /= 1024.0
    return f"{size:.1f}TiB"


def _fmt_eta(seconds: float | None) -> str:
    """Format seconds into HH:MM:SS or MM:SS."""
    if seconds is None or seconds < 0:
        return "N/A"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def _emit_json(data: dict[str, Any], out: TextIO | None = None) -> None:
    target = out or sys.stdout
    target.write(json.dumps(data, ensure_ascii=False) + "\n")
    target.flush()


def run_headless(
    args: argparse.Namespace,
    config: AppConfig,
    *,
    stdin_stream: TextIO | None = None,
    stdout_stream: TextIO | None = None,
    stderr_stream: TextIO | None = None,
) -> int:
    """Run non-interactive downloads and return an exit code."""
    out = stdout_stream or sys.stdout
    err = stderr_stream or sys.stderr

    # 1. Dependency check
    report = check_dependencies()
    if not report.ok:
        err.write("Dependency check failed:\n")
        err.write(report.as_text() + "\n")
        return EXIT_DEPENDENCY

    # 2. Preset resolution
    preset_name = getattr(args, "preset", None)
    preset = None
    if preset_name:
        if preset_name not in config.presets:
            available = ", ".join(sorted(config.presets.keys()))
            err.write(f"Error: Unknown preset {preset_name!r}. Available: {available}\n")
            return EXIT_USAGE
        preset = config.presets[preset_name]

    # 3. Policy build
    policy = DownloadPolicy.from_config(config, preset=preset)
    policy_overrides: dict[str, Any] = {}
    if getattr(args, "mode", None):
        policy_overrides["mode"] = args.mode
    if getattr(args, "container", None):
        policy_overrides["container"] = args.container
    if getattr(args, "audio_format", None):
        policy_overrides["audio_format"] = args.audio_format
    if getattr(args, "audio_quality", None):
        policy_overrides["audio_quality"] = args.audio_quality
    if getattr(args, "quality_cap", None) is not None:
        policy_overrides["quality_cap"] = args.quality_cap
    if getattr(args, "write_subtitles", None) is not None:
        policy_overrides["write_subtitles"] = args.write_subtitles
    if getattr(args, "embed_metadata", None) is not None:
        policy_overrides["embed_metadata"] = args.embed_metadata
    if getattr(args, "embed_thumbnail", None) is not None:
        policy_overrides["embed_thumbnail"] = args.embed_thumbnail
    if getattr(args, "keep_original", None) is not None:
        policy_overrides["keep_original"] = args.keep_original
    if getattr(args, "download_dir", None):
        policy_overrides["download_dir"] = Path(args.download_dir).expanduser()

    if policy_overrides:
        import dataclasses

        policy = dataclasses.replace(policy, **policy_overrides)

    try:
        policy.download_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        err.write(f"Error: Could not create download directory {policy.download_dir}: {exc}\n")
        return EXIT_DISK

    # 4. Collect URLs
    try:
        urls = collect_urls(
            getattr(args, "urls", []),
            batch_file=getattr(args, "batch_file", None),
            stdin_stream=stdin_stream,
        )
    except FileNotFoundError as exc:
        err.write(f"Error: {exc}\n")
        return EXIT_USAGE

    if not urls:
        err.write("Error: No URLs provided to download.\n")
        return EXIT_USAGE

    # 5. History store
    library: LibraryStore | None = None
    if not getattr(args, "no_history", False) and not getattr(args, "dry_run", False):
        try:
            library = LibraryStore()
        except Exception:
            library = None

    format_selector = getattr(args, "format_selector", None)
    output_template = getattr(args, "output_template", None)
    yes_playlist = getattr(args, "yes_playlist", False)
    playlist_items_spec = getattr(args, "playlist_items", None)
    dry_run = getattr(args, "dry_run", False)
    print_command = getattr(args, "print_command", False)
    as_json = getattr(args, "json", False)
    quiet = getattr(args, "quiet", False)

    first_failure_code = EXIT_SUCCESS

    is_tty = hasattr(out, "isatty") and out.isatty()

    for url in urls:
        items_to_download: list[QueueItem] = []

        if yes_playlist:
            try:
                playlist = probe_playlist(url, extra_args=config.ytdlp_args)
                entries = playlist.entries
                if playlist_items_spec:
                    indices = parse_playlist_items(playlist_items_spec, len(entries))
                    entries = [entries[i - 1] for i in indices if 1 <= i <= len(entries)]
                for entry in entries:
                    item = QueueItem.from_entry(entry, policy)
                    if format_selector:
                        item.selector = format_selector
                    if output_template:
                        item.out_template = output_template
                    items_to_download.append(item)
            except DownloadError:
                # If it's not a playlist, fall back to single video probe
                items_to_download = []

        if not items_to_download:
            try:
                info = probe(url, extra_args=config.ytdlp_args)
                item = QueueItem.from_media(info, policy)
                if format_selector:
                    item.selector = format_selector
                if output_template:
                    item.out_template = output_template
                items_to_download.append(item)
            except KeyboardInterrupt:
                if as_json:
                    _emit_json(
                        {
                            "event": "error",
                            "url": url,
                            "error": "Cancelled by user",
                            "reason": ErrorReason.CANCELLED.value,
                        },
                        out=out,
                    )
                else:
                    err.write("\nOperation cancelled by user.\n")
                return EXIT_CANCELLED
            except DownloadError as exc:
                if as_json:
                    _emit_json(
                        {
                            "event": "error",
                            "url": url,
                            "error": str(exc),
                            "reason": exc.reason.value,
                        },
                        out=out,
                    )
                else:
                    err.write(f"Error probing {url}: {exc.user_message}\n")
                if first_failure_code == EXIT_SUCCESS:
                    first_failure_code = exit_code_for_error(exc)
                continue
            except Exception as exc:
                if as_json:
                    _emit_json(
                        {
                            "event": "error",
                            "url": url,
                            "error": str(exc),
                            "reason": ErrorReason.UNKNOWN.value,
                        },
                        out=out,
                    )
                else:
                    err.write(f"Error probing {url}: {exc}\n")
                if first_failure_code == EXIT_SUCCESS:
                    first_failure_code = EXIT_GENERAL
                continue

        for item in items_to_download:
            cmd = _build_cmd(
                item.url,
                item.selector,
                item.out_template,
                extract_audio=item.extract_audio,
                audio_format=item.audio_format,
                audio_quality=item.audio_quality,
                merge_format=item.merge_format,
                extra_args=item.extra_args,
                section=item.section,
                concurrent_fragments=item.concurrent_fragments,
                rate_limit=item.rate_limit,
                write_subtitles=item.write_subtitles,
                embed_metadata=item.embed_metadata,
                embed_thumbnail=item.embed_thumbnail,
                keep_original=item.keep_original,
            )

            if print_command:
                out.write(shlex.join(cmd) + "\n")
                out.flush()

            if dry_run:
                if as_json:
                    _emit_json(
                        {
                            "event": "dry_run",
                            "url": item.url,
                            "title": item.title,
                            "selector": item.selector,
                            "out_template": item.out_template,
                            "command": cmd,
                        },
                        out=out,
                    )
                elif not quiet and not print_command:
                    out.write(f"[dry-run] URL:      {item.url}\n")
                    out.write(f"[dry-run] Title:    {item.title}\n")
                    out.write(f"[dry-run] Format:   {item.selector}\n")
                    out.write(f"[dry-run] Output:   {item.out_template}\n")
                    out.flush()
                continue

            record_id: int | None = None
            if library is not None:
                try:
                    record_id = library.record_start(item, title=item.title)
                except Exception:
                    record_id = None

            if as_json:
                _emit_json(
                    {
                        "event": "start",
                        "url": item.url,
                        "title": item.title,
                        "selector": item.selector,
                        "out_template": item.out_template,
                    },
                    out=out,
                )
            elif not quiet:
                out.write(f"[yoinktui] Starting: {item.title or item.url}\n")
                out.flush()

            start_time = time.monotonic()
            done_path = ""
            last_size: float | None = None
            last_line_len = 0

            try:
                for event in download(
                    item.url,
                    selector=item.selector,
                    out_template=item.out_template,
                    extract_audio=item.extract_audio,
                    extra_args=item.extra_args,
                    section=item.section,
                    expected_bytes=item.expected_bytes,
                    merge_format=item.merge_format,
                    audio_format=item.audio_format,
                    audio_quality=item.audio_quality,
                    concurrent_fragments=item.concurrent_fragments,
                    rate_limit=item.rate_limit,
                    write_subtitles=item.write_subtitles,
                    embed_metadata=item.embed_metadata,
                    embed_thumbnail=item.embed_thumbnail,
                    keep_original=item.keep_original,
                ):
                    if event.kind == "download":
                        if event.total:
                            last_size = event.total
                        if as_json:
                            _emit_json(
                                {
                                    "event": "download",
                                    "url": item.url,
                                    "status": event.status,
                                    "downloaded": event.downloaded,
                                    "total": event.total,
                                    "speed": event.speed,
                                    "eta": event.eta,
                                },
                                out=out,
                            )
                        elif not quiet and is_tty:
                            pct = (
                                (event.downloaded / event.total * 100.0)
                                if event.total and event.total > 0
                                else 0.0
                            )
                            speed_str = f"{_fmt_bytes(event.speed)}/s" if event.speed else "--.-B/s"
                            eta_str = _fmt_eta(event.eta)
                            total_str = _fmt_bytes(event.total)
                            dl_str = _fmt_bytes(event.downloaded)
                            line = f"\r[download] {pct:5.1f}% of {total_str} ({dl_str}) at {speed_str} ETA {eta_str}"
                            last_line_len = max(last_line_len, len(line))
                            out.write(line.ljust(last_line_len))
                            out.flush()

                    elif event.kind == "postprocess":
                        if as_json:
                            _emit_json(
                                {
                                    "event": "postprocess",
                                    "url": item.url,
                                    "section": event.section,
                                    "filename": event.filename,
                                },
                                out=out,
                            )
                        elif not quiet:
                            if is_tty and last_line_len > 0:
                                out.write("\n")
                                last_line_len = 0
                            out.write(f"[postprocess] {event.section or 'Processing'}...\n")
                            out.flush()

                    elif event.kind == "done":
                        done_path = event.filename

                duration = time.monotonic() - start_time
                if not as_json and not quiet and is_tty and last_line_len > 0:
                    out.write("\n")

                if as_json:
                    _emit_json(
                        {
                            "event": "done",
                            "url": item.url,
                            "title": item.title,
                            "path": done_path,
                            "size": last_size,
                            "duration_s": duration,
                        },
                        out=out,
                    )
                elif not quiet:
                    out.write(f"[yoinktui] Completed: {done_path or item.title}\n")
                    out.flush()

                if library is not None and record_id is not None:
                    library.record_finish(
                        record_id,
                        status="done",
                        path=done_path,
                        size=last_size,
                        duration_s=duration,
                    )

            except DownloadError as exc:
                if not as_json and not quiet and is_tty and last_line_len > 0:
                    out.write("\n")
                if as_json:
                    _emit_json(
                        {
                            "event": "error",
                            "url": item.url,
                            "error": str(exc),
                            "reason": exc.reason.value,
                        },
                        out=out,
                    )
                else:
                    err.write(f"Error downloading {item.url}: {exc.user_message}\n")
                if library is not None and record_id is not None:
                    library.record_finish(
                        record_id,
                        status="failed",
                        error=str(exc),
                    )
                if first_failure_code == EXIT_SUCCESS:
                    first_failure_code = exit_code_for_error(exc)

            except KeyboardInterrupt:
                if not as_json and not quiet and is_tty and last_line_len > 0:
                    out.write("\n")
                if as_json:
                    _emit_json(
                        {
                            "event": "error",
                            "url": item.url,
                            "error": "Cancelled by user",
                            "reason": ErrorReason.CANCELLED.value,
                        },
                        out=out,
                    )
                else:
                    err.write("\nOperation cancelled by user.\n")
                if library is not None and record_id is not None:
                    library.record_finish(
                        record_id,
                        status="cancelled",
                    )
                return EXIT_CANCELLED

            except Exception as exc:
                if not as_json and not quiet and is_tty and last_line_len > 0:
                    out.write("\n")
                if as_json:
                    _emit_json(
                        {
                            "event": "error",
                            "url": item.url,
                            "error": str(exc),
                            "reason": ErrorReason.UNKNOWN.value,
                        },
                        out=out,
                    )
                else:
                    err.write(f"Error downloading {item.url}: {exc}\n")
                if library is not None and record_id is not None:
                    library.record_finish(
                        record_id,
                        status="failed",
                        error=str(exc),
                    )
                if first_failure_code == EXIT_SUCCESS:
                    first_failure_code = EXIT_GENERAL

    return first_failure_code
