"""Alembic environment. Hand-written migrations only — no autogenerate, no ORM
models (ARCHITECTURE.md > Data access: raw SQL via asyncpg, no ORM). Alembic's
own dependency on SQLAlchemy is used purely as a migration runner; application
code never touches SQLAlchemy.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from topos.config import get_settings

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# DSN comes from TOPOS_DB_DSN (see topos.config), not alembic.ini, so one
# source of truth serves both the app and migrations.
settings = get_settings()
dsn = settings.db_dsn.replace("postgresql://", "postgresql+asyncpg://", 1)
config.set_main_option("sqlalchemy.url", dsn)

target_metadata = None  # no ORM models; migrations are hand-written SQL


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
