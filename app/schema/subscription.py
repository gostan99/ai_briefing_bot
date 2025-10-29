"""Pydantic schemas for subscription API."""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class SubscriptionRequest(BaseModel):
    """Inbound payload for registering an email and channel list."""

    email: EmailStr
    channels: list[str] = Field(min_length=1, description="List of YouTube channel identifiers")


class SubscriptionResponse(BaseModel):
    """Response payload confirming stored subscription details."""

    email: EmailStr
    channels: list[str]
