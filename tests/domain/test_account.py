"""RED -> GREEN for the Account aggregate's core invariant.

Spec: account-balance-ledger / balance-mutation-api - a debit/transfer
leg that would take balance below zero must be rejected with no state
change (InsufficientFunds), and a valid credit/debit must append a
ledger entry whose balance_after matches the new aggregate balance.
"""

from decimal import Decimal

import pytest

from src.modules.account_balance.domain.account import Account
from src.modules.account_balance.domain.errors import InsufficientFunds
from src.modules.account_balance.domain.ledger_entry import EntryType
from src.modules.account_balance.domain.money import Money


def test_credit_increases_balance_and_returns_ledger_entry():
    account = Account(balance=Decimal("10.00"))

    entry = account.apply_credit(Money(Decimal("5.00")), idempotency_key="key-1")

    assert account.balance == Decimal("15.00")
    assert account.version == 1
    assert entry.entry_type == EntryType.CREDIT
    assert entry.balance_after == Decimal("15.00")
    assert entry.idempotency_key == "key-1"


def test_debit_decreases_balance_when_sufficient_funds():
    account = Account(balance=Decimal("10.00"))

    entry = account.apply_debit(Money(Decimal("4.00")), idempotency_key="key-2")

    assert account.balance == Decimal("6.00")
    assert entry.entry_type == EntryType.DEBIT
    assert entry.balance_after == Decimal("6.00")


def test_debit_resulting_in_negative_balance_is_rejected():
    account = Account(balance=Decimal("10.00"))

    with pytest.raises(InsufficientFunds):
        account.apply_debit(Money(Decimal("10.01")), idempotency_key="key-3")

    # No state change on rejection.
    assert account.balance == Decimal("10.00")
    assert account.version == 0


def test_debit_of_exactly_the_full_balance_is_allowed():
    account = Account(balance=Decimal("10.00"))

    entry = account.apply_debit(Money(Decimal("10.00")), idempotency_key="key-4")

    assert account.balance == Decimal("0.00")
    assert entry.balance_after == Decimal("0.00")
