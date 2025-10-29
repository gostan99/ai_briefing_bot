"""Background worker that enriches video metadata by scraping the YouTube watch page."""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone, timedelta

try:
    from playwright.async_api import async_playwright
except ImportError:  # pragma: no cover - optional dependency
    async_playwright = None
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import Video
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)

WATCH_URL = "https://www.youtube.com/watch?v={video_id}"
_TAG_SPLIT_RE = re.compile(r",\s*")
_TIMESTAMP_RE = re.compile(r"^\s*\d{1,2}:\d{2}")
_URL_RE = re.compile(r"https?://\S+")
_HASHTAG_RE = re.compile(r"#(\w+)")


class MetadataFetchError(RuntimeError):
    """Raised when metadata scraping fails."""


async def fetch_video_metadata(video_id: str) -> dict[str, list[str] | str | None]:
    """Fetch metadata via Playwright (preferred) with httpx fallback."""

    if async_playwright is None:
        raise MetadataFetchError("Playwright is not installed; cannot fetch metadata")

    return await _fetch_with_playwright(video_id)


async def _fetch_with_playwright(video_id: str) -> dict[str, list[str] | str | None]:
    async with async_playwright() as p:  # type: ignore[misc]
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        try:
            page = await context.new_page()
            await page.goto(WATCH_URL.format(video_id=video_id), wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)

            raw_description = await page.evaluate(
                """
                () => {
                    const player = window.ytInitialPlayerResponse?.microformat?.playerMicroformatRenderer;
                    if (player?.description?.simpleText) return player.description.simpleText;
                    const videoDetails = window.ytInitialPlayerResponse?.videoDetails;
                    if (videoDetails?.shortDescription) return videoDetails.shortDescription;
                    const descEl = document.querySelector('#description') || document.querySelector('#description-inline-expander');
                    return descEl ? descEl.innerText : '';
                }
                """
            )

            keywords = await page.evaluate(
                "() => window.ytInitialPlayerResponse?.videoDetails?.keywords || []"
            )

            tags = _normalise_tags(", ".join(keywords or []))
            cleaned, hashtags, urls, sponsors = _clean_description(raw_description)
        finally:
            await context.close()
            await browser.close()

    return {
        "tags": tags,
        "clean_description": cleaned,
        "hashtags": hashtags,
        "urls": urls,
        "sponsors": sponsors,
        "raw_description": raw_description or "",
    }




def _normalise_tags(raw: str) -> list[str]:
    if not raw:
        return []
    candidates = [tag.strip().lower() for tag in _TAG_SPLIT_RE.split(raw) if tag.strip()]
    deduped = sorted(set(candidates))
    return deduped


def _clean_description(raw: str) -> tuple[str, list[str], list[str], list[str]]:
    if not raw:
        return "", [], [], []

    lines = raw.splitlines()
    cleaned_lines: list[str] = []
    sponsors: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if _TIMESTAMP_RE.match(stripped):
            continue
        if "sponsor" in stripped.lower():
            sponsors.append(stripped)
        cleaned_lines.append(stripped)

    hashtags = sorted({match.lower() for match in _HASHTAG_RE.findall(raw)})
    urls = sorted({match for match in _URL_RE.findall(raw)})

    cleaned_description = "\n".join(cleaned_lines)
    return cleaned_description, hashtags, urls, sponsors


def _apply_metadata_success(video: Video, metadata: dict[str, list[str] | str | None]) -> None:
    now = datetime.now(timezone.utc)
    video.metadata_status = "ready"
    video.metadata_retry_count = 0
    video.metadata_next_retry_at = None
    video.metadata_last_error = None
    video.metadata_fetched_at = now
    video.metadata_tags = "\n".join(metadata.get("tags", [])) or None
    video.metadata_clean_description = metadata.get("clean_description") or None
    video.metadata_hashtags = "\n".join(metadata.get("hashtags", [])) or None
    video.metadata_urls = "\n".join(metadata.get("urls", [])) or None
    video.metadata_sponsors = "\n".join(metadata.get("sponsors", [])) or None


def _apply_metadata_failure(video: Video, error: Exception) -> None:
    video.metadata_status = "pending"
    video.metadata_retry_count += 1
    video.metadata_last_error = str(error)

    if video.metadata_retry_count >= settings.metadata_max_retry:
        video.metadata_status = "failed"
        video.metadata_next_retry_at = None
        return

    delay_minutes = settings.metadata_backoff_minutes * (2 ** max(video.metadata_retry_count - 1, 0))
    video.metadata_next_retry_at = datetime.now(timezone.utc) + timedelta(minutes=delay_minutes)


async def process_pending_metadata(session: AsyncSession, *, batch_size: int = 10) -> list[Video]:
    """Process pending metadata jobs and return updated video rows."""

    now = datetime.now(timezone.utc)
    stmt = (
        select(Video)
        .where(Video.transcript_status == "ready")
        .where(Video.metadata_status == "pending")
        .where((Video.metadata_next_retry_at.is_(None)) | (Video.metadata_next_retry_at <= now))
        .order_by(Video.metadata_next_retry_at, Video.id)
        .limit(batch_size)
    )

    result = await session.execute(stmt)
    videos = list(result.scalars())
    if not videos:
        return []

    for video in videos:
        try:
            metadata = await fetch_video_metadata(video.youtube_id)
            _apply_metadata_success(video, metadata)
        except Exception as exc:  # pragma: no cover - network dependent
            logger.exception("Metadata fetch failed", extra={"video_id": video.youtube_id})
            _apply_metadata_failure(video, exc)

    await session.flush()
    return videos


class MetadataWorker:
    """Background loop that enriches metadata for videos with ready transcripts."""

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    async def _run(self) -> None:
        idle_sleep = 60
        active_sleep = 5

        while not self._stop_event.is_set():
            try:
                async with SessionLocal() as session:
                    videos = await process_pending_metadata(session)
                    if videos:
                        await session.commit()
                    else:
                        await session.rollback()
            except Exception:  # pragma: no cover - defensive guard
                logger.exception("Metadata worker iteration failed")
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


metadata_worker = MetadataWorker()


def start_metadata_worker() -> None:
    metadata_worker.start()


async def stop_metadata_worker() -> None:
    await metadata_worker.stop()


__all__ = [
    "process_pending_metadata",
    "fetch_video_metadata",
    "start_metadata_worker",
    "stop_metadata_worker",
]
