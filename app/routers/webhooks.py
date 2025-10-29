"""YouTube WebSub webhook handlers."""

from __future__ import annotations

import logging

import hashlib
import hmac

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_session
from app.services.youtube_notifications import (
    WebhookParseError,
    parse_notifications,
    persist_notifications,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.get("/youtube", response_class=PlainTextResponse)
async def verify_webhook(
    hub_mode: str = Query(..., alias="hub.mode"),
    hub_topic: str = Query(..., alias="hub.topic"),
    hub_challenge: str = Query(..., alias="hub.challenge"),
    hub_lease_seconds: int | None = Query(None, alias="hub.lease_seconds"),
    hub_verify_token: str | None = Query(None, alias="hub.verify_token"),
) -> PlainTextResponse:
    """Respond to WebSub hub verification challenge."""

    logger.info(
        "WebSub verification",
        extra={
            "mode": hub_mode,
            "topic": hub_topic,
            "lease_seconds": hub_lease_seconds,
            "verify_token": hub_verify_token,
        },
    )
    return PlainTextResponse(content=hub_challenge, status_code=status.HTTP_200_OK)


def _validate_signature(payload: bytes, signature: str, secret: str) -> bool:
    try:
        algo, received = signature.split("=", 1)
    except ValueError:
        return False

    algo = algo.lower()
    if algo == "sha1":
        digestmod = hashlib.sha1
    elif algo == "sha256":
        digestmod = hashlib.sha256
    else:
        return False

    expected = hmac.new(secret.encode(), payload, digestmod).hexdigest()
    return hmac.compare_digest(expected, received)


@router.post("/youtube", status_code=status.HTTP_204_NO_CONTENT)
async def receive_webhook(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Receive WebSub notifications and persist new uploads."""

    payload = await request.body()
    logger.info("Received WebSub notification", extra={"payload_length": len(payload)})

    secret = settings.webhook_secret
    if secret:
        signature = request.headers.get("X-Hub-Signature") or request.headers.get("X-Hub-Signature-256")
        if not signature or not _validate_signature(payload, signature, secret):
            logger.warning("Webhook signature validation failed")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid signature")

    if not payload:
        logger.info("Empty WebSub payload")
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    try:
        notifications = parse_notifications(payload)
    except WebhookParseError as exc:
        logger.warning("Invalid WebSub payload", exc_info=exc)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed payload") from exc

    if not notifications:
        logger.info("No actionable entries in WebSub payload")
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    try:
        videos = await persist_notifications(session, notifications)
        await session.commit()
    except Exception as exc:  # noqa: BLE001 - let FastAPI handle HTTP error
        await session.rollback()
        logger.exception("Failed to persist WebSub notification")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to persist notification",
        ) from exc

    logger.info(
        "Processed WebSub notification",
        extra={"video_ids": [video.youtube_id for video in videos], "count": len(videos)},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
