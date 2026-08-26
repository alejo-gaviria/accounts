"""Idempotency replay orchestration.

Shared by all three use cases (credit/debit/transfer): attempt to append
a freshly-computed LedgerEntry; if the ledger repository reports the
(account_id, idempotency_key) pair already exists, fetch and return the
original entry instead — no re-application, no new row.
"""

from src.modules.account_balance.application.gateways.ledger_repository import (
    DuplicateIdempotencyKey,
    LedgerRepository,
)
from src.modules.account_balance.domain.ledger_entry import LedgerEntry


async def append_with_replay(
    ledgers: LedgerRepository, entry: LedgerEntry
) -> tuple[LedgerEntry, bool]:
    try:
        await ledgers.append(entry)
    except DuplicateIdempotencyKey:
        existing = await ledgers.find_by_idempotency_key(
            entry.account_id, entry.idempotency_key
        )
        if existing is None:
            # The repository raised a duplicate-key conflict but can't
            # find the row it conflicted with — a repository bug, not a
            # recoverable application-level condition.
            raise
        return existing, True
    return entry, False
