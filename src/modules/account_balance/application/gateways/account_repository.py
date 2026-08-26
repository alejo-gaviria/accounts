"""Port: AccountRepository.

Concrete implementation lives in
adapters/outbound/repositories/sql/account_repo.py and performs a real
`SELECT ... FOR UPDATE`. This Protocol is what the application layer's
use cases depend on, and what test doubles implement.
"""

from typing import Protocol
from uuid import UUID

from src.modules.account_balance.domain.account import Account


class AccountRepository(Protocol):
    async def get_for_update(self, account_id: UUID) -> Account:
        """Lock and return the account aggregate row.

        Raises domain.errors.UnknownAccount if no such account exists.
        """
        ...

    async def save(self, account: Account) -> None:
        """Persist the account's current balance/version (UPDATE)."""
        ...

    async def create(self, account: Account) -> None:
        """Insert a brand-new account row (dev/test convenience only —
        see application/use_cases/create_dummy_account.py). No locking
        needed: this is a fresh row, not a mutation of an existing one.
        """
        ...
