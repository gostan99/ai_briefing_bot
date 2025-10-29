"""Background worker responsible for fetching YouTube transcripts."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from youtube_transcript_api import (  # type: ignore[import-not-found]
    NoTranscriptFound,
    TranscriptsDisabled,
    YouTubeTranscriptApi,
)

from app.core.config import settings
from app.db.models import Video
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class TranscriptResult:
    """Represents a fetched transcript for a video."""

    text: str
    language_code: str | None


_max_concurrency = max(settings.transcript_max_concurrency, 1)
_fetch_semaphore = asyncio.Semaphore(_max_concurrency)
_rate_lock = asyncio.Lock()
_last_fetch_monotonic = 0.0


async def _throttle_requests() -> None:
    """Ensure a minimum delay between outbound transcript requests."""

    global _last_fetch_monotonic

    min_interval = max(settings.transcript_min_interval_ms, 0) / 1000.0
    if min_interval <= 0:
        return

    async with _rate_lock:
        now = time.monotonic()
        sleep_for = (_last_fetch_monotonic + min_interval) - now
        if sleep_for > 0:
            await asyncio.sleep(sleep_for)
            now = time.monotonic()
        _last_fetch_monotonic = now


def compute_backoff(base_minutes: int, retry_count: int) -> timedelta:
    """Return exponential backoff delay for the given retry count."""

    base_minutes = max(base_minutes, 1)
    exponent = max(retry_count - 1, 0)
    return timedelta(minutes=base_minutes * (2**exponent))


async def fetch_transcript(video_id: str) -> TranscriptResult:
    """Fetch a transcript for the given YouTube video id."""

    loop = asyncio.get_running_loop()

    def _blocking_fetch() -> TranscriptResult:
        try:
            segments = YouTubeTranscriptApi.get_transcript(video_id, languages=["en", "en-US", "en-GB"])
        except TranscriptsDisabled as exc:  # pragma: no cover - depends on YouTube responses
            raise
        except NoTranscriptFound as exc:  # pragma: no cover - depends on YouTube responses
            raise

        if not segments:
            raise NoTranscriptFound("Transcript returned no segments")

        parts: list[str] = []
        for segment in segments:
            text = (segment.get("text") or "").strip()
            if text:
                parts.append(text)

        language = segments[0].get("language_code") or segments[0].get("language")
        return TranscriptResult(text=" ".join(parts), language_code=language)

    async with _fetch_semaphore:
        await _throttle_requests()
        return await loop.run_in_executor(None, _blocking_fetch)


def _apply_success(video: Video, result: TranscriptResult, *, now: datetime) -> None:
    video.transcript_text = result.text
    video.transcript_lang = result.language_code
    video.transcript_status = "ready"
    video.retry_count = 0
    video.next_retry_at = None
    video.last_error = None
    video.fetched_transcript_at = now


def _apply_retry(
    video: Video,
    error: Exception,
    *,
    now: datetime,
    base_minutes: int,
    max_retry: int,
) -> None:
    video.transcript_status = "pending"
    current_retry = video.retry_count or 0
    video.retry_count = current_retry + 1
    video.last_error = str(error)

    if video.retry_count >= max_retry:
        video.transcript_status = "failed"
        video.next_retry_at = None
        return

    delay = compute_backoff(base_minutes, video.retry_count)
    video.next_retry_at = now + delay


def _apply_permanent_failure(video: Video, error: Exception, *, now: datetime) -> None:
    video.transcript_status = "failed"
    current_retry = video.retry_count or 0
    video.retry_count = current_retry + 1
    video.last_error = str(error)
    video.next_retry_at = None
    video.fetched_transcript_at = now


async def process_pending_transcripts(
    session: AsyncSession,
    *,
    fetcher: Callable[[str], Awaitable[TranscriptResult]] = fetch_transcript,
    batch_size: int = 10,
) -> list[Video]:
    """Process pending transcripts and update video records accordingly."""

    now = datetime.now(timezone.utc)
    stmt = (
        select(Video)
        .where(Video.transcript_status == "pending", Video.next_retry_at <= now)
        .order_by(Video.next_retry_at, Video.created_at)
        .limit(batch_size)
    )

    result = await session.execute(stmt)
    videos = list(result.scalars())

    if not videos:
        return []

    processed: list[Video] = []

    for video in videos:
        try:
            result_obj = await fetcher(video.youtube_id)
            _apply_success(video, result_obj, now=now)
            processed.append(video)
        except TranscriptsDisabled as exc:
            logger.info("Transcripts disabled; marking failed", extra={"video_id": video.youtube_id})
            _apply_permanent_failure(video, exc, now=now)
            processed.append(video)
        except NoTranscriptFound as exc:
            logger.info(
                "Transcript not yet available; scheduling retry",
                extra={"video_id": video.youtube_id, "retry_count": video.retry_count + 1},
            )
            _apply_retry(
                video,
                exc,
                now=now,
                base_minutes=settings.transcript_backoff_minutes,
                max_retry=settings.transcript_max_retry,
            )
            processed.append(video)
        except Exception as exc:  # pragma: no cover - network dependent
            logger.exception("Unexpected transcript error", extra={"video_id": video.youtube_id})
            _apply_retry(
                video,
                exc,
                now=now,
                base_minutes=settings.transcript_backoff_minutes,
                max_retry=settings.transcript_max_retry,
            )
            processed.append(video)

    await session.flush()
    return processed


class TranscriptWorker:
    """Background loop that continuously processes pending transcripts."""

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    async def _run(self) -> None:
        idle_sleep = 30
        active_sleep = 2

        while not self._stop_event.is_set():
            try:
                async with SessionLocal() as session:
                    videos = await process_pending_transcripts(session)
                    if videos:
                        await session.commit()
                    else:
                        await session.rollback()
            except Exception:  # pragma: no cover - defensive guard
                logger.exception("Transcript worker iteration failed")
                await asyncio.sleep(idle_sleep)
                continue

            await asyncio.sleep(active_sleep if videos else idle_sleep)

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


transcript_worker = TranscriptWorker()


async def start_transcript_worker() -> None:
    """Public entry for FastAPI startup hook."""

    transcript_worker.start()


async def stop_transcript_worker() -> None:
    """Public entry for FastAPI shutdown hook."""

    await transcript_worker.stop()
