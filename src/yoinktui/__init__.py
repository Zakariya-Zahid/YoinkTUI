"""yoinktui - a creative TUI for downloading YouTube media.

Backend: yt-dlp (extraction) + ffmpeg (merge/postprocess), orchestrated the
way yt-x does it, but with an entirely original interface.
"""

from importlib.metadata import PackageNotFoundError, version

try:  # pyproject.toml is the single source of truth for the version
    __version__ = version("yoinktui")
except PackageNotFoundError:  # pragma: no cover - running from a raw source tree
    __version__ = "0.0.0+source"
