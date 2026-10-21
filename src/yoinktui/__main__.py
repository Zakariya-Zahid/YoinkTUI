"""Package entry point: ``python -m yoinktui``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="yoinktui",
        description="Steam-style TUI download manager powered by yt-dlp.",
    )
    parser.add_argument(
        "--download-dir",
        type=Path,
        metavar="DIR",
        help="where downloads are saved (default: ~/Videos/yoinktui)",
    )
    parser.add_argument(
        "--cookies-from-browser",
        metavar="BROWSER[:PROFILE]",
        help="pass browser cookies to yt-dlp (chrome, firefox, edge, brave, ...)",
    )
    parser.add_argument(
        "--proxy",
        metavar="URL",
        help="proxy for yt-dlp, e.g. socks5://127.0.0.1:1080",
    )
    parser.add_argument(
        "--yt-dlp-arg",
        action="append",
        default=[],
        dest="yt_dlp_args",
        metavar="ARG",
        help="extra yt-dlp argument; repeatable (use --yt-dlp-arg=--flag for flags)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    from yoinktui.app import AppConfig, YoinkTUIApp

    config = AppConfig()
    if args.download_dir is not None:
        config.download_dir = args.download_dir
    config.cookies_from_browser = args.cookies_from_browser
    config.proxy = args.proxy
    config.extra_args = tuple(args.yt_dlp_args)

    app = YoinkTUIApp(config=config)
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
