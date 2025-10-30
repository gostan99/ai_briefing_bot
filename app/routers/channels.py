"""API endpoints for managing tracked YouTube channels."""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_session
from app.schema.channel import ChannelCreateRequest, ChannelListResponse, ChannelResponse
from app.services.channel_registry import ensure_channel, get_channel, list_channels, remove_channel
from app.services.channel_resolver import ChannelResolutionError, extract_channel_id
from app.services.websub import channel_feed_url, ensure_subscriptions, unsubscribe

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/channels", tags=["channels"])


@router.get("", response_model=ChannelListResponse)
async def list_tracked_channels(session: AsyncSession = Depends(get_session)) -> ChannelListResponse:
    channels = await list_channels(session)
    payload = [
        ChannelResponse(external_id=channel.external_id, title=channel.title, rss_url=channel.rss_url)
        for channel in channels
    ]
    return ChannelListResponse(channels=payload)


@router.post("", response_model=ChannelResponse, status_code=status.HTTP_201_CREATED)
async def add_channel(
    payload: ChannelCreateRequest,
    session: AsyncSession = Depends(get_session),
) -> ChannelResponse:
    try:
        channel_id = extract_channel_id(payload.identifier)
    except ChannelResolutionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    rss_url = channel_feed_url(channel_id)
    channel = await ensure_channel(session, channel_id=channel_id, rss_url=rss_url)
    await session.commit()

    try:
        async with httpx.AsyncClient() as client:
            await ensure_subscriptions(
                client,
                callback_url=settings.webhook_callback_url,
                channel_ids=[channel.external_id],
                lease_seconds=None,
            )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to register WebSub subscription for channel %s", channel.external_id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to register WebSub subscription; please retry",
        ) from exc

    return ChannelResponse(external_id=channel.external_id, title=channel.title, rss_url=channel.rss_url)


@router.delete("/{identifier}", response_model=ChannelResponse)
async def delete_channel(
    identifier: str,
    session: AsyncSession = Depends(get_session),
) -> ChannelResponse:
    try:
        channel_id = extract_channel_id(identifier)
    except ChannelResolutionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    channel = await get_channel(session, channel_id)
    if channel is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel not tracked")

    response = ChannelResponse(external_id=channel.external_id, title=channel.title, rss_url=channel.rss_url)

    removed = await remove_channel(session, channel_id=channel_id)
    if not removed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel not tracked")

    await session.commit()

    try:
        async with httpx.AsyncClient() as client:
            await unsubscribe(
                client,
                callback_url=settings.webhook_callback_url,
                topic_url=channel_feed_url(channel_id),
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to unsubscribe WebSub for %s: %s", channel_id, exc)

    return response
