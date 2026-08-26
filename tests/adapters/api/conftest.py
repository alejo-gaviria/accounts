"""In-process API test fixtures.

Uses the REAL wired app (src.main.app) and overrides the container's
leaf providers (account_repository_provider, ledger_repository_provider,
unit_of_work_provider) with fakes via `provider.override(...)` -
dependency-injector's own supported testing pattern. Because the real
credit/debit/transfer use-case providers reference those leaf providers
BY REFERENCE (not by snapshotted value), overriding just the three leaf
providers is enough - no need to also override each use-case provider
individually. No live DB needed.
"""

import pytest
import pytest_asyncio
from dependency_injector import providers
from httpx import ASGITransport, AsyncClient

from src.config import settings
from src.main import app as fastapi_app
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

    container.account_repository_provider.override(providers.Object(fake_accounts))
    container.ledger_repository_provider.override(providers.Object(ledger_store))
    container.unit_of_work_provider.override(providers.Factory(FakeUnitOfWork))

    yield fastapi_app

    container.account_repository_provider.reset_override()
    container.ledger_repository_provider.reset_override()
    container.unit_of_work_provider.reset_override()


@pytest_asyncio.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def valid_headers():
    return {"X-API-Key": settings.api_key, "Idempotency-Key": "test-key"}
