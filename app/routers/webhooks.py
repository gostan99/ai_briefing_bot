"""YouTube WebSub webhook handlers."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query, Request, Response, status
from fastapi.responses import PlainTextResponse

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


@router.post("/youtube", status_code=status.HTTP_204_NO_CONTENT)
async def receive_webhook(request: Request) -> Response:
    """Receive WebSub notifications (payload parsing to be implemented)."""

    payload = await request.body()
    logger.info("Received WebSub notification", extra={"payload_length": len(payload)})
    # TODO: parse Atom payload, queue transcript fetch job, verify HMAC signature when secret configured.
    return Response(status_code=status.HTTP_204_NO_CONTENT)
