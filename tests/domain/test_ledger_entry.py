import dataclasses
from decimal import Decimal
from uuid import uuid4

import pytest

from src.modules.account_balance.domain.errors import InvalidAmount
from src.modules.account_balance.domain.ledger_entry import EntryType, LedgerEntry
from src.modules.account_balance.domain.money import Money


def _make_entry() -> LedgerEntry:
    return LedgerEntry(
        account_id=uuid4(),
        entry_type=EntryType.CREDIT,
        amount=Money(Decimal("1.00")),
        balance_after=Decimal("1.00"),
        idempotency_key="key",
        original_amount=Decimal("1.00"),
    )


def test_ledger_entry_is_immutable_after_construction():
    entry = _make_entry()

    with pytest.raises(dataclasses.FrozenInstanceError):
        entry.balance_after = Decimal("999.00")


def test_ledger_entry_defaults_id_and_no_transfer_id():
    entry = _make_entry()

    assert entry.id is not None
    assert entry.transfer_id is None


def test_money_rejects_zero_or_negative_amount():
    with pytest.raises(InvalidAmount):
        Money(Decimal("0"))

    with pytest.raises(InvalidAmount):
        Money(Decimal("-1.00"))


def test_money_accepts_positive_amount_with_default_currency():
    money = Money(Decimal("5.00"))

    assert money.amount == Decimal("5.00")
    assert money.currency == "MXN"


def test_ledger_entry_defaults_original_currency_and_fx_rate_to_no_conversion():
    entry = _make_entry()

    assert entry.original_amount == Decimal("1.00")
    assert entry.original_currency == "MXN"
    assert entry.fx_rate == Decimal("1")
