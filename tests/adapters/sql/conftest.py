"""Fixtures for the Postgres integration suite.

Requires a live `db-test` compose service (see tests/conftest.py for the
test-db strategy). Any fixture here that can't reach Postgres calls
`pytest.skip(...)` rather than failing, so the unit suite
(tests/domain, tests/application) is never blocked by missing infra.
"""

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from src.modules.account_balance.adapters.outbound.repositories.sql.models import Base
from tests.conftest import TEST_DATABASE_URL

APP_ROLE = "accounts_app"
APP_PASSWORD = "accounts_app"


async def _grant_append_only(engine: AsyncEngine) -> None:
    """Mirrors the initial migration's role/grant DDL (see
    migrations/versions/3f8f816fa633_*.py) so this integration suite is
    self-contained and doesn't require `make migrate` to have been run
    against db-test first.
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
