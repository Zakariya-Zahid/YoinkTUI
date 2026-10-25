"""Tests for the yt-dlp command builder."""

from __future__ import annotations

from yoinktui.backend.ytdlp import Section, _build_cmd


def _base_cmd(**overrides):
    kwargs = {
        "extract_audio": False,
        "audio_format": "mp3",
        "audio_quality": "0",
        "merge_format": "mkv",
        "extra_args": [],
    }
    kwargs.update(overrides)
    return _build_cmd(
        "https://example.com/video",
        "bv*+ba/b",
        "/tmp/demo.%(ext)s",
        **kwargs,
    )


def test_safety_and_reproducibility_flags() -> None:
    cmd = _base_cmd()
    assert "--no-config-locations" in cmd
    assert "--no-exec" in cmd
    assert "--ignore-config" in cmd
    assert cmd[-1] == "https://example.com/video"


def test_resume_flag_is_always_enabled() -> None:
    cmd = _base_cmd()
    assert "--continue" in cmd
    assert "--no-overwrites" not in cmd


def test_policy_flags_are_opt_in() -> None:
    cmd = _base_cmd()
    assert "--concurrent-fragments" not in cmd
    assert "--limit-rate" not in cmd
    assert "--write-subs" not in cmd

    cmd = _base_cmd(
        concurrent_fragments=4,
        rate_limit="5M",
        write_subtitles=True,
        embed_metadata=True,
        embed_thumbnail=True,
        keep_original=True,
    )
    assert cmd[cmd.index("--concurrent-fragments") + 1] == "4"
    assert cmd[cmd.index("--limit-rate") + 1] == "5M"
    assert "--write-subs" in cmd
    assert "--embed-metadata" in cmd
    assert "--embed-thumbnail" in cmd
    assert "--keep-video" in cmd


def test_audio_mode_uses_extraction_flags() -> None:
    cmd = _base_cmd(
        extract_audio=True,
        audio_format="m4a",
        audio_quality="2",
        write_subtitles=True,
        keep_original=True,
    )
    assert "-x" in cmd
    assert cmd[cmd.index("--audio-format") + 1] == "m4a"
    assert cmd[cmd.index("--audio-quality") + 1] == "2"
    # Subtitles and intermediate video files are meaningless for audio-only.
    assert "--write-subs" not in cmd
    assert "--keep-video" not in cmd


def test_section_flags() -> None:
    section = Section(start=30, end=90, precise=True)
    cmd = _base_cmd(section=section)
    assert cmd[cmd.index("--download-sections") + 1] == "*00:00:30-00:01:30"
    assert "--force-keyframes-at-cuts" in cmd


def test_merge_format_omitted_when_auto() -> None:
    cmd = _base_cmd(merge_format="")
    assert "--merge-output-format" not in cmd


def test_extra_args_are_passed_before_url() -> None:
    cmd = _base_cmd(extra_args=["--proxy", "socks5://127.0.0.1:1080"])
    proxy_at = cmd.index("--proxy")
    assert cmd[proxy_at + 1] == "socks5://127.0.0.1:1080"
    assert proxy_at < cmd.index("https://example.com/video")
