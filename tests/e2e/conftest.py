"""E2E fixtures: the REAL FastAPI app (src.main:app), REAL SqlUnitOfWork
and SQL repos - only the DB connection target is swapped (from the dev
`db` service to the test-db `engine`/`app_role_engine_url` fixtures in
the root conftest).

account_repository_provider/ledger_repository_provider need NO
override at all: the real SqlAccountRepository/SqlLedgerRepository
singletons resolve their DB session from context at call time (see
session_context.py), so they work unchanged regardless of which
Postgres the active SqlUnitOfWork's session came from. Only
unit_of_work_provider needs overriding, to a session factory pointed
at db-test instead of the dev `db` service.
"""

import pytest
from dependency_injector import providers
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.main import app as fastapi_app
from src.modules.account_balance.adapters.outbound.repositories.sql.uow import (
    SqlUnitOfWork,
)


@pytest.fixture
def app(engine, app_role_engine_url):
    container = fastapi_app.container
    test_app_engine = create_async_engine(app_role_engine_url)
    session_factory = async_sessionmaker(test_app_engine, expire_on_commit=False)

    container.unit_of_work_provider.override(
        providers.Factory(SqlUnitOfWork, session_factory=session_factory)
    )

    yield fastapi_app

    container.unit_of_work_provider.reset_override()
