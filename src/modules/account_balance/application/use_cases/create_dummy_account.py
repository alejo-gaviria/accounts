from decimal import Decimal

from src.modules.account_balance.application.gateways.unit_of_work import UnitOfWork
from src.modules.account_balance.domain.account import Account


class CreateDummyAccountUseCase:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def execute(self, initial_balance: Decimal = Decimal("0")) -> Account:
        account = Account(balance=initial_balance)
        async with self._uow as uow:
            await uow.accounts.create(account)

        return account
