"""
ReconAI — Database Connection & Session Management
"""
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from backend.config import settings


class Base(DeclarativeBase):
    """Declarative base for all models."""
    pass


_engine = None
_session_factory = None


def get_engine():
    """Lazily initialize async database engine."""
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            settings.DATABASE_URL,
            echo=settings.DEBUG,
            future=True,
        )
    return _engine


def get_session_factory():
    """Lazily initialize session factory."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


# Backward compatibility proxy
class AsyncSessionProxy:
    def __call__(self, *args, **kwargs):
        factory = get_session_factory()
        return factory(*args, **kwargs)


async_session = AsyncSessionProxy()


async def get_db() -> AsyncSession:
    """Dependency to get database session."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    """Create all tables."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db():
    """Close database engine."""
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None
