"""Tests for pause/resume/cancel process control (POSIX)."""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

from yoinktui.backend.ytdlp import DownloadControl


@pytest.mark.skipif(os.name != "posix", reason="process groups are POSIX-only")
def test_pause_resume_cancel() -> None:
    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        start_new_session=True,
    )
    control = DownloadControl()
    control.attach(proc)
    try:
        assert control.pause() is True
        assert control.paused is True
        assert proc.poll() is None

        assert control.resume() is True
        assert control.paused is False

        control.cancel()
        proc.wait(timeout=10)
        assert proc.returncode is not None
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)


def test_detach_keeps_state_consistent() -> None:
    control = DownloadControl()
    control.detach()
    assert control.paused is False
    # Without an attached process these are safe no-ops.  ``resume`` reports
    # "now running", which is true even when nothing was paused.
    assert control.pause() is False
    assert control.resume() is True
