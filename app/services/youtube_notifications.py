"""Helpers for parsing and persisting YouTube WebSub notifications."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable
from xml.etree import ElementTree as ET

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Channel, Video
from app.services.channel_registry import ensure_channel

logger = logging.getLogger(__name__)


ATOM_NS = "http://www.w3.org/2005/Atom"
YT_NS = "http://www.youtube.com/xml/schemas/2015"
MEDIA_NS = "http://search.yahoo.com/mrss/"
TOMBSTONE_NS = "http://purl.org/atompub/tombstones/1.0"


class WebhookParseError(ValueError):
    """Raised when a WebSub payload cannot be parsed."""


@dataclass(slots=True)
class YouTubeNotification:
    """Represents a single YouTube video notification."""

    channel_id: str
    video_id: str
    channel_title: str | None
    video_title: str | None
    description: str | None
    published_at: datetime | None
    updated_at: datetime | None


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    if not value:
        return None
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        logger.debug("Failed to parse datetime", extra={"value": value})
        return None


def parse_notifications(payload: bytes) -> list[YouTubeNotification]:
    """Parse a raw Atom XML payload into YouTube notifications."""

    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise WebhookParseError("Invalid XML payload") from exc

    if root.tag != f"{{{ATOM_NS}}}feed":
        raise WebhookParseError(f"Unexpected root element: {root.tag}")

    notifications: list[YouTubeNotification] = []

    for deleted in root.findall(f"{{{TOMBSTONE_NS}}}deleted-entry"):
        logger.info(
            "Ignoring deleted-entry notification",
            extra={"ref": deleted.get(f"{{{ATOM_NS}}}ref")},
        )

    for entry in root.findall(f"{{{ATOM_NS}}}entry"):
        channel_id = entry.findtext(f"{{{YT_NS}}}channelId")
        video_id = entry.findtext(f"{{{YT_NS}}}videoId")

        if not channel_id or not video_id:
            logger.warning("Skipping entry missing identifiers")
            continue

        channel_title = entry.findtext(f"{{{ATOM_NS}}}author/{{{ATOM_NS}}}name")
        video_title = entry.findtext(f"{{{ATOM_NS}}}title")

        description = None
        media_group = entry.find(f"{{{MEDIA_NS}}}group")
        if media_group is not None:
            description = media_group.findtext(f"{{{MEDIA_NS}}}description")

        published_at = _parse_datetime(entry.findtext(f"{{{ATOM_NS}}}published"))
        updated_at = _parse_datetime(entry.findtext(f"{{{ATOM_NS}}}updated"))

        notifications.append(
            YouTubeNotification(
                channel_id=channel_id,
                video_id=video_id,
                channel_title=channel_title,
                video_title=video_title,
                description=description,
                published_at=published_at,
                updated_at=updated_at,
            )
        )

    return notifications


async def persist_notifications(
    session: AsyncSession,
    notifications: Iterable[YouTubeNotification],
) -> list[Video]:
    """Upsert channel/video rows for the given notifications."""

    processed: list[Video] = []
    now = datetime.now(timezone.utc)

    for notification in notifications:
        channel = await ensure_channel(session, channel_id=notification.channel_id)

        if notification.channel_title and channel.title != notification.channel_title:
            channel.title = notification.channel_title
        channel.last_polled_at = now

        existing_video = await session.scalar(
            select(Video).where(
                Video.channel_id == channel.id, Video.youtube_id == notification.video_id
            )
        )

        if existing_video is None:
            video = Video(
                channel_id=channel.id,
                youtube_id=notification.video_id,
                title=notification.video_title or notification.video_id,
                description=notification.description,
                published_at=notification.published_at,
                transcript_status="pending",
                retry_count=0,
                next_retry_at=now,
                last_error=None,
                metadata_status="pending",
                metadata_retry_count=0,
                metadata_next_retry_at=now,
                metadata_last_error=None,
            )
            session.add(video)
            processed.append(video)
        else:
            if notification.video_title and existing_video.title != notification.video_title:
                existing_video.title = notification.video_title
            if notification.description is not None and existing_video.description != notification.description:
                existing_video.description = notification.description
            if notification.published_at and existing_video.published_at != notification.published_at:
                existing_video.published_at = notification.published_at
            if existing_video.transcript_status == "pending" and existing_video.next_retry_at is None:
                existing_video.next_retry_at = now
            if existing_video.metadata_status == "pending" and existing_video.metadata_next_retry_at is None:
                existing_video.metadata_next_retry_at = now
            processed.append(existing_video)

    await session.flush()
    return processed
