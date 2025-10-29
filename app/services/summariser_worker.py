"""Background worker that turns transcripts into summaries."""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.db.models import NotificationJob, SubscriberChannel, Summary, Video
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SummaryResult:
    """Represents an LLM-style summary of a transcript."""

    tl_dr: str
    highlights: list[str]
    key_quote: str | None


def _split_sentences(text: str) -> list[str]:
    """Naively split text into sentences."""

    text = text.strip()
    if not text:
        return []
    sentences = re.split(r"(?<=[.!?])\s+", text)
    return [sentence.strip() for sentence in sentences if sentence.strip()]


def generate_summary_from_transcript(transcript: str) -> SummaryResult:
    """Generate a simple summary using heuristic rules."""

    sentences = _split_sentences(transcript)
    if not sentences:
        raise ValueError("Transcript is empty")

    tl_dr = " ".join(sentences[:2]) if len(sentences) > 1 else sentences[0]

    highlights: list[str] = []
    for sentence in sentences:
        if len(highlights) >= 4:
            break
        highlights.append(sentence)

    key_quote = max(sentences, key=len)
    return SummaryResult(tl_dr=tl_dr, highlights=highlights, key_quote=key_quote)


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


async def process_pending_summaries(
    session: AsyncSession,
    *,
    batch_size: int = 5,
    generator: Callable[[str], SummaryResult] = generate_summary_from_transcript,
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

        try:
            result = generator(video.transcript_text)
            _apply_summary_success(video, summary, result)
        except Exception as exc:  # pragma: no cover - defensive guard
            logger.exception("Summary generation failed", extra={"video_id": video.youtube_id})
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
