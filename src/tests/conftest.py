"""Shared test fixtures for yoink-dl tests."""
from __future__ import annotations

import os

import pytest
import pytest_asyncio
import sqlalchemy
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from yoink.core.db.base import Base


TEST_DB_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://yoink:yoink@yoink-postgres:5432/yoink_test",
)


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest_asyncio.fixture
async def db_engine():
    eng = create_async_engine(TEST_DB_URL, echo=False, pool_size=5, pool_recycle=300)
    async with eng.begin() as conn:
        await conn.execute(sqlalchemy.text("DROP SCHEMA public CASCADE"))
        await conn.execute(sqlalchemy.text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False)
