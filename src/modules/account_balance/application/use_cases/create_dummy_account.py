"""Dev/test convenience use case — NOT a real account-onboarding or
provisioning flow.

Inserts a fresh `accounts` row and nothing else: no KYC, no customer
linkage, no business validation beyond "balance can't start negative"
(Account's own invariant). If real account provisioning is ever
needed, it deserves its own use case with real validation and identity
linkage — do not extend this one into that.
"""

from decimal import Decimal

from src.modules.account_balance.application.gateways.unit_of_work import UnitOfWork
from src.modules.account_balance.domain.account import Account


class CreateDummyAccountUseCase:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def execute(self, initial_balance: Decimal = Decimal("0")) -> Account:
        # Account.__post_init__ raises InvalidAmount if initial_balance
        # < 0. No locking: this is a brand-new row.
        account = Account(balance=initial_balance)

        async with self._uow as uow:
            await uow.accounts.create(account)

        return account
