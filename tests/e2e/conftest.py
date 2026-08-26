"""E2E fixtures: the REAL FastAPI app (src.main:app), REAL SqlUnitOfWork
(which builds REAL SqlAccountRepository/SqlLedgerRepository fresh in
its own __aenter__) - only the DB connection target is swapped, from
the dev `db` service to the test-db `engine`/`app_role_engine_url`
fixtures in the root conftest. Only `unit_of_work_provider` needs
overriding (to a session factory pointed at db-test, plus a logger -
SqlUnitOfWork's constructor requires both) - there is no separate
repository provider to override, since repos are never resolved from
the container directly.
"""

import logging

import pytest
from dependency_injector import providers
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.infrastructure.main import app as fastapi_app
from src.modules.account_balance.adapters.outbound.repositories.sql.uow import (
    SqlUnitOfWork,
)


@pytest.fixture
def app(engine, app_role_engine_url):
    container = fastapi_app.container
    test_app_engine = create_async_engine(app_role_engine_url)
    session_factory = async_sessionmaker(test_app_engine, expire_on_commit=False)
    test_logger = logging.getLogger("test.account_balance.e2e")

    container.unit_of_work_provider.override(
        providers.Factory(
            SqlUnitOfWork, session_factory=session_factory, logger=test_logger
        )
    )

    yield fastapi_app

    container.unit_of_work_provider.reset_override()
