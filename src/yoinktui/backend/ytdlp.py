"""yt-dlp orchestration layer.

This is the whole "backend": it shells out to yt-dlp (which in turn uses
ffmpeg for stream merging and post-processing) and turns the process output
into typed events the TUI can render.

yt-dlp is driven with ``--newline`` plus custom ``--progress-template``s so
progress arrives as line-delimited records on stdout:

    DL|<status>|<downloaded>|<total>|<speed>|<eta>
    PP|<status>|<section>|<filename>
    FINAL|<filepath>

Note: ``--print`` implies ``--quiet``, so ``--no-quiet`` is required to keep
the progress stream alive.
"""

from __future__ import annotations

import contextlib
import os
import queue
import re
import shutil
import signal
import subprocess
import threading
import time
from collections import deque
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from yoinktui.backend.errors import DownloadError, ErrorReason, classify_error
from yoinktui.backend.models import FormatInfo, MediaInfo

ProgressKind = Literal["status", "download", "postprocess", "log", "done", "error"]

DL_TEMPLATE = (
    "download:DL|%(progress.status)s|%(progress.downloaded_bytes)s|"
    "%(progress.total_bytes)s|%(progress.total_bytes_estimate)s|"
    "%(progress.speed)s|%(progress.eta)s"
)
PP_TEMPLATE = "postprocess:PP|%(progress.status)s|%(progress.section_name)s|%(progress.filename)s"


# Backwards-compatible alias; new code should import DownloadError.
BackendError = DownloadError


@dataclass(slots=True)
class ProgressEvent:
    """A single decoded line of yt-dlp output."""

    kind: ProgressKind
    # download phase
    status: str = ""
    downloaded: float = 0.0
    total: float | None = None
    speed: float | None = None
    eta: float | None = None
    # postprocess / done
    filename: str = ""
    section: str = ""
    # log / error
    text: str = ""


@dataclass(frozen=True, slots=True)
class Section:
    """A time range (in seconds) to download from a longer video.

    ``end=None`` means "until the end of the video". ``precise`` asks yt-dlp
    to re-encode around the cut points so the output starts/ends exactly on
    the requested timestamps instead of the nearest keyframe.
    """

    start: float = 0.0
    end: float | None = None
    precise: bool = False


_CLOCK_HMS = re.compile(r"^(\d+):([0-5]?\d):([0-5]?\d)$")
_CLOCK_MS = re.compile(r"^(\d+):([0-5]?\d)$")
_SECONDS = re.compile(r"^\d+(?:\.\d+)?$")
_UNITS = re.compile(r"^(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?$", re.IGNORECASE)


def parse_timecode(value: str) -> float:
    """Parse a user-entered timestamp into seconds.

    Accepts ``HH:MM:SS``, ``MM:SS``, plain seconds (``90``), and compact
    units (``1h2m3s``). Raises ``ValueError`` with a friendly message.
    """
    text = value.strip()
    if not text:
        raise ValueError("Enter a time like 00:05:00")

    match = _CLOCK_HMS.fullmatch(text)
    if match:
        hours, minutes, seconds = (int(part) for part in match.groups())
        return hours * 3600 + minutes * 60 + seconds

    match = _CLOCK_MS.fullmatch(text)
    if match:
        minutes, seconds = (int(part) for part in match.groups())
        return minutes * 60 + seconds

    if _SECONDS.fullmatch(text):
        return float(text)

    match = _UNITS.fullmatch(text)
    if match and any(match.groups()):
        hours, minutes, seconds = (int(part or 0) for part in match.groups())
        return hours * 3600 + minutes * 60 + seconds

    raise ValueError("Use HH:MM:SS, MM:SS, seconds, or 1h2m3s")


def format_timecode(seconds: float | None, *, force_hours: bool = False) -> str:
    """Format seconds for the UI (``05:30`` or ``1:05:30``)."""
    if seconds is None:
        return "—"
    total = max(0, int(round(seconds)))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours or force_hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _section_time(seconds: float) -> str:
    """Always-hour (zero-padded) format for yt-dlp section specs and filenames."""
    total = max(0, int(round(seconds)))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def section_spec(section: Section) -> str:
    """Build the yt-dlp ``--download-sections`` value for a section."""
    if section.start < 0:
        raise ValueError("Start time cannot be negative")
    if section.end is not None and section.end <= section.start:
        raise ValueError("End time must be after start time")
    end = "" if section.end is None else _section_time(section.end)
    return f"*{_section_time(section.start)}-{end}"


def section_slug(section: Section) -> str:
    """A filesystem-friendly suffix identifying a section."""
    start = _section_time(section.start).replace(":", "-")
    end = "end" if section.end is None else _section_time(section.end).replace(":", "-")
    return f"{start}_{end}"


class _FileProgressMonitor:
    """Estimate live progress from the growing output file.

    yt-dlp's ``--download-sections`` path (which often hands the transfer to
    ffmpeg) does not emit the normal progress hooks until the section is
    complete. The output ``.part`` file still grows, so we can sample its size
    and derive speed/ETA for the dashboard.
    """

    def __init__(self, out_template: str, expected_bytes: float | None = None) -> None:
        self._expected = expected_bytes if expected_bytes and expected_bytes > 0 else None
        path = Path(out_template)
        self._parent = path.parent
        name = path.name
        # app templates end in "title.%(ext)s"; avoid patterns with other placeholders
        if "%(ext)s" in name:
            prefix = name.split("%(ext)s", 1)[0]
            self._prefix = prefix if prefix and "%(" not in prefix else None
        else:
            self._prefix = None
        self._started = time.time()
        self._last_emit = 0.0
        self._samples: deque[tuple[float, float]] = deque()

    def _size(self) -> float:
        if self._prefix is None:
            return 0.0
        total = 0.0
        try:
            candidates = self._parent.iterdir()
        except OSError:
            return 0.0
        for candidate in candidates:
            if not candidate.name.startswith(self._prefix):
                continue
            try:
                if not candidate.is_file():
                    continue
                stat = candidate.stat()
            except OSError:
                continue
            if candidate.name.endswith(".ytdl"):
                continue
            # Ignore old completed files from an earlier run. An active
            # .part is included even if its mtime predates this download.
            if stat.st_mtime < self._started - 2 and not candidate.name.endswith(".part"):
                continue
            total += stat.st_size
        return total

    def poll(self) -> ProgressEvent | None:
        now = time.monotonic()
        if now - self._last_emit < 0.45:
            return None
        size = self._size()
        if size <= 0:
            return None

        self._samples.append((now, size))
        while len(self._samples) > 2 and now - self._samples[0][0] > 8.0:
            self._samples.popleft()
        self._last_emit = now
        if len(self._samples) < 2:
            return None

        first_time, first_size = self._samples[0]
        elapsed = now - first_time
        if elapsed <= 0:
            return None
        speed = max(0.0, (size - first_size) / elapsed)
        total = self._expected
        eta = (total - size) / speed if total and speed > 0 and total > size else None
        return ProgressEvent(
            kind="download",
            status="downloading",
            downloaded=size,
            total=total,
            speed=speed or None,
            eta=eta,
        )


class DownloadControl:
    """Thread-safe handle used to pause, resume, or cancel a download.

    Pause/resume uses POSIX job control (``SIGSTOP``/``SIGCONT``) on the
    yt-dlp process group, so any child processes (``ffmpeg``) are suspended
    too. On platforms without ``SIGSTOP``, :meth:`pause` simply returns
    ``False`` and the caller can keep the control disabled.
    """

    def __init__(self) -> None:
        self.cancelled = False
        self.paused = False
        self._proc: subprocess.Popen[str] | None = None
        self._lock = threading.Lock()

    @property
    def supported(self) -> bool:
        return hasattr(signal, "SIGSTOP") and hasattr(os, "killpg")

    def attach(self, proc: subprocess.Popen[str]) -> None:
        with self._lock:
            self._proc = proc

    def detach(self) -> None:
        with self._lock:
            self._proc = None

    def _send(self, sig: int) -> bool:
        with self._lock:
            proc = self._proc
        if proc is None or proc.poll() is not None:
            return False
        try:
            os.killpg(os.getpgid(proc.pid), sig)
        except (ProcessLookupError, PermissionError, OSError):
            try:
                proc.send_signal(sig)
            except (ProcessLookupError, PermissionError, OSError):
                return False
        return True

    def pause(self) -> bool:
        """Suspend the process group. Returns True if now paused."""
        if self.paused:
            return True
        if not self.supported:
            return False
        self.paused = self._send(signal.SIGSTOP)
        return self.paused

    def resume(self) -> bool:
        """Continue a paused download. Returns True if now running."""
        if not self.paused:
            return True
        if not self.supported:
            return True
        self.paused = not self._send(signal.SIGCONT)
        return not self.paused

    def cancel(self) -> None:
        """Abort the download, resuming it first if it was paused."""
        self.cancelled = True
        if self.paused:
            self.resume()
        if self.supported:
            self._send(signal.SIGTERM)


def _to_float(value: str) -> float | None:
    if value in ("", "NA", "None", None):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clean(value: str) -> str:
    return "" if value in ("NA", "None") else value


def tool_available(tool: str) -> bool:
    return shutil.which(tool) is not None


MIN_YTDLP_VERSION = (2024, 1, 1)


@dataclass(frozen=True, slots=True)
class DependencyStatus:
    """Result of checking one external tool."""

    tool: str
    path: str | None
    version: str | None
    ok: bool
    detail: str = ""


@dataclass(frozen=True, slots=True)
class DependencyReport:
    """Aggregate pre-flight dependency check."""

    tools: tuple[DependencyStatus, ...]

    @property
    def errors(self) -> list[str]:
        return [
            f"{status.tool} is not installed"
            + (
                " — install ffmpeg and make sure it is on PATH."
                if status.tool == "ffmpeg"
                else " — install it with 'uv tool install yt-dlp' or your package manager."
            )
            for status in self.tools
            if not status.ok
        ]

    @property
    def warnings(self) -> list[str]:
        return [status.detail for status in self.tools if status.ok and status.detail]

    @property
    def ok(self) -> bool:
        return not self.errors

    def as_text(self) -> str:
        lines = []
        for status in self.tools:
            if not status.ok:
                lines.append(f"✗ {status.tool}: not found")
                continue
            version = f" {status.version}" if status.version else ""
            lines.append(f"✓ {status.tool}:{version} ({status.path})")
            if status.detail:
                lines.append(f"  ! {status.detail}")
        return "\n".join(lines)


def _version_args(tool: str) -> list[str]:
    return ["--version"] if tool == "yt-dlp" else ["-version"]


def tool_version(tool: str) -> str | None:
    """Return the first line of ``tool --version``, or ``None``."""
    if not tool_available(tool):
        return None
    try:
        proc = subprocess.run(
            [tool, *_version_args(tool)],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    output = (proc.stdout or proc.stderr or "").strip()
    return output.splitlines()[0].strip() if output else None


def _ytdlp_too_old(version_text: str | None) -> bool:
    if not version_text:
        return False
    match = re.search(r"(\d{4})\.(\d{2})\.(\d{2})", version_text)
    if not match:
        return False
    return tuple(int(part) for part in match.groups()) < MIN_YTDLP_VERSION


def check_dependencies() -> DependencyReport:
    """Check that yt-dlp and ffmpeg are available before any screen opens."""
    statuses: list[DependencyStatus] = []
    for tool in ("yt-dlp", "ffmpeg"):
        path = shutil.which(tool)
        version = tool_version(tool) if path else None
        detail = ""
        if tool == "yt-dlp" and _ytdlp_too_old(version):
            detail = f"yt-dlp {version} is old; run 'yt-dlp -U' for best site support."
        statuses.append(
            DependencyStatus(
                tool=tool, path=path, version=version, ok=path is not None, detail=detail
            )
        )
    return DependencyReport(tuple(statuses))


def _stop_process(proc: subprocess.Popen[str], *, grace: float = 5.0) -> None:
    """Terminate a process (and its group on POSIX), escalating to SIGKILL."""
    if proc.poll() is not None:
        return
    try:
        if os.name == "posix":
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        else:  # pragma: no cover - Windows path
            proc.terminate()
    except (ProcessLookupError, PermissionError, OSError):
        try:
            proc.terminate()
        except OSError:
            return
    try:
        proc.wait(timeout=grace)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        if os.name == "posix":
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        else:  # pragma: no cover - Windows path
            proc.kill()
    except (ProcessLookupError, PermissionError, OSError):
        try:
            proc.kill()
        except OSError:
            return
    with contextlib.suppress(subprocess.TimeoutExpired):
        proc.wait(timeout=2)


def _missing_tool(tool: str) -> DownloadError:
    if tool == "ffmpeg":
        return DownloadError(
            "ffmpeg is not installed",
            ErrorReason.FFMPEG_MISSING,
        )
    return DownloadError(
        "yt-dlp is not installed",
        ErrorReason.UNKNOWN,
        hint="Install yt-dlp and make sure it is on PATH.",
        action="Try 'uv tool install yt-dlp' or your package manager.",
    )


def _error_for(url: str, message: str) -> DownloadError:
    """Build a typed error, adding site-specific guidance where useful."""
    reason = classify_error(message)
    hint: str | None = None
    host = (urlparse(url).hostname or "").lower()
    if "403" in message and "tiktok" in host:
        hint = (
            "TikTok blocked this request (HTTP 403). This is TikTok's anti-bot "
            "protection, not a YoinkTUI limit. Log into TikTok in your browser and "
            "launch with --cookies-from-browser, or try a VPN/proxy."
        )
    return DownloadError(message, reason, hint=hint)


def _capture(
    cmd: list[str],
    *,
    timeout: float,
    cancel_check: Callable[[], bool] | None = None,
) -> tuple[int, str, str]:
    """Run a command, capturing output while honouring a timeout/cancel flag."""
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=os.name == "posix",
        )
    except FileNotFoundError as exc:
        raise _missing_tool(cmd[0]) from exc

    stdout_chunks: list[str] = []
    stderr_chunks: list[str] = []

    def _read(stream, chunks: list[str]) -> None:
        assert stream is not None
        # A killed process may close the stream while the thread is reading.
        with contextlib.suppress(OSError):
            chunks.append(stream.read())

    stdout_thread = threading.Thread(target=_read, args=(proc.stdout, stdout_chunks), daemon=True)
    stderr_thread = threading.Thread(target=_read, args=(proc.stderr, stderr_chunks), daemon=True)
    stdout_thread.start()
    stderr_thread.start()

    started = time.monotonic()
    try:
        while proc.poll() is None:
            if cancel_check is not None and cancel_check():
                _stop_process(proc)
                raise DownloadError("Probe cancelled", ErrorReason.CANCELLED)
            if timeout and time.monotonic() - started > timeout:
                _stop_process(proc)
                raise DownloadError(
                    "Timed out while contacting the site",
                    ErrorReason.NETWORK,
                )
            time.sleep(0.05)
    finally:
        stdout_thread.join(timeout=5)
        stderr_thread.join(timeout=5)
        if proc.poll() is None:  # pragma: no cover - defensive
            _stop_process(proc)

    return proc.returncode or 0, "".join(stdout_chunks), "".join(stderr_chunks)


def probe(
    url: str,
    extra_args: list[str] | None = None,
    *,
    timeout: float = 180.0,
    cancel_check: Callable[[], bool] | None = None,
) -> MediaInfo:
    """Fetch metadata + format list without downloading anything."""
    cmd = [
        "yt-dlp",
        "-J",
        "--no-playlist",
        "--no-warnings",
        "--ignore-config",
        "--no-config-locations",
        "--no-exec",
        "--socket-timeout",
        "20",
        *(extra_args or []),
        url,
    ]
    returncode, stdout, stderr = _capture(cmd, timeout=timeout, cancel_check=cancel_check)

    if returncode != 0:
        message = _extract_error(stderr) or "Could not read that URL"
        raise _error_for(url, message)

    import json

    try:
        raw = json.loads(stdout)
    except json.JSONDecodeError as exc:
        message = _extract_error(stderr) or "yt-dlp returned unreadable data"
        raise _error_for(url, message) from exc

    info = MediaInfo.from_dict(raw)
    if not info.video_formats and not info.audio_formats:
        raise DownloadError(
            "No downloadable streams were found",
            ErrorReason.NO_STREAMS,
        )
    return info


def _extract_error(stderr: str) -> str:
    """Pull the most meaningful line out of yt-dlp's stderr."""
    lines = [ln.strip() for ln in (stderr or "").splitlines() if ln.strip()]
    for line in reversed(lines):
        if line.startswith("ERROR"):
            return line.removeprefix("ERROR:").strip()
    return lines[-1] if lines else ""


# ---------------------------------------------------------------------------
# Format selection
# ---------------------------------------------------------------------------


def video_selector(format_id: str | None, cap: int | None) -> str:
    """Build a yt-dlp ``-f`` expression for a video download.

    Always pairs the chosen/limited video with the best audio stream, with a
    progressive fallback so downloads never hard-fail on sparse format tables.
    """
    if format_id:
        return f"{format_id}+ba/{format_id}/b"
    if cap:
        return f"bv*[height<={cap}]+ba/b[height<={cap}]/bv*+ba/b"
    return "bv*+ba/b"


def audio_selector() -> str:
    return "ba/b/bv*"


_MP4_VIDEO_CODECS = ("avc", "hev", "hvc", "av01")
_MP4_AUDIO_CODECS = ("aac", "mp4a", "alac")


def _codec_matches(codec: str, prefixes: tuple[str, ...]) -> bool:
    return codec.lower().startswith(prefixes)


def resolve_merge_format(
    preferred: str,
    video: FormatInfo | None,
    audio: FormatInfo | None,
) -> str:
    """Pick a container, preferring mp4 when the selected streams allow it.

    ``preferred`` is the configured container (``mkv``, ``mp4``, or ``""`` for
    ``auto``).  The mkv default falls back to mp4 only when both sides are
    mp4/aac-compatible, avoiding a needless remux for the common YouTube case.
    """
    if preferred != "mkv" or video is None or not video.has_video:
        return preferred
    if video.ext not in ("mp4", "m4v"):
        return preferred
    if not _codec_matches(video.vcodec, _MP4_VIDEO_CODECS):
        return preferred
    if video.has_audio:
        return "mp4" if _codec_matches(video.acodec, _MP4_AUDIO_CODECS) else preferred
    if audio is not None and _codec_matches(audio.acodec, _MP4_AUDIO_CODECS):
        return "mp4"
    return preferred


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------


def _build_cmd(
    url: str,
    selector: str,
    out_template: str,
    *,
    extract_audio: bool,
    audio_format: str,
    audio_quality: str,
    merge_format: str,
    extra_args: list[str],
    section: Section | None = None,
    concurrent_fragments: int = 0,
    rate_limit: str = "",
    write_subtitles: bool = False,
    embed_metadata: bool = False,
    embed_thumbnail: bool = False,
    keep_original: bool = False,
) -> list[str]:
    cmd = [
        "yt-dlp",
        "-f",
        selector,
        "-o",
        out_template,
        "--no-playlist",
        "--no-warnings",
        "--ignore-config",
        "--no-config-locations",
        "--no-exec",
        "--newline",
        "--no-quiet",
        "--progress-delta",
        "0.2",
        "--progress-template",
        DL_TEMPLATE,
        "--progress-template",
        PP_TEMPLATE,
        "--print",
        "after_move:FINAL|%(filepath)s",
    ]
    if concurrent_fragments > 0:
        cmd += ["--concurrent-fragments", str(concurrent_fragments)]
    if rate_limit:
        cmd += ["--limit-rate", rate_limit]
    if section is not None:
        cmd += ["--download-sections", section_spec(section)]
        if section.precise:
            cmd += ["--force-keyframes-at-cuts"]
    if merge_format:
        cmd += ["--merge-output-format", merge_format]
    if extract_audio:
        cmd += ["-x", "--audio-format", audio_format]
        if audio_quality:
            cmd += ["--audio-quality", audio_quality]
    else:
        if write_subtitles:
            cmd += ["--write-subs"]
        if keep_original:
            cmd += ["--keep-video"]
    if embed_metadata:
        cmd += ["--embed-metadata"]
    if embed_thumbnail:
        cmd += ["--embed-thumbnail"]
    if extra_args:
        cmd += extra_args
    cmd.append(url)
    return cmd


def _parse_line(line: str) -> ProgressEvent | None:
    """Decode one stdout line, or return ``None`` for untracked noise."""
    if line.startswith("DL|"):
        parts = line.split("|", 6)
        if len(parts) < 4:
            return None
        # Fields: DL | status | downloaded | total | total_estimate | speed | eta
        total = _to_float(parts[3]) if len(parts) > 3 else None
        estimate = _to_float(parts[4]) if len(parts) > 4 else None
        total = total or estimate or None
        return ProgressEvent(
            kind="download",
            status=parts[1],
            downloaded=_to_float(parts[2]) or 0.0,
            total=total,
            speed=_to_float(parts[5]) if len(parts) > 5 else None,
            eta=_to_float(parts[6]) if len(parts) > 6 else None,
        )
    if line.startswith("PP|"):
        parts = line.split("|", 4)
        return ProgressEvent(
            kind="postprocess",
            status=parts[1] if len(parts) > 1 else "",
            section=_clean(parts[2]) if len(parts) > 2 else "",
            filename=_clean(parts[3]) if len(parts) > 3 else "",
        )
    if line.startswith("FINAL|"):
        return ProgressEvent(kind="done", filename=line.split("|", 1)[1].strip())
    stripped = line.strip()
    if not stripped:
        return None
    return ProgressEvent(kind="log", text=stripped)


def _download_once(
    url: str,
    *,
    selector: str,
    out_template: str,
    extract_audio: bool = False,
    audio_format: str = "mp3",
    audio_quality: str = "0",
    merge_format: str = "mkv",
    extra_args: list[str] | None = None,
    section: Section | None = None,
    expected_bytes: float | None = None,
    cancel_check=None,
    control: DownloadControl | None = None,
    concurrent_fragments: int = 0,
    rate_limit: str = "",
    write_subtitles: bool = False,
    embed_metadata: bool = False,
    embed_thumbnail: bool = False,
    keep_original: bool = False,
    stall_timeout: float = 300.0,
) -> Iterator[ProgressEvent]:
    """Run one yt-dlp attempt and stream its progress events."""
    cmd = _build_cmd(
        url,
        selector,
        out_template,
        extract_audio=extract_audio,
        audio_format=audio_format,
        audio_quality=audio_quality,
        merge_format=merge_format,
        extra_args=list(extra_args or []),
        section=section,
        concurrent_fragments=concurrent_fragments,
        rate_limit=rate_limit,
        write_subtitles=write_subtitles,
        embed_metadata=embed_metadata,
        embed_thumbnail=embed_thumbnail,
        keep_original=keep_original,
    )

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            start_new_session=os.name == "posix",
        )
    except FileNotFoundError as exc:
        raise _missing_tool("yt-dlp") from exc

    if control is not None:
        control.attach(proc)

    monitor = _FileProgressMonitor(out_template, expected_bytes) if section is not None else None

    # Drain stdout on its own thread so the main loop can sample the output
    # file while a section download is running (yt-dlp is quiet during those).
    stdout_queue: queue.Queue[str | None] = queue.Queue()

    def _drain_stdout() -> None:
        assert proc.stdout is not None
        try:
            for out_line in proc.stdout:
                stdout_queue.put(out_line)
        finally:
            stdout_queue.put(None)

    # Drain stderr on its own thread so a chatty warning can't deadlock us.
    stderr_lines: list[str] = []

    def _drain_stderr() -> None:
        assert proc.stderr is not None
        for err_line in proc.stderr:
            stderr_lines.append(err_line.rstrip())

    stdout_thread = threading.Thread(target=_drain_stdout, daemon=True)
    stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
    stdout_thread.start()
    stderr_thread.start()

    def _is_cancelled() -> bool:
        if control is not None and control.cancelled:
            return True
        return bool(cancel_check is not None and cancel_check())

    def _terminate() -> None:
        if control is not None:
            control.resume()
        _stop_process(proc)

    finished_path = ""
    last_activity = time.monotonic()
    try:
        while True:
            if _is_cancelled():
                _terminate()
                yield ProgressEvent(kind="error", text="Cancelled")
                return

            if stall_timeout and time.monotonic() - last_activity > stall_timeout:
                _terminate()
                raise DownloadError(
                    f"No output for {int(stall_timeout)} seconds; the download looks stalled",
                    ErrorReason.NETWORK,
                )

            try:
                raw_line = stdout_queue.get(timeout=0.5)
            except queue.Empty:
                if monitor is not None:
                    progress = monitor.poll()
                    if progress is not None:
                        last_activity = time.monotonic()
                        yield progress
                continue

            if raw_line is None:
                break

            last_activity = time.monotonic()
            line = raw_line.rstrip("\n")
            event = _parse_line(line)
            if event is None:
                if monitor is not None:
                    progress = monitor.poll()
                    if progress is not None:
                        last_activity = time.monotonic()
                        yield progress
                continue
            if event.kind == "done" and event.filename:
                finished_path = event.filename
            if event.kind in ("done", "error") or (
                event.kind == "download" and event.status == "finished"
            ):
                monitor = None
            yield event
            if monitor is not None:
                progress = monitor.poll()
                if progress is not None:
                    last_activity = time.monotonic()
                    yield progress
    finally:
        stdout_thread.join(timeout=5)
        stderr_thread.join(timeout=5)
        if proc.poll() is None:
            _stop_process(proc)
        if control is not None:
            control.detach()

    if control is not None and control.cancelled:
        yield ProgressEvent(kind="error", text="Cancelled")
        return

    if proc.returncode not in (0, None) and not finished_path:
        message = _extract_error("\n".join(stderr_lines))
        raise _error_for(url, message or f"yt-dlp exited with code {proc.returncode}")

    if finished_path:
        yield ProgressEvent(kind="done", filename=finished_path)


def download(
    url: str,
    *,
    selector: str,
    out_template: str,
    extract_audio: bool = False,
    audio_format: str = "mp3",
    audio_quality: str = "0",
    merge_format: str = "mkv",
    extra_args: list[str] | None = None,
    section: Section | None = None,
    expected_bytes: float | None = None,
    cancel_check=None,
    control: DownloadControl | None = None,
    concurrent_fragments: int = 0,
    rate_limit: str = "",
    write_subtitles: bool = False,
    embed_metadata: bool = False,
    embed_thumbnail: bool = False,
    keep_original: bool = False,
    stall_timeout: float = 300.0,
    retries: int = 2,
    retry_backoff: float = 1.0,
) -> Iterator[ProgressEvent]:
    """Yield :class:`ProgressEvent`s while yt-dlp runs.

    ``cancel_check`` is polled periodically; returning True aborts.
    ``control`` offers thread-safe pause/resume/cancel from another thread.
    ``section`` limits the download to a start/end time range.
    ``expected_bytes`` is a size estimate for section downloads, whose
    downloader does not report live progress itself.
    ``retries`` re-runs the process after transient network failures, with a
    linear backoff of ``retry_backoff * attempt`` seconds.
    """
    attempt = 0
    while True:
        try:
            yield from _download_once(
                url,
                selector=selector,
                out_template=out_template,
                extract_audio=extract_audio,
                audio_format=audio_format,
                audio_quality=audio_quality,
                merge_format=merge_format,
                extra_args=extra_args,
                section=section,
                expected_bytes=expected_bytes,
                cancel_check=cancel_check,
                control=control,
                concurrent_fragments=concurrent_fragments,
                rate_limit=rate_limit,
                write_subtitles=write_subtitles,
                embed_metadata=embed_metadata,
                embed_thumbnail=embed_thumbnail,
                keep_original=keep_original,
                stall_timeout=stall_timeout,
            )
            return
        except DownloadError as exc:
            cancelled = (
                exc.reason is ErrorReason.CANCELLED
                or (control is not None and control.cancelled)
                or bool(cancel_check is not None and cancel_check())
            )
            if exc.reason is ErrorReason.NETWORK and attempt < retries and not cancelled:
                attempt += 1
                yield ProgressEvent(
                    kind="log",
                    text=f"Network error: {exc.message}. Retrying ({attempt}/{retries})…",
                )
                time.sleep(retry_backoff * attempt)
                continue
            raise
