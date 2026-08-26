"""Dev/test convenience use case — NOT a real account-onboarding or
provisioning flow.

Exists purely so credit/debit/transfer can be exercised without hand-
seeding rows into Postgres via `psql`. There is no KYC, no customer
linkage, no business validation beyond "balance can't start negative"
(domain.Account's own invariant) — it inserts a fresh `accounts` row
and nothing else. If real account provisioning is ever needed, it
deserves its own proper use case with real validation and identity
linkage; do not extend this one into that.

Same class-based DI shape as the other use cases: constructor takes
`uow`, wired through AccountBalanceContainer as a `providers.Factory`.
"""

from decimal import Decimal

from src.modules.account_balance.application.gateways.unit_of_work import UnitOfWork
from src.modules.account_balance.domain.account import Account


class CreateDummyAccountUseCase:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def execute(self, initial_balance: Decimal = Decimal("0")) -> Account:
        # No currency param at all — every account is MXN by
        # construction now (Account.currency defaults to "MXN"), same
        # class of decorative-field problem the whole Currency
        # Conversion capability fixes elsewhere. Account.__post_init__
        # raises InvalidAmount if initial_balance < 0 — same
        # error-to-HTTP mapping the router already uses for
        # credit/debit, no separate validation needed here. Id is
        # server-generated (Account's default_factory=uuid4). No
        # locking: this is a brand-new row, not a mutation of an
        # existing one.
        account = Account(balance=initial_balance)

        async with self._uow as uow:
            await uow.accounts.create(account)

        return account
