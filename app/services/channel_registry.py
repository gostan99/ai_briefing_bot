"""Helpers for managing tracked YouTube channels."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Channel
from app.services.channel_resolver import CHANNEL_ID_REGEX


async def list_channels(session: AsyncSession) -> Sequence[Channel]:
    """Return all tracked channels ordered by creation time (newest first)."""

    result = await session.scalars(select(Channel).order_by(Channel.created_at.desc()))
    return list(result)


async def get_channel(session: AsyncSession, channel_id: str) -> Channel | None:
    """Fetch a channel by external identifier."""

    if not CHANNEL_ID_REGEX.match(channel_id):
        return None
    return await session.scalar(select(Channel).where(Channel.external_id == channel_id))


async def ensure_channel(
    session: AsyncSession,
    *,
    channel_id: str,
    rss_url: str | None = None,
) -> Channel:
    """Fetch or create a channel row by canonical identifier."""

    if not CHANNEL_ID_REGEX.match(channel_id):
        raise ValueError(f"Invalid channel id: {channel_id}")

    channel = await session.scalar(select(Channel).where(Channel.external_id == channel_id))
    if channel:
        if rss_url and channel.rss_url != rss_url:
            channel.rss_url = rss_url
        return channel

    channel = Channel(external_id=channel_id, title=channel_id, rss_url=rss_url)
    session.add(channel)
    await session.flush()
    return channel


async def remove_channel(session: AsyncSession, channel_id: str) -> bool:
    """Delete a channel and cascade to related videos; returns True when removed."""

    if not CHANNEL_ID_REGEX.match(channel_id):
        return False

    channel = await session.scalar(select(Channel).where(Channel.external_id == channel_id))
    if channel is None:
        return False

    await session.delete(channel)
    await session.flush()
    return True
