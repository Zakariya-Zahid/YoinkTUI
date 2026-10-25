"""Queue policy, serialization, and resume persistence."""

from __future__ import annotations

from pathlib import Path

from yoinktui.backend.config import AppConfig
from yoinktui.backend.models import FormatInfo, MediaInfo
from yoinktui.backend.presets import Preset
from yoinktui.backend.queue import (
    DownloadPolicy,
    DownloadQueue,
    QueueItem,
    QueueStore,
    safe_filename,
)


def _info() -> MediaInfo:
    return MediaInfo(
        id="abc",
        title="Demo: a useful video",
        uploader="Creator",
        webpage_url="https://example.com/v",
        video_formats=[
            FormatInfo(
                format_id="137",
                ext="mp4",
                vcodec="avc1",
                acodec="none",
                height=1080,
                filesize=100_000_000,
            ),
            FormatInfo(
                format_id="22",
                ext="mp4",
                vcodec="avc1",
                acodec="mp4a",
                height=720,
                filesize=50_000_000,
            ),
        ],
        audio_formats=[
            FormatInfo(
                format_id="140",
                ext="m4a",
                vcodec="none",
                acodec="mp4a",
                abr=128,
                filesize=2_000_000,
            )
        ],
    )


def test_policy_from_config_uses_preset_and_config(tmp_path: Path) -> None:
    config = AppConfig(download_dir=tmp_path, quality_cap=720)
    policy = DownloadPolicy.from_config(
        config,
        Preset(name="phone", mode="video", quality_cap=480, container="mp4"),
    )
    assert policy.mode == "video"
    assert policy.quality_cap == 480
    assert policy.container == "mp4"
    assert policy.merge_format == "mp4"
    assert policy.download_dir == tmp_path


def test_policy_selector_modes() -> None:
    audio = DownloadPolicy(mode="audio")
    vonly = DownloadPolicy(mode="vonly", quality_cap=720)
    video = DownloadPolicy(mode="video", quality_cap=1080)
    assert "ba" in audio.default_selector()
    assert "height<=720" in vonly.default_selector()
    assert "bv" in video.default_selector()


def test_queue_item_from_media_keeps_selection_and_policy(tmp_path: Path) -> None:
    info = _info()
    policy = DownloadPolicy.from_config(AppConfig(download_dir=tmp_path))
    item = QueueItem.from_media(
        info,
        policy,
        selected_format=info.video_formats[0],
        expected_bytes=12.5,
    )
    assert item.url == "https://example.com/v"
    # The selected row is video-only; Video+Audio mode must request audio too.
    assert item.selector == "137+ba/137/b"
    assert item.merge_format == "mp4"
    assert item.expected_bytes == 12.5
    assert item.out_template.endswith(".%(ext)s")
    assert "Demo" in item.out_template
    assert item.status == "pending"


def test_queue_item_keeps_muxed_selection_without_extra_audio(tmp_path: Path) -> None:
    info = _info()
    policy = DownloadPolicy.from_config(AppConfig(download_dir=tmp_path))
    item = QueueItem.from_media(
        info,
        policy,
        selected_format=info.video_formats[1],
    )
    assert item.selector == "22"


def test_queue_item_video_only_mode_keeps_selected_video(tmp_path: Path) -> None:
    info = _info()
    policy = DownloadPolicy(mode="vonly", download_dir=tmp_path)
    item = QueueItem.from_media(
        info,
        policy,
        selected_format=info.video_formats[0],
    )
    assert item.selector == "137"


def test_queue_item_from_playlist_entry(tmp_path: Path) -> None:
    from yoinktui.backend.ytdlp import PlaylistEntry

    policy = DownloadPolicy(
        mode="audio",
        download_dir=tmp_path,
        audio_format="m4a",
        container="mkv",
    )
    item = QueueItem.from_entry(
        PlaylistEntry(
            url="https://example.com/watch?v=one",
            title="Episode One",
            id="one",
            uploader="Channel",
        ),
        policy,
    )
    assert item.url.endswith("one")
    assert item.extract_audio is True
    assert item.audio_format == "m4a"
    assert item.title == "Episode One"


def test_queue_roundtrip_and_resume_status(tmp_path: Path) -> None:
    store = QueueStore(tmp_path / "queue.json")
    queue = DownloadQueue()
    item = QueueItem(
        url="https://example.com/v",
        title="Demo",
        section=None,
        status="running",
        extra_args=["--proxy", "http://localhost:8080"],
    )
    queue.add(item)
    store.save(queue)

    loaded = store.load()
    assert len(loaded.items) == 1
    assert loaded.items[0].status == "interrupted"
    assert loaded.items[0].extra_args == ["--proxy", "http://localhost:8080"]
    assert loaded.has_resumable()
    assert loaded.pending_count() == 0


def test_queue_store_corrupt_file_is_empty(tmp_path: Path) -> None:
    path = tmp_path / "queue.json"
    path.write_text("{not json", encoding="utf-8")
    assert QueueStore(path).load().items == []


def test_queue_store_repairs_or_skips_malformed_items(tmp_path: Path) -> None:
    path = tmp_path / "queue.json"
    path.write_text(
        '{"version": 1, "items": ['
        '{"url": "https://example.com/ok", "title": "Ok"},'
        '{"url": "https://example.com/bad", "expected_bytes": "nope"},'
        '{"title": "No URL"}'
        "]}",
        encoding="utf-8",
    )
    queue = QueueStore(path).load()
    # Bad numeric fields are repaired; items with no URL are skipped.
    assert len(queue.items) == 2
    assert queue.items[1].expected_bytes is None


def test_clear_finished_keeps_resumable() -> None:
    queue = DownloadQueue(
        items=[
            QueueItem(url="https://example.com/a", status="done"),
            QueueItem(url="https://example.com/b", status="failed"),
            QueueItem(url="https://example.com/c", status="interrupted"),
        ]
    )
    assert queue.clear_finished() == 1
    assert [item.status for item in queue.items] == ["failed", "interrupted"]


def test_safe_filename_strips_unsafe_characters() -> None:
    assert safe_filename("a/b:c?d*e") == "abcde"
    assert safe_filename("   ") == "video"
