"""Package entry point: ``python -m yoinktui``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from yoinktui import __version__
from yoinktui.backend.config import (
    default_config_path,
    load_config,
    to_toml,
    write_default_config,
)
from yoinktui.backend.ytdlp import check_dependencies


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="yoinktui",
        description="Steam-style TUI download manager powered by yt-dlp.",
    )
    parser.add_argument(
        "urls",
        nargs="*",
        metavar="URL",
        help="media URL(s) to download without TUI (or '-' for stdin)",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--config",
        type=Path,
        metavar="PATH",
        help="configuration file (default: ~/.config/yoinktui/config.toml)",
    )
    parser.add_argument(
        "--print-config",
        action="store_true",
        help="print the effective config as TOML and exit",
    )
    parser.add_argument(
        "--write-default-config",
        action="store_true",
        help="write a default config file and exit",
    )
    parser.add_argument(
        "--doctor",
        action="store_true",
        help="check yt-dlp/ffmpeg, config, and paths, then exit",
    )

    download = parser.add_argument_group("download options")
    download.add_argument(
        "-o",
        "--output-dir",
        "--download-dir",
        type=Path,
        dest="download_dir",
        metavar="DIR",
        help="where downloads are saved (default: ~/Videos/yoinktui)",
    )
    download.add_argument(
        "-f",
        "--format",
        dest="format_selector",
        metavar="FORMAT",
        help="format selector for yt-dlp (e.g. 137, bestvideo+bestaudio)",
    )
    download.add_argument(
        "-m",
        "--mode",
        dest="mode",
        choices=("video", "vonly", "audio"),
        help="download mode: video, vonly, or audio",
    )
    download.add_argument(
        "--preset",
        metavar="NAME",
        help="apply download settings from a named preset (e.g. music, phone)",
    )
    download.add_argument(
        "--output-template",
        metavar="TEMPLATE",
        help="custom yt-dlp output template (e.g. '%%(title)s.%%(ext)s')",
    )
    download.add_argument(
        "--quality-cap",
        type=int,
        metavar="P",
        help="maximum video height, 0 = best (default: 1080)",
    )
    download.add_argument(
        "--container",
        choices=("mkv", "mp4", "auto"),
        help="merge container (default: mkv)",
    )
    download.add_argument(
        "--audio-format",
        choices=("mp3", "m4a", "opus", "flac", "best"),
        help="audio extraction format (default: mp3)",
    )
    download.add_argument("--audio-quality", metavar="Q", help="audio quality (default: 0)")
    download.add_argument(
        "--concurrent-fragments",
        type=int,
        metavar="N",
        help="fragments to download in parallel (0 = yt-dlp default)",
    )
    download.add_argument("--rate-limit", metavar="RATE", help="download rate limit, e.g. 5M")
    download.add_argument(
        "--default-mode",
        choices=("video", "vonly", "audio"),
        help="mode preselected on the format screen",
    )
    download.add_argument(
        "--write-subtitles",
        "--write-subs",
        action="store_true",
        default=None,
        dest="write_subtitles",
        help="download and embed subtitles",
    )
    download.add_argument(
        "--no-write-subtitles",
        "--no-subs",
        action="store_false",
        dest="write_subtitles",
        help="do not download subtitles",
    )
    download.add_argument(
        "--embed-metadata",
        action="store_true",
        default=None,
        dest="embed_metadata",
        help="embed metadata tags into media file",
    )
    download.add_argument(
        "--no-embed-metadata",
        action="store_false",
        dest="embed_metadata",
        help="do not embed metadata tags",
    )
    download.add_argument(
        "--embed-thumbnail",
        action="store_true",
        default=None,
        dest="embed_thumbnail",
        help="embed cover/thumbnail artwork into media file",
    )
    download.add_argument(
        "--no-embed-thumbnail",
        action="store_false",
        dest="embed_thumbnail",
        help="do not embed cover artwork",
    )
    download.add_argument(
        "--keep-original",
        action="store_true",
        default=None,
        dest="keep_original",
        help="keep original video/audio files after extraction or merging",
    )
    download.add_argument(
        "--theme", metavar="NAME", help="theme name (dark/light or a Textual theme)"
    )

    playlist = parser.add_argument_group("playlist options")
    playlist.add_argument(
        "--yes-playlist",
        action="store_true",
        help="download the entire playlist if URL refers to one",
    )
    playlist.add_argument(
        "--no-playlist",
        action="store_true",
        help="only download single video if URL has both video and playlist",
    )
    playlist.add_argument(
        "--playlist-items",
        metavar="ITEMS",
        help="playlist item indices to download (e.g. '1,2,5-8')",
    )

    automation = parser.add_argument_group("headless & automation options")
    automation.add_argument(
        "-a",
        "--batch-file",
        type=Path,
        metavar="FILE",
        help="file containing URLs to download (one per line, or '-' for stdin)",
    )
    automation.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="suppress download progress output (errors still print to stderr)",
    )
    automation.add_argument(
        "--json",
        action="store_true",
        help="stream progress and results as newline-delimited JSON (NDJSON)",
    )
    automation.add_argument(
        "--dry-run",
        action="store_true",
        help="simulate download; probe metadata and print plan without fetching media",
    )
    automation.add_argument(
        "--print-command",
        action="store_true",
        help="print the exact yt-dlp command line invocation",
    )
    automation.add_argument(
        "--no-history",
        action="store_true",
        help="do not record downloads in the SQLite history/library database",
    )
    automation.add_argument(
        "--tui",
        action="store_true",
        help="launch the interactive TUI even if a URL is provided",
    )

    network = parser.add_argument_group("network options")
    network.add_argument(
        "--cookies-from-browser",
        metavar="BROWSER[:PROFILE]",
        help="pass browser cookies to yt-dlp (chrome, firefox, edge, brave, ...)",
    )
    network.add_argument(
        "--cookies",
        type=Path,
        metavar="FILE",
        dest="cookies_file",
        help="Netscape-format cookies.txt file exported from a browser",
    )
    network.add_argument(
        "--impersonate",
        metavar="CLIENT[:OS]",
        dest="impersonate",
        help="client to impersonate for anti-bot bypass (e.g. chrome)",
    )
    network.add_argument(
        "--proxy",
        metavar="URL",
        help="proxy for yt-dlp, e.g. socks5://127.0.0.1:1080",
    )
    network.add_argument(
        "--yt-dlp-arg",
        action="append",
        default=[],
        dest="yt_dlp_args",
        metavar="ARG",
        help="extra yt-dlp argument; repeatable (use --yt-dlp-arg=--flag for flags)",
    )

    ui = parser.add_argument_group("UI options")
    ui.add_argument("--no-color", action="store_true", default=None, help="disable colour output")
    ui.add_argument("--ascii", action="store_true", default=None, help="prefer ASCII glyphs")
    return parser


def _cli_overrides(args: argparse.Namespace) -> dict[str, object]:
    overrides: dict[str, object] = {
        "download_dir": args.download_dir,
        "quality_cap": args.quality_cap,
        "container": args.container,
        "audio_format": args.audio_format,
        "audio_quality": args.audio_quality,
        "concurrent_fragments": args.concurrent_fragments,
        "rate_limit": args.rate_limit,
        "default_mode": args.mode or args.default_mode,
        "theme": args.theme,
        "cookies_from_browser": args.cookies_from_browser,
        "cookies_file": args.cookies_file,
        "impersonate": args.impersonate,
        "proxy": args.proxy,
        "extra_args": tuple(args.yt_dlp_args) if args.yt_dlp_args else None,
        "no_color": args.no_color,
        "ascii": args.ascii,
    }
    if getattr(args, "write_subtitles", None) is not None:
        overrides["write_subtitles"] = args.write_subtitles
    if getattr(args, "embed_metadata", None) is not None:
        overrides["embed_metadata"] = args.embed_metadata
    if getattr(args, "embed_thumbnail", None) is not None:
        overrides["embed_thumbnail"] = args.embed_thumbnail
    if getattr(args, "keep_original", None) is not None:
        overrides["keep_original"] = args.keep_original
    return overrides


def _run_doctor(config_path: Path | None) -> int:
    report = check_dependencies()
    print("YoinkTUI doctor")
    print(report.as_text())

    config = load_config(config_path)
    print(f"\nconfig file: {config_path or default_config_path()}")
    print(f"download dir: {config.download_dir}")
    try:
        config.download_dir.mkdir(parents=True, exist_ok=True)
        probe = config.download_dir / ".yoinktui-write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        print(f"✗ download dir is not writable: {exc}")
        return 1
    print("✓ download dir is writable")
    if config.cookies_file:
        print(f"✓ cookies file: {config.cookies_file}")
    elif config.cookies_from_browser:
        print(f"✓ cookies from browser: {config.cookies_from_browser}")
    if config.impersonate:
        print(f"✓ impersonate client: {config.impersonate}")
    for warning in config.warnings:
        print(f"! {warning}")
    return 0 if report.ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.write_default_config:
        try:
            path = write_default_config(args.config)
        except FileExistsError:
            target = args.config or default_config_path()
            print(f"Config already exists: {target}")
            return 1
        print(f"Wrote {path}")
        return 0

    if args.doctor:
        return _run_doctor(args.config)

    config = load_config(args.config, cli=_cli_overrides(args))

    if args.print_config:
        print(to_toml(config), end="")
        for warning in config.warnings:
            print(f"warning: {warning}", file=sys.stderr)
        return 0

    if not args.quiet:
        for warning in config.warnings:
            print(f"warning: {warning}", file=sys.stderr)

    is_headless = not args.tui and bool(
        args.urls or args.batch_file or args.dry_run or args.print_command
    )
    if is_headless:
        from yoinktui.cli import run_headless

        return run_headless(args, config)

    from yoinktui.app import YoinkTUIApp

    initial_url = args.urls[0] if args.urls else ""
    app = YoinkTUIApp(config=config, initial_url=initial_url)
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
