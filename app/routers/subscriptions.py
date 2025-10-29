"""Subscription endpoint."""

from __future__ import annotations

import logging
from typing import Iterable

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_session
from app.schema.subscription import SubscriptionRequest, SubscriptionResponse
from app.services.channel_resolver import ChannelResolutionError, extract_channel_id
from app.services.subscription_service import get_or_create_subscriber, sync_subscriber_channels
from app.services.websub import channel_feed_url, ensure_subscriptions

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


def _normalize_channels(raw_channels: Iterable[str]) -> list[str]:
    """Normalize and deduplicate channel identifiers."""

    normalized: set[str] = set()
    for raw in raw_channels:
        try:
            channel_id = extract_channel_id(raw)
        except ChannelResolutionError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        normalized.add(channel_id)
    if not normalized:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No valid channels provided")
    return sorted(normalized)


@router.post("", response_model=SubscriptionResponse, status_code=status.HTTP_200_OK)
async def register_subscription(
    payload: SubscriptionRequest,
    session: AsyncSession = Depends(get_session),
) -> SubscriptionResponse:
    """Register an email address for summaries from selected channels."""

    channels = _normalize_channels(payload.channels)
    subscriber = await get_or_create_subscriber(session, payload.email)

    rss_map = {channel_id: channel_feed_url(channel_id) for channel_id in channels}

    await sync_subscriber_channels(
        session,
        subscriber=subscriber,
        channel_ids=channels,
        rss_urls=rss_map,
    )

    await session.commit()

    try:
        async with httpx.AsyncClient() as client:
            await ensure_subscriptions(
                client,
                callback_url=settings.webhook_callback_url,
                channel_ids=channels,
                lease_seconds=None,
            )
    except Exception as exc:  # noqa: BLE001 - propagate as HTTP error
        logger.exception("Failed to register WebSub subscription")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to register WebSub subscription; please retry",
        ) from exc

    return SubscriptionResponse(email=subscriber.email, channels=channels)
