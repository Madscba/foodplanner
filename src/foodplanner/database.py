"""Database configuration and session management."""

import os

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://localhost/foodplanner")
_SQL_ECHO = os.getenv("ENVIRONMENT", "development").lower() == "development"


class Base(DeclarativeBase):
    """Base class for all database models."""

    pass


# Async engine for FastAPI endpoints
async_engine = create_async_engine(DATABASE_URL, echo=_SQL_ECHO)
AsyncSessionLocal = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# Sync engine for batch jobs and migrations
sync_engine = create_engine(
    DATABASE_URL.replace("+asyncpg", ""),
    echo=_SQL_ECHO,
)


async def get_db() -> AsyncSession:
    """Dependency for FastAPI endpoints."""
    async with AsyncSessionLocal() as session:
        yield session
