"""Integration tests against a real Postgres (db-test compose service).

Spec: account-balance-ledger / "Ledger row cannot be altered" - the
app's DB role must not be able to UPDATE/DELETE ledger_entries.
Spec: concurrency-safety / "Concurrent mutations serialize correctly" -
SELECT ... FOR UPDATE on the account row.

NOT executed in the sandbox this change was authored in (Docker daemon
unreachable there - see apply-progress); written and reasoned through
against documented SQLAlchemy/asyncpg/Postgres behavior, and will
self-skip (not fail) wherever `db-test` isn't reachable.
"""

import asyncio
import logging
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

from src.modules.account_balance.adapters.outbound.repositories.sql.account_repo import (
    SqlAccountRepository,
)

pytestmark = pytest.mark.integration

_test_logger = logging.getLogger("test.account_balance")


@pytest.mark.asyncio
async def test_ledger_entries_update_is_rejected_for_app_role(
    engine, app_role_engine_url
):
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO accounts (id, balance) VALUES (:id, 100) "
            ),
            {"id": str(uuid4())},
        )

    app_engine = create_async_engine(app_role_engine_url)
    try:
        with pytest.raises(DBAPIError, match="permission denied"):
            async with app_engine.begin() as conn:
                await conn.execute(text("UPDATE ledger_entries SET amount = amount"))
    finally:
        await app_engine.dispose()


@pytest.mark.asyncio
async def test_ledger_entries_delete_is_rejected_for_app_role(
    engine, app_role_engine_url
):
    app_engine = create_async_engine(app_role_engine_url)
    try:
        with pytest.raises(DBAPIError, match="permission denied"):
            async with app_engine.begin() as conn:
                await conn.execute(text("DELETE FROM ledger_entries"))
    finally:
        await app_engine.dispose()


@pytest.mark.asyncio
async def test_ledger_entries_insert_and_select_allowed_for_app_role(
    engine, app_role_engine_url
):
    async with engine.begin() as conn:
        account_id = uuid4()
        await conn.execute(
            text("INSERT INTO accounts (id, balance) VALUES (:id, 100)"),
            {"id": str(account_id)},
        )

    app_engine = create_async_engine(app_role_engine_url)
    try:
        async with app_engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO ledger_entries "
                    "(account_id, entry_type, amount, currency, balance_after, idempotency_key) "
                    "VALUES (:acct, 'credit', 10, 'USD', 110, 'k1')"
                ),
                {"acct": str(account_id)},
            )
            result = await conn.execute(text("SELECT count(*) FROM ledger_entries"))
            assert result.scalar_one() == 1
    finally:
        await app_engine.dispose()


@pytest.mark.asyncio
async def test_get_for_update_blocks_a_second_lock_on_the_same_account(
    engine, session_factory
):
    """SqlAccountRepository is a plain class taking its session via the
    constructor (DI refactor - no singleton, no ambient/contextvar
    state) - two "concurrent" transactions are simulated here with two
    separate sessions, each with its own repository instance, exactly
    like two different SqlUnitOfWork.__aenter__ calls for two different
    requests would produce.
    """
    account_id = uuid4()
    async with engine.begin() as conn:
        await conn.execute(
            text("INSERT INTO accounts (id, balance) VALUES (:id, 100)"),
            {"id": str(account_id)},
        )

    session_a = session_factory()
    session_b = session_factory()
    try:
        repo_a = SqlAccountRepository(session=session_a, logger=_test_logger)
        repo_b = SqlAccountRepository(session=session_b, logger=_test_logger)

        await repo_a.get_for_update(account_id)  # holds the lock

        # A second lock attempt on the same row must block until the
        # first transaction ends - prove it by racing a short timeout.
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(repo_b.get_for_update(account_id), timeout=0.5)

        await session_a.rollback()  # releases the lock

        # Now it should succeed promptly.
        account = await asyncio.wait_for(
            repo_b.get_for_update(account_id), timeout=2.0
        )
        assert account.id == account_id
    finally:
        await session_a.close()
        await session_b.close()
