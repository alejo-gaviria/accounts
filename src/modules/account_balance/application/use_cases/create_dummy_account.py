from decimal import Decimal
from logging import Logger

from src.modules.account_balance.adapters.outbound.repositories.sql.account_repo import (
    SqlAccountRepository,
)
from src.modules.account_balance.domain.account import Account
from src.modules.shared.application.ports.unit_of_work import UnitOfWork


class CreateDummyAccountUseCase:
    def __init__(self, uow: UnitOfWork, logger: Logger) -> None:
        self._uow = uow
        self._logger = logger

    async def execute(self, initial_balance: Decimal = Decimal("0")) -> Account:
        account = Account(balance=initial_balance)
        async with self._uow as uow:
            accounts = SqlAccountRepository(session=uow.session, logger=self._logger)
            await accounts.create(account)

        return account
