"""Pydantic models for channel management API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ChannelCreateRequest(BaseModel):
    """Inbound payload to start tracking a channel."""

    identifier: str = Field(..., min_length=1, description="YouTube channel handle, URL, or UC id")


class ChannelResponse(BaseModel):
    """Representation of a tracked channel."""

    external_id: str
    title: str
    rss_url: str | None = None


class ChannelListResponse(BaseModel):
    """Wrapper containing tracked channels."""

    channels: list[ChannelResponse]
