from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings


def create_engine() -> AsyncEngine:
    """Create a SQLAlchemy async engine from settings."""

    return create_async_engine(settings.database_url, echo=False, pool_pre_ping=True)


engine = create_engine()
SessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency that yields a database session."""

    async with SessionLocal() as session:
        yield session


async def session_from_pool() -> AsyncIterator[AsyncSession]:
    """Utility context manager for scripts."""

    async with SessionLocal() as session:
        yield session
