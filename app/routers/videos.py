"""API endpoints exposing video pipeline status."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.db.models import Channel, Summary, Video
from app.db.session import get_session
from app.schema.video import MetadataSnapshot, SummarySnapshot, VideoDetail, VideoStatus

router = APIRouter(prefix="/videos", tags=["videos"])


def _split_lines(value: str | None) -> list[str]:
    if not value:
        return []
    return [line.strip() for line in value.splitlines() if line.strip()]


async def _map_video(video: Video) -> VideoStatus:
    metadata = MetadataSnapshot(
        status=video.metadata_status,
        tags=_split_lines(video.metadata_tags),
        hashtags=_split_lines(video.metadata_hashtags),
        sponsors=_split_lines(video.metadata_sponsors),
        urls=_split_lines(video.metadata_urls),
        fetched_at=video.metadata_fetched_at,
        last_error=video.metadata_last_error,
    )
    summary = SummarySnapshot(
        status=video.summary.summary_status if video.summary else "pending",
        tl_dr=video.summary.tl_dr if video.summary else None,
        highlights=_split_lines(video.summary.highlights) if video.summary else [],
        key_quote=video.summary.key_quote if video.summary else None,
        ready_at=video.summary_ready_at,
        last_error=video.summary.summary_last_error if video.summary else None,
    )
    return VideoStatus(
        video_id=video.youtube_id,
        title=video.title,
        channel=video.channel.title if video.channel else None,
        published_at=video.published_at,
        transcript_status=video.transcript_status,
        transcript_retries=video.retry_count,
        transcript_last_error=video.last_error,
        metadata=metadata,
        summary=summary,
        created_at=video.created_at,
    )


@router.get("", response_model=list[VideoStatus])
async def list_videos(
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
) -> list[VideoStatus]:
    stmt = (
        select(Video)
        .options(joinedload(Video.channel), joinedload(Video.summary))
        .order_by(Video.created_at.desc())
        .limit(limit)
    )
    videos = (await session.execute(stmt)).scalars().all()
    return [await _map_video(video) for video in videos]


@router.get("/{video_id}", response_model=VideoDetail)
async def get_video(video_id: str, session: AsyncSession = Depends(get_session)) -> VideoDetail:
    stmt = (
        select(Video)
        .options(joinedload(Video.channel), joinedload(Video.summary))
        .where(Video.youtube_id == video_id)
    )
    video = (await session.execute(stmt)).scalars().first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    status = await _map_video(video)
    return VideoDetail(
        **status.dict(),
        description=video.description,
        transcript_text=video.transcript_text,
        metadata_clean_description=video.metadata_clean_description,
        summary_highlights_raw=video.summary.highlights if video.summary else None,
    )
