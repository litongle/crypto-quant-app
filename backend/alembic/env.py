"""
Alembic async migration config

- Read database URL from app.config (supports SQLite / PostgreSQL)
- Async engine for online migrations
- Auto-import all models for autogenerate
- ALEMBIC_DATABASE_URL env var can override for local dev
"""
import asyncio
import os
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# this is the Alembic Config object
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Read database URL: env var > app config
db_url = os.environ.get("ALEMBIC_DATABASE_URL")
if not db_url:
    from app.config import get_settings
    settings = get_settings()
    db_url = settings.database_url

config.set_main_option("sqlalchemy.url", db_url)

# Import all models so Base.metadata knows all tables
import app.models  # noqa: F401
from app.database import Base

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Generates SQL without connecting to the database.
    Useful for generating SQL scripts for DBA review.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    """Execute migrations (reused by async online mode)"""
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode with async engine."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    Uses async engine for compatibility with asyncpg / aiosqlite.
    """
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
