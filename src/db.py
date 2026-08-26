"""Async SQLAlchemy engine/session setup.

The running application always connects as the restricted
`accounts_app` role (settings.app_database_url) — never as the
owner/migration role. Alembic is the only thing that uses
settings.database_url directly (see migrations/env.py).
"""

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.config import settings

engine = create_async_engine(
    settings.app_database_url, pool_size=10, pool_pre_ping=True
)

async_session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    engine, expire_on_commit=False
)
