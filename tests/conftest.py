"""Shared pytest fixtures.

Test-database strategy
-----------------------
Integration-level tests (domain/application tests remain pure and need no
database) run against the ``db-test`` service defined in
``docker-compose.yml`` (Postgres 16, isolated from the ``db`` dev service,
tmpfs-backed so each run starts empty). Start it with::

    docker compose up -d db-test

The connection string is read from ``TEST_DATABASE_URL``, defaulting to the
docker-compose ``db-test`` service's exposed port. Adapter/integration tests
should be marked with ``@pytest.mark.integration`` and are expected to be
skipped in environments without the compose stack running.
"""

import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://accounts_test:accounts_test@localhost:5433/accounts_test",
)

APP_ROLE = "accounts_app"
APP_PASSWORD = "accounts_app"


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "integration: requires the db-test docker-compose service"
    )


@pytest.fixture(scope="session")
def test_database_url() -> str:
    return TEST_DATABASE_URL


async def _grant_append_only(engine: AsyncEngine) -> None:
    """Mirrors the initial migration's role/grant DDL (see
    migrations/versions/3f8f816fa633_*.py) so integration/e2e suites are
    self-contained and don't require `make migrate` to have run against
    db-test first.
    """
    async with engine.begin() as conn:
        await conn.execute(
            text(
                f"""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT FROM pg_catalog.pg_roles WHERE rolname = '{APP_ROLE}'
                    ) THEN
                        CREATE ROLE {APP_ROLE} LOGIN PASSWORD '{APP_PASSWORD}';
                    END IF;
                END
                $$;
                """
            )
        )
        await conn.execute(text(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}"))
        await conn.execute(
            text(f"GRANT SELECT, INSERT, UPDATE ON accounts TO {APP_ROLE}")
        )
        await conn.execute(
            text(f"GRANT SELECT, INSERT ON ledger_entries TO {APP_ROLE}")
        )
        await conn.execute(
            text(f"REVOKE UPDATE, DELETE ON ledger_entries FROM {APP_ROLE}")
        )


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    """Session-independent Postgres engine against TEST_DATABASE_URL,
    schema + accounts_app grants created fresh, skips (not fails) if
    db-test isn't reachable. Shared by tests/adapters/sql and tests/e2e.
    """
    from src.modules.account_balance.adapters.outbound.repositories.sql.models import (
        Base,
    )

    eng = create_async_engine(TEST_DATABASE_URL)
    try:
        async with eng.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - environment dependent
        await eng.dispose()
        pytest.skip(f"db-test Postgres not reachable at {TEST_DATABASE_URL}: {exc}")

    async with eng.begin() as conn:
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS "pgcrypto"'))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    await _grant_append_only(eng)

    yield eng

    await eng.dispose()


@pytest.fixture
def session_factory(engine: AsyncEngine) -> async_sessionmaker:
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
def app_role_engine_url() -> str:
    owner_prefix, _, host_and_db = TEST_DATABASE_URL.partition("@")
    scheme = owner_prefix.split("://", 1)[0]
    return f"{scheme}://{APP_ROLE}:{APP_PASSWORD}@{host_and_db}"
