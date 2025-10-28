import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncIterator, Iterable
from urllib.parse import urlencode

import feedparser
import httpx
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import Channel, Video
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Provide a transactional scope around a series of operations."""

    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except SQLAlchemyError:
            await session.rollback()
            logger.exception("Database error during polling run")
            raise


def resolve_feed_url(source: str) -> str:
    """Return a YouTube RSS feed URL for a given source identifier or URL."""

    source = source.strip()
    if source.startswith("http://") or source.startswith("https://"):
        return source

    # Assume plain channel id; support @handle and playlist id later
    params = urlencode({"channel_id": source})
    return f"https://www.youtube.com/feeds/videos.xml?{params}"


async def fetch_feed(url: str, client: httpx.AsyncClient) -> feedparser.FeedParserDict | None:
    """Fetch and parse an RSS/Atom feed."""

    try:
        response = await client.get(url, timeout=15)
        response.raise_for_status()
    except httpx.HTTPError:
        logger.exception("Failed to download feed %s", url)
        return None

    return feedparser.parse(response.content)


def channel_from_feed(feed: feedparser.FeedParserDict) -> tuple[str | None, str | None]:
    """Extract channel id and title from a feed document."""

    channel_id = feed.feed.get("yt_channelid") or feed.feed.get("channel_id")
    channel_title = feed.feed.get("title")
    return channel_id, channel_title


def parse_published(entry: feedparser.FeedParserDict) -> datetime | None:
    """Convert feed published timestamp to timezone-aware datetime."""

    struct_time = entry.get("published_parsed") or entry.get("updated_parsed")
    if not struct_time:
        return None
    return datetime(*struct_time[:6], tzinfo=timezone.utc)


def video_identity(entry: feedparser.FeedParserDict) -> tuple[str | None, str | None]:
    """Return (video_id, title) from a feed entry."""

    video_id = entry.get("yt_videoid") or entry.get("video_id") or entry.get("id")
    title = entry.get("title")
    if video_id and video_id.startswith("yt:video:"):
        video_id = video_id.split(":")[-1]
    return video_id, title


async def upsert_channel(session: AsyncSession, *, external_id: str, title: str | None, rss_url: str) -> Channel:
    """Retrieve or create a channel record."""

    existing = await session.scalar(select(Channel).where(Channel.external_id == external_id))
    now = datetime.now(timezone.utc)
    if existing:
        existing.last_polled_at = now
        if title and existing.title != title:
            existing.title = title
        return existing

    channel = Channel(external_id=external_id, title=title or external_id, rss_url=rss_url, last_polled_at=now)
    session.add(channel)
    await session.flush()
    return channel


async def store_videos(session: AsyncSession, channel: Channel, entries: Iterable[feedparser.FeedParserDict]) -> int:
    """Persist new videos for a given channel."""

    new_count = 0
    for entry in entries:
        video_id, title = video_identity(entry)
        if not video_id or not title:
            continue

        existing = await session.scalar(
            select(Video).where(Video.channel_id == channel.id, Video.youtube_id == video_id)
        )
        if existing:
            continue

        description = entry.get("summary") or entry.get("description")
        published_at = parse_published(entry)

        video = Video(
            channel_id=channel.id,
            youtube_id=video_id,
            title=title,
            description=description,
            published_at=published_at,
        )
        session.add(video)
        new_count += 1

    return new_count


async def poll_once() -> None:
    """Fetch configured channels once and persist any new videos."""

    if not settings.watch_channels:
        logger.warning("No channels configured; skipping poll run")
        return

    async with httpx.AsyncClient(headers={"User-Agent": "ai-briefing-bot/0.1"}) as client:
        for source in settings.watch_channels:
            feed_url = resolve_feed_url(source)
            logger.info("Polling feed %s", feed_url)
            parsed_feed = await fetch_feed(feed_url, client)
            if not parsed_feed:
                continue

            channel_id, channel_title = channel_from_feed(parsed_feed)
            if not channel_id:
                logger.warning("Could not determine channel id for feed %s", feed_url)
                continue

            async with session_scope() as session:
                channel = await upsert_channel(
                    session, external_id=channel_id, title=channel_title, rss_url=feed_url
                )
                new_videos = await store_videos(session, channel, parsed_feed.entries)
                logger.info(
                    "Poll complete for %s (%s); new videos: %s",
                    channel_title or channel_id,
                    feed_url,
                    new_videos,
                )


async def run_forever() -> None:
    """Run the poller loop according to configured interval."""

    interval_minutes = max(1, settings.poll_interval_minutes)
    logger.info("Starting poller loop (interval_minutes=%s)", interval_minutes)
    while True:
        start = datetime.now(timezone.utc)
        try:
            await poll_once()
        except Exception:  # noqa: BLE001 - top-level guard to keep loop alive
            logger.exception("Poll cycle failed")
        elapsed = (datetime.now(timezone.utc) - start).total_seconds()
        sleep_seconds = max(5, interval_minutes * 60 - elapsed)
        await asyncio.sleep(sleep_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(poll_once())
