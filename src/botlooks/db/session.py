from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


def make_sessionmaker(database_url: str) -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(database_url, pool_pre_ping=True)
    return async_sessionmaker(engine, expire_on_commit=False)
