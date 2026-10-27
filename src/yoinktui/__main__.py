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
        "--download-dir",
        type=Path,
        metavar="DIR",
        help="where downloads are saved (default: ~/Videos/yoinktui)",
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
        "--theme", metavar="NAME", help="theme name (dark/light or a Textual theme)"
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
    return {
        "download_dir": args.download_dir,
        "quality_cap": args.quality_cap,
        "container": args.container,
        "audio_format": args.audio_format,
        "audio_quality": args.audio_quality,
        "concurrent_fragments": args.concurrent_fragments,
        "rate_limit": args.rate_limit,
        "default_mode": args.default_mode,
        "theme": args.theme,
        "cookies_from_browser": args.cookies_from_browser,
        "cookies_file": args.cookies_file,
        "proxy": args.proxy,
        "extra_args": tuple(args.yt_dlp_args) if args.yt_dlp_args else None,
        "no_color": args.no_color,
        "ascii": args.ascii,
    }


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

    for warning in config.warnings:
        print(f"warning: {warning}", file=sys.stderr)

    from yoinktui.app import YoinkTUIApp

    app = YoinkTUIApp(config=config)
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
