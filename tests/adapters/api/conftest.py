"""In-process API test fixtures.

Uses the REAL wired app (src.main.app) and overrides the container's
`unit_of_work_provider` with a Factory that builds a fresh
FakeUnitOfWork (fresh .committed/.rolled_back per "request", same as a
real fresh transaction) sharing the SAME fake accounts/ledger stores
across requests within one test - dependency-injector's own supported
testing pattern (provider.override(...)/reset_override()). No live DB
needed.
"""

import pytest
import pytest_asyncio
from dependency_injector import providers
from httpx import ASGITransport, AsyncClient

from src.config import settings
from src.infrastructure.main import app as fastapi_app
from tests.application.fakes import (
    FakeAccountRepository,
    FakeLedgerRepository,
    FakeUnitOfWork,
)


@pytest.fixture
def accounts_store():
    return {}


@pytest.fixture
def ledger_store():
    return FakeLedgerRepository()


@pytest.fixture
def app(accounts_store, ledger_store):
    container = fastapi_app.container
    fake_accounts = FakeAccountRepository(accounts_store)

    container.unit_of_work_provider.override(
        providers.Factory(FakeUnitOfWork, accounts=fake_accounts, ledger=ledger_store)
    )

    yield fastapi_app

    container.unit_of_work_provider.reset_override()


@pytest_asyncio.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def valid_headers():
    return {"X-API-Key": settings.api_key, "Idempotency-Key": "test-key"}
