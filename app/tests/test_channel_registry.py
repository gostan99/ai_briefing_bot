"""Tests for the channel registry helpers."""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.models import Base, Channel
from app.services import channel_registry

pytest_plugins = ("pytest_asyncio",)


def _memory_db_url() -> str:
    return f"sqlite+aiosqlite:///file:channel_registry_{uuid.uuid4().hex}?mode=memory&cache=shared"


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine(_memory_db_url(), future=True, connect_args={"uri": True})
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    async with SessionLocal() as session:
        yield session
        await session.rollback()

    await engine.dispose()


@pytest.mark.asyncio
async def test_ensure_channel_creates_and_updates(session: AsyncSession) -> None:
    channel_id = "UC" + "A" * 22
    channel = await channel_registry.ensure_channel(session, channel_id=channel_id, rss_url="https://example.com/feed")
    assert isinstance(channel, Channel)
    assert channel.external_id == channel_id
    assert channel.rss_url == "https://example.com/feed"

    channel = await channel_registry.ensure_channel(session, channel_id=channel_id, rss_url="https://example.com/new")
    assert channel.rss_url == "https://example.com/new"


@pytest.mark.asyncio
async def test_list_and_remove_channel(session: AsyncSession) -> None:
    channel_id = "UC" + "B" * 22
    await channel_registry.ensure_channel(session, channel_id=channel_id)

    channels = await channel_registry.list_channels(session)
    assert [ch.external_id for ch in channels] == [channel_id]

    removed = await channel_registry.remove_channel(session, channel_id)
    assert removed is True

    channels = await channel_registry.list_channels(session)
    assert channels == []


@pytest.mark.asyncio
async def test_remove_channel_invalid_identifier(session: AsyncSession) -> None:
    removed = await channel_registry.remove_channel(session, "invalid")
    assert removed is False
