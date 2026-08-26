"""In-process API test fixtures.

Uses the same in-memory fakes as tests/application (no live DB needed)
via a FastAPI dependency override on get_unit_of_work, so router/auth/
validation logic is exercised end-to-end (real ASGI request/response
cycle via httpx) without requiring db-test.
"""

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.config import settings
from src.modules.account_balance.adapters.inbound.api.dependencies import (
    get_unit_of_work,
)
from src.modules.account_balance.adapters.inbound.api.error_handlers import (
    register_error_handlers,
)
from src.modules.account_balance.adapters.inbound.api.router import router
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
    application = FastAPI()
    application.include_router(router)
    register_error_handlers(application)

    def _override_uow():
        return FakeUnitOfWork(FakeAccountRepository(accounts_store), ledger_store)

    application.dependency_overrides[get_unit_of_work] = _override_uow
    return application


@pytest_asyncio.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def valid_headers():
    return {"X-API-Key": settings.api_key, "Idempotency-Key": "test-key"}
