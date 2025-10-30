"""Pydantic models for video status endpoints."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class MetadataSnapshot(BaseModel):
    status: str
    tags: list[str]
    hashtags: list[str]
    sponsors: list[str]
    urls: list[str]
    fetched_at: datetime | None
    last_error: str | None


class SummarySnapshot(BaseModel):
    status: str
    tl_dr: str | None
    highlights: list[str]
    key_quote: str | None
    ready_at: datetime | None
    last_error: str | None


class VideoStatus(BaseModel):
    video_id: str
    title: str
    channel: str | None
    published_at: datetime | None
    transcript_status: str
    transcript_retries: int
    transcript_last_error: str | None
    metadata: MetadataSnapshot
    summary: SummarySnapshot
    created_at: datetime


class VideoDetail(VideoStatus):
    description: str | None
    transcript_text: str | None
    metadata_clean_description: str | None
    summary_highlights_raw: str | None
