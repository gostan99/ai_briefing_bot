"""Business logic for managing subscriber channel registrations."""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.models import Channel, Subscriber, SubscriberChannel
from app.services.channel_resolver import CHANNEL_ID_REGEX


async def get_or_create_subscriber(session, email: str) -> Subscriber:
    """Fetch an existing subscriber or create a new one."""

    normalized = email.lower()
    subscriber = await session.scalar(select(Subscriber).where(Subscriber.email == normalized))
    if subscriber:
        return subscriber

    subscriber = Subscriber(email=normalized)
    session.add(subscriber)
    await session.flush()
    return subscriber


async def get_or_create_channel(
    session,
    channel_id: str,
    *,
    rss_url: str | None = None,
) -> Channel:
    """Fetch or create a channel record by external_id."""

    if not CHANNEL_ID_REGEX.match(channel_id):
        raise ValueError(f"Invalid channel id: {channel_id}")

    existing = await session.scalar(select(Channel).where(Channel.external_id == channel_id))
    if existing:
        if rss_url and existing.rss_url != rss_url:
            existing.rss_url = rss_url
        return existing

    channel = Channel(external_id=channel_id, title=channel_id, rss_url=rss_url)
    session.add(channel)
    await session.flush()
    return channel


async def sync_subscriber_channels(
    session,
    *,
    subscriber: Subscriber,
    channel_ids: Iterable[str],
    rss_urls: dict[str, str] | None = None,
) -> list[Channel]:
    """Ensure subscriber is linked to exactly the provided channel ids."""

    # Fetch existing links and map by channel external id
    existing_links = await session.scalars(
        select(SubscriberChannel)
        .options(selectinload(SubscriberChannel.channel))
        .where(SubscriberChannel.subscriber_id == subscriber.id)
    )
    link_map = {link.channel.external_id: link for link in existing_links}

    desired = set(channel_ids)
    channels: list[Channel] = []

    rss_urls = rss_urls or {}

    for channel_id in desired:
        channel = await get_or_create_channel(session, channel_id, rss_url=rss_urls.get(channel_id))
        channels.append(channel)
        if channel_id not in link_map:
            session.add(SubscriberChannel(subscriber_id=subscriber.id, channel_id=channel.id))

    # Remove links no longer desired
    for channel_id, link in link_map.items():
        if channel_id not in desired:
            await session.delete(link)

    await session.flush()
    return channels
