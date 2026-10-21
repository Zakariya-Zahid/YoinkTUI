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

import os
import shutil
import signal
import subprocess
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from yoinktui.backend.models import MediaInfo

ProgressKind = Literal["status", "download", "postprocess", "log", "done", "error"]

DL_TEMPLATE = (
    "download:DL|%(progress.status)s|%(progress.downloaded_bytes)s|"
    "%(progress.total_bytes)s|%(progress.total_bytes_estimate)s|"
    "%(progress.speed)s|%(progress.eta)s"
)
PP_TEMPLATE = "postprocess:PP|%(progress.status)s|%(progress.section_name)s|%(progress.filename)s"


class BackendError(RuntimeError):
    """Raised when yt-dlp fails; ``message`` is safe to show in the UI."""


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


def _friendly_error(url: str, message: str) -> str:
    """Append a useful hint to common site-side blocks."""
    if "403" not in message:
        return message

    host = (urlparse(url).hostname or "").lower()
    if "tiktok" in host:
        hint = (
            "TikTok blocked this request (HTTP 403). This is TikTok's anti-bot "
            "protection, not a YoinkTUI limit. Log into TikTok in your browser and "
            "launch with --cookies-from-browser, or try a VPN/proxy."
        )
    else:
        hint = (
            "The site blocked this request (HTTP 403). Cookies or a different "
            "network may help."
        )
    return f"{message}\n\n{hint}"


def probe(url: str, extra_args: list[str] | None = None) -> MediaInfo:
    """Fetch metadata + format list without downloading anything."""
    cmd = [
        "yt-dlp",
        "-J",
        "--no-playlist",
        "--no-warnings",
        "--ignore-config",
        "--socket-timeout", "20",
        *(extra_args or []),
        url,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    except FileNotFoundError as exc:  # pragma: no cover - dependency guard
        raise BackendError("yt-dlp is not installed") from exc
    except subprocess.TimeoutExpired as exc:
        raise BackendError("Timed out while contacting the site") from exc

    if proc.returncode != 0:
        message = _extract_error(proc.stderr) or "Could not read that URL"
        raise BackendError(_friendly_error(url, message))

    import json

    try:
        raw = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise BackendError("yt-dlp returned unreadable data") from exc

    info = MediaInfo.from_dict(raw)
    if not info.video_formats and not info.audio_formats:
        raise BackendError("No downloadable streams were found")
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
) -> list[str]:
    cmd = [
        "yt-dlp",
        "-f", selector,
        "-o", out_template,
        "--no-playlist",
        "--no-warnings",
        "--ignore-config",
        "--newline",
        "--no-quiet",
        "--progress-delta", "0.2",
        "--progress-template", DL_TEMPLATE,
        "--progress-template", PP_TEMPLATE,
        "--print", "after_move:FINAL|%(filepath)s",
    ]
    if merge_format:
        cmd += ["--merge-output-format", merge_format]
    if extract_audio:
        cmd += ["-x", "--audio-format", audio_format]
        if audio_quality:
            cmd += ["--audio-quality", audio_quality]
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
        return ProgressEvent(
            kind="download",
            status=parts[1],
            downloaded=_to_float(parts[2]) or 0.0,
            total=total or estimate,
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
    cancel_check=None,
    control: DownloadControl | None = None,
) -> Iterator[ProgressEvent]:
    """Yield :class:`ProgressEvent`s while yt-dlp runs.

    ``cancel_check`` is polled once per output line; returning True aborts.
    ``control`` offers thread-safe pause/resume/cancel from another thread.
    """
    cmd = _build_cmd(
        url,
        selector,
        out_template,
        extract_audio=extract_audio,
        audio_format=audio_format,
        audio_quality=audio_quality,
        merge_format=merge_format,
        extra_args=list(extra_args or []),
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
    except FileNotFoundError as exc:  # pragma: no cover
        raise BackendError("yt-dlp is not installed") from exc

    if control is not None:
        control.attach(proc)

    # Drain stderr on its own thread so a chatty warning can't deadlock us.
    stderr_lines: list[str] = []

    def _drain_stderr() -> None:
        assert proc.stderr is not None
        for err_line in proc.stderr:
            stderr_lines.append(err_line.rstrip())
        # Closing here unblocks wait() once stdout is exhausted.

    t = threading.Thread(target=_drain_stderr, daemon=True)
    t.start()

    def _is_cancelled() -> bool:
        if control is not None and control.cancelled:
            return True
        return bool(cancel_check is not None and cancel_check())

    assert proc.stdout is not None
    finished_path = ""
    try:
        for raw_line in proc.stdout:
            if _is_cancelled():
                if control is not None:
                    control.resume()
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                yield ProgressEvent(kind="error", text="Cancelled")
                return

            line = raw_line.rstrip("\n")
            event = _parse_line(line)
            if event is None:
                continue
            if event.kind == "done" and event.filename:
                finished_path = event.filename
            yield event
    finally:
        t.join(timeout=5)
        if proc.poll() is None:
            proc.kill()
        if control is not None:
            control.detach()

    if control is not None and control.cancelled:
        yield ProgressEvent(kind="error", text="Cancelled")
        return

    if proc.returncode not in (0, None) and not finished_path:
        message = _extract_error("\n".join(stderr_lines))
        raise BackendError(
            _friendly_error(url, message or f"yt-dlp exited with code {proc.returncode}")
        )

    if finished_path:
        yield ProgressEvent(kind="done", filename=finished_path)
