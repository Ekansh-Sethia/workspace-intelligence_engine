import asyncio
from logging.config import fileConfig
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context

from core.database import Base
from authentication.models import User
from workspaces.models import Workspace
from chat.models import ChatSession, ChatMessage
from utils.config import settings
from utils.db_url import make_async_url, make_connect_args

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Pre-compute the clean URL and connect_args once
_ASYNC_URL = make_async_url(settings.DATABASE_URL)
_CONNECT_ARGS = make_connect_args(settings.DATABASE_URL)


def run_migrations_offline() -> None:
    context.configure(
        url=_ASYNC_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section)
    configuration["sqlalchemy.url"] = _ASYNC_URL
    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args=_CONNECT_ARGS,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
