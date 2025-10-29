"""Unit tests for notification worker helper logic."""

from datetime import datetime, timezone

from app.core.config import settings
from app.db.models import NotificationJob
from app.services.notification_worker import (
    _apply_delivery_failure,
    _apply_delivery_success,
    _compute_backoff,
)


def _make_job(status: str = "pending", retry_count: int = 0) -> NotificationJob:
    return NotificationJob(
        video_id=1,
        subscriber_id=1,
        status=status,
        retry_count=retry_count,
        next_retry_at=None,
        last_error=None,
        created_at=datetime.now(timezone.utc),
    )


def test_compute_backoff_doubles_each_retry():
    assert _compute_backoff(5, 1).total_seconds() == 300
    assert _compute_backoff(5, 2).total_seconds() == 600
    assert _compute_backoff(5, 3).total_seconds() == 1200


def test_apply_delivery_success_sets_delivered_state():
    job = _make_job()
    job.retry_count = 2
    job.last_error = "boom"
    _apply_delivery_success(job)
    assert job.status == "delivered"
    assert job.retry_count == 0
    assert job.last_error is None
    assert job.next_retry_at is None
    assert job.delivered_at is not None


def test_apply_delivery_failure_schedules_retry():
    job = _make_job()
    _apply_delivery_failure(job, RuntimeError("smtp down"))
    assert job.status == "pending"
    assert job.retry_count == 1
    assert job.next_retry_at is not None
    assert "smtp down" in (job.last_error or "")


def test_apply_delivery_failure_marks_failed_when_exhausted():
    job = _make_job(retry_count=settings.notify_max_retry - 1)
    _apply_delivery_failure(job, RuntimeError("fail"))
    assert job.status == "failed"
    assert job.next_retry_at is None
