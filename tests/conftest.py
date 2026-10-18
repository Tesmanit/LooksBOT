from collections.abc import AsyncIterator, Iterator

import pytest
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from testcontainers.community.postgres import PostgresContainer

from alembic import command
from botlooks.db.session import make_sessionmaker


@pytest.fixture(scope="session")
def pg_url() -> Iterator[str]:
    mp = pytest.MonkeyPatch()
    # The Ryuk reaper container has no reachable port mapping on Docker Desktop for Windows;
    # the context manager below removes the container itself.
    mp.setenv("TESTCONTAINERS_RYUK_DISABLED", "true")
    with PostgresContainer("postgres:16", driver="asyncpg") as pg:
        url = pg.get_connection_url()
        mp.setenv("DATABASE_URL", url)
        command.upgrade(Config("alembic.ini"), "head")
        yield url
    mp.undo()


@pytest.fixture
async def sm(pg_url: str) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    maker = make_sessionmaker(pg_url)
    engine = maker.kw["bind"]
    try:
        async with maker.begin() as s:
            await s.execute(text("TRUNCATE users, analyses, payments RESTART IDENTITY CASCADE"))
        yield maker
    finally:
        await engine.dispose()
