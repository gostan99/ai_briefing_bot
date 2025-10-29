"""Helpers to interact with YouTube's WebSub (PubSubHubbub) hub."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urlencode

import httpx

from app.core.config import settings
from app.services.channel_resolver import CHANNEL_ID_REGEX

logger = logging.getLogger(__name__)

YOUTUBE_HUB_URL = "https://pubsubhubbub.appspot.com/"
YOUTUBE_FEED_BASE = "https://www.youtube.com/xml/feeds/videos.xml"


@dataclass(slots=True)
class WebSubSubscription:
    """Represents a WebSub subscription request."""

    callback_url: str
    topic_url: str
    mode: str = "subscribe"
    verify: str = "async"
    lease_seconds: int | None = None
    secret: str | None = None
    verify_token: str | None = None

    def to_form(self) -> dict[str, str]:
        """Convert the subscription details into form payload."""

        payload: dict[str, str] = {
            "hub.callback": self.callback_url,
            "hub.mode": self.mode,
            "hub.topic": self.topic_url,
            "hub.verify": self.verify,
        }
        if self.lease_seconds is not None:
            payload["hub.lease_seconds"] = str(self.lease_seconds)
        if self.secret:
            payload["hub.secret"] = self.secret
        if self.verify_token:
            payload["hub.verify_token"] = self.verify_token
        return payload


def channel_feed_url(channel_identifier: str) -> str:
    """Return a canonical YouTube channel feed URL for the given identifier or handle."""

    identifier = channel_identifier.strip()
    if identifier.startswith("http://") or identifier.startswith("https://"):
        return identifier
    if not CHANNEL_ID_REGEX.match(identifier):
        raise ValueError("channel_feed_url expects a canonical channel id")
    params = urlencode({"channel_id": identifier})
    return f"{YOUTUBE_FEED_BASE}?{params}"


async def subscribe(
    client: httpx.AsyncClient,
    *,
    callback_url: str,
    topic_url: str,
    lease_seconds: int | None = None,
    secret: str | None = None,
    verify_token: str | None = None,
) -> None:
    """Submit a WebSub (subscribe) request for the given topic."""

    request = WebSubSubscription(
        callback_url=callback_url,
        topic_url=topic_url,
        lease_seconds=lease_seconds,
        secret=secret,
        verify_token=verify_token,
    )
    payload = request.to_form()
    logger.info("Subscribing to WebSub topic %s", topic_url)
    response = await client.post(YOUTUBE_HUB_URL, data=payload, timeout=10)
    response.raise_for_status()


async def unsubscribe(
    client: httpx.AsyncClient,
    *,
    callback_url: str,
    topic_url: str,
) -> None:
    """Cancel an existing WebSub subscription."""

    request = WebSubSubscription(callback_url=callback_url, topic_url=topic_url, mode="unsubscribe")
    payload = request.to_form()
    logger.info("Unsubscribing from WebSub topic %s", topic_url)
    response = await client.post(YOUTUBE_HUB_URL, data=payload, timeout=10)
    response.raise_for_status()


async def ensure_subscriptions(
    client: httpx.AsyncClient,
    *,
    callback_url: str,
    channel_ids: Iterable[str],
    lease_seconds: int | None = None,
) -> None:
    """Ensure all provided channel feeds are subscribed via WebSub."""

    secret = settings.webhook_secret
    tasks = []
    for channel_identifier in channel_ids:
        topic = channel_feed_url(channel_identifier)
        tasks.append(
            subscribe(
                client,
                callback_url=callback_url,
                topic_url=topic,
                lease_seconds=lease_seconds,
                secret=secret,
            )
        )
    if tasks:
        await asyncio.gather(*tasks)


async def refresh_subscription(
    client: httpx.AsyncClient,
    *,
    callback_url: str,
    channel_identifier: str,
    lease_seconds: int | None = None,
) -> None:
    """Refresh a single channel subscription (resubscribe)."""

    await subscribe(
        client,
        callback_url=callback_url,
        topic_url=channel_feed_url(channel_identifier),
        lease_seconds=lease_seconds,
        secret=settings.webhook_secret,
    )
