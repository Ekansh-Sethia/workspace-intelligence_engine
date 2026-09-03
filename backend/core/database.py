from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base
from utils.config import settings
from utils.db_url import make_async_url, make_connect_args

_async_url = make_async_url(settings.DATABASE_URL)
_connect_args = make_connect_args(settings.DATABASE_URL)

engine = create_async_engine(_async_url, connect_args=_connect_args, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

Base = declarative_base()

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
