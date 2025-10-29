"""Background worker that turns transcripts into summaries."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.db.models import NotificationJob, SubscriberChannel, Summary, Video
from app.db.session import SessionLocal
from app.services.summariser_utils import (
    SummaryResult,
    generate_summary_from_transcript,
    generate_summary_via_openai,
)

logger = logging.getLogger(__name__)


def _ensure_summary_record(session: AsyncSession, video: Video) -> Summary:
    summary = video.summary
    if summary is None:
        summary = Summary(
            video_id=video.id,
            tl_dr="",
            highlights=None,
            key_quote=None,
            summary_status="pending",
            summary_retry_count=0,
            summary_last_error=None,
        )
        session.add(summary)
        video.summary = summary
    return summary


def _apply_summary_success(video: Video, summary: Summary, result: SummaryResult) -> None:
    now = datetime.now(timezone.utc)
    summary.tl_dr = result.tl_dr
    summary.highlights = "\n".join(result.highlights)
    summary.key_quote = result.key_quote
    summary.summary_status = "ready"
    summary.summary_retry_count = 0
    summary.summary_last_error = None
    video.summary_ready_at = now


def _apply_summary_failure(summary: Summary, error: Exception) -> None:
    summary.summary_retry_count += 1
    summary.summary_last_error = str(error)
    if summary.summary_retry_count >= settings.summary_max_retry:
        summary.summary_status = "failed"
    else:
        summary.summary_status = "pending"


def _select_generator() -> Callable[[str], SummaryResult]:
    if settings.openai_api_key:
        return generate_summary_via_openai
    return generate_summary_from_transcript


async def process_pending_summaries(
    session: AsyncSession,
    *,
    batch_size: int = 5,
    generator: Callable[[str], SummaryResult] | None = None,
) -> list[Summary]:
    """Process videos with ready transcripts but missing summaries."""

    stmt = (
        select(Video)
        .options(selectinload(Video.summary))
        .where(Video.transcript_status == "ready")
        .order_by(Video.summary_ready_at.is_(None).desc(), Video.id)
        .limit(batch_size)
    )
    result = await session.execute(stmt)
    videos = list(result.scalars())

    updated: list[Summary] = []

    for video in videos:
        summary = _ensure_summary_record(session, video)

        if summary.summary_status == "ready":
            continue
        if summary.summary_status == "failed" and summary.summary_retry_count >= settings.summary_max_retry:
            continue

        if not video.transcript_text:
            _apply_summary_failure(summary, ValueError("Missing transcript text"))
            updated.append(summary)
            continue

        chosen_generator = generator or _select_generator()

        try:
            result = chosen_generator(video.transcript_text)
            _apply_summary_success(video, summary, result)
        except Exception as exc:
            if generator is None and chosen_generator is generate_summary_via_openai:
                logger.exception(
                    "LLM summary failed, falling back to heuristic",
                    extra={"video_id": video.youtube_id},
                )
                try:
                    result = generate_summary_from_transcript(video.transcript_text)
                    _apply_summary_success(video, summary, result)
                except Exception as fallback_exc:  # pragma: no cover - defensive guard
                    logger.exception(
                        "Fallback summary generation failed",
                        extra={"video_id": video.youtube_id},
                    )
                    _apply_summary_failure(summary, fallback_exc)
            else:
                logger.exception(
                    "Summary generation failed",
                    extra={"video_id": video.youtube_id},
                )
                _apply_summary_failure(summary, exc)

        updated.append(summary)

    await session.flush()
    await _queue_notification_jobs(session, [video for video in videos if video.summary])
    return updated


async def _queue_notification_jobs(session: AsyncSession, videos: list[Video]) -> None:
    """Create notification jobs for summaries that are ready."""

    for video in videos:
        summary = video.summary
        if summary is None or summary.summary_status != "ready":
            continue

        subscriber_ids = (
            await session.execute(
                select(SubscriberChannel.subscriber_id).where(
                    SubscriberChannel.channel_id == video.channel_id
                )
            )
        ).scalars().all()

        for subscriber_id in subscriber_ids:
            exists = await session.scalar(
                select(NotificationJob).where(
                    NotificationJob.video_id == video.id,
                    NotificationJob.subscriber_id == subscriber_id,
                )
            )
            if exists:
                continue

            job = NotificationJob(
                video_id=video.id,
                subscriber_id=subscriber_id,
                status="pending",
                retry_count=0,
                next_retry_at=datetime.now(timezone.utc),
            )
            session.add(job)

    await session.flush()


class SummariserWorker:
    """Background loop for summary generation."""

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    async def _run(self) -> None:
        idle_sleep = 30
        active_sleep = 3

        while not self._stop_event.is_set():
            try:
                async with SessionLocal() as session:
                    summaries = await process_pending_summaries(session)
                    if summaries:
                        await session.commit()
                    else:
                        await session.rollback()
            except Exception:  # pragma: no cover - defensive guard
                logger.exception("Summariser worker iteration failed")
                await asyncio.sleep(idle_sleep)
                continue

            await asyncio.sleep(active_sleep if summaries else idle_sleep)

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stop_event.set()
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:  # pragma: no cover - event loop behaviour
            pass
        finally:
            self._task = None


summariser_worker = SummariserWorker()


def start_summariser_worker() -> None:
    """Public entry for FastAPI startup."""

    summariser_worker.start()


async def stop_summariser_worker() -> None:
    """Public entry for FastAPI shutdown."""

    await summariser_worker.stop()

