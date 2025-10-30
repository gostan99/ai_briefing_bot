"""Utility to delete video pipeline records by YouTube ID."""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.db.models import Video
from app.db.session import SessionLocal


async def delete_video(video_id: str) -> None:
    async with SessionLocal() as session:
        result = await session.execute(select(Video).where(Video.youtube_id == video_id))
        video = result.scalar_one_or_none()
        if not video:
            print(f"Video {video_id} not found.")
            return
        await session.delete(video)
        await session.commit()
        print(f"Deleted video {video_id}.")


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print("Usage: docker compose exec app python -m app.jobs.delete_video <YOUTUBE_ID>")
        sys.exit(1)

    asyncio.run(delete_video(sys.argv[1]))
