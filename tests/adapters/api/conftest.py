import pytest
import pytest_asyncio
from dependency_injector import providers
from httpx import ASGITransport, AsyncClient

import src.modules.account_balance.adapters.inbound.api.router as router_module
import src.modules.account_balance.application.use_cases.create_dummy_account as create_dummy_account_module
import src.modules.account_balance.application.use_cases.credit as credit_module
import src.modules.account_balance.application.use_cases.debit as debit_module
import src.modules.account_balance.application.use_cases.transfer as transfer_module
from src.config import settings
from src.infrastructure.main import app as fastapi_app
from tests.application.fakes import (
    FakeAccountRepository,
    FakeLedgerRepository,
    FakeUnitOfWork,
)

_MUTATION_USE_CASE_MODULES = [credit_module, debit_module, transfer_module]


@pytest.fixture
def accounts_store():
    return {}


@pytest.fixture
def ledger_store():
    return FakeLedgerRepository()


@pytest.fixture
def app(monkeypatch, accounts_store, ledger_store):
    container = fastapi_app.container
    fake_accounts = FakeAccountRepository(accounts_store)

    for module in _MUTATION_USE_CASE_MODULES:
        monkeypatch.setattr(
            module, "SqlAccountRepository", lambda session, logger: fake_accounts
        )
        monkeypatch.setattr(
            module, "SqlLedgerRepository", lambda session, logger: ledger_store
        )
    monkeypatch.setattr(
        create_dummy_account_module,
        "SqlAccountRepository",
        lambda session, logger: fake_accounts,
    )
    monkeypatch.setattr(
        router_module, "SqlAccountRepository", lambda session, logger: fake_accounts
    )

    container.shared.unit_of_work_provider.override(providers.Factory(FakeUnitOfWork))

    yield fastapi_app

    container.shared.unit_of_work_provider.reset_override()


@pytest_asyncio.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def valid_headers():
    return {"X-API-Key": settings.api_key, "Idempotency-Key": "test-key"}
