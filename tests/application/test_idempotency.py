import logging
from decimal import Decimal
from uuid import uuid4

import pytest

import src.modules.account_balance.application.use_cases.credit as credit_module
from src.modules.account_balance.application.services.exchange_rates import (
    StaticExchangeRates,
)
from src.modules.account_balance.application.use_cases.credit import (
    CreditAccountUseCase,
)
from src.modules.account_balance.domain.account import Account
from tests.application.fakes import (
    FakeAccountRepository,
    FakeLedgerRepository,
    FakeUnitOfWork,
    patch_use_case_repos,
)

_logger = logging.getLogger("test")


@pytest.mark.asyncio
async def test_duplicate_idempotency_key_returns_original_result_no_reapply(
    monkeypatch,
):
    account = Account(id=uuid4(), balance=Decimal("10.00"))
    accounts = FakeAccountRepository({account.id: account})
    ledger = FakeLedgerRepository()
    patch_use_case_repos(monkeypatch, credit_module, accounts, ledger)

    use_case_1 = CreditAccountUseCase(
        uow=FakeUnitOfWork(), logger=_logger, exchange_rates=StaticExchangeRates()
    )
    first = await use_case_1.execute(account.id, Decimal("5.00"), "MXN", "same-key")
    assert account.balance == Decimal("15.00")

    uow2 = FakeUnitOfWork()
    use_case_2 = CreditAccountUseCase(
        uow=uow2, logger=_logger, exchange_rates=StaticExchangeRates()
    )
    second = await use_case_2.execute(account.id, Decimal("5.00"), "MXN", "same-key")

    assert second is first
    assert account.balance == Decimal("15.00")
    assert len(ledger.entries) == 1
    assert uow2.committed is True
    assert uow2.rolled_back is False
