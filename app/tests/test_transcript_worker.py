"""Unit tests for transcript worker helper functions."""

from __future__ import annotations

from datetime import datetime, timezone
import time

import pytest

pytest_plugins = ("pytest_asyncio",)

from app.db.models import Video
from app.services.transcript_worker import (
    TranscriptResult,
    _throttle_requests,
    _apply_permanent_failure,
    _apply_retry,
    _apply_success,
    compute_backoff,
)


def _make_video() -> Video:
    return Video(channel_id=1, youtube_id="VID123", title="Video Title")


def test_compute_backoff_exponential():
    assert compute_backoff(5, 1).total_seconds() == 300
    assert compute_backoff(5, 2).total_seconds() == 600
    assert compute_backoff(5, 3).total_seconds() == 1200


def test_apply_success_sets_ready_state():
    video = _make_video()
    now = datetime.now(timezone.utc)
    result = TranscriptResult(text="hello world", language_code="en")

    _apply_success(video, result, now=now)

    assert video.transcript_status == "ready"
    assert video.transcript_text == "hello world"
    assert video.transcript_lang == "en"
    assert video.retry_count == 0
    assert video.next_retry_at is None
    assert video.last_error is None
    assert video.fetched_transcript_at == now


def test_apply_retry_schedules_next_attempt():
    video = _make_video()
    now = datetime.now(timezone.utc)

    _apply_retry(video, RuntimeError("boom"), now=now, base_minutes=5, max_retry=3)

    assert video.transcript_status == "pending"
    assert video.retry_count == 1
    assert video.next_retry_at is not None
    assert video.next_retry_at > now
    assert "boom" in (video.last_error or "")


def test_apply_retry_marks_failed_after_max():
    video = _make_video()
    video.retry_count = 2
    now = datetime.now(timezone.utc)

    _apply_retry(video, RuntimeError("fail"), now=now, base_minutes=5, max_retry=3)

    assert video.transcript_status == "failed"
    assert video.next_retry_at is None


def test_permanent_failure_marks_failed_immediately():
    video = _make_video()
    now = datetime.now(timezone.utc)

    _apply_permanent_failure(video, RuntimeError("disabled"), now=now)

    assert video.transcript_status == "failed"
    assert video.retry_count == 1
    assert video.next_retry_at is None
    assert video.fetched_transcript_at == now


@pytest.mark.asyncio
async def test_throttle_respects_min_interval():
    from app.core.config import settings
    from app.services import transcript_worker as worker

    previous_interval = settings.transcript_min_interval_ms
    previous_last = worker._last_fetch_monotonic
    try:
        settings.transcript_min_interval_ms = 100
        worker._last_fetch_monotonic = time.monotonic()
        start = time.monotonic()
        await _throttle_requests()
        elapsed = time.monotonic() - start
        assert elapsed >= 0.09
    finally:
        settings.transcript_min_interval_ms = previous_interval
        worker._last_fetch_monotonic = previous_last
