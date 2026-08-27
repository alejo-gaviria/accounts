from decimal import Decimal

import pytest

from src.modules.account_balance.application.services.exchange_rates import (
    StaticExchangeRates,
)
from src.modules.account_balance.domain.errors import UnsupportedCurrency


@pytest.mark.parametrize(
    "currency, expected_rate",
    [
        ("MXN", Decimal("1")),
        ("USD", Decimal("16.96")),
        ("CAD", Decimal("12.22")),
        ("COP", Decimal("0.00549")),
        ("CNY", Decimal("2.52")),
    ],
)
def test_rate_to_mxn_returns_the_hardcoded_rate_for_each_supported_currency(
    currency, expected_rate
):
    rates = StaticExchangeRates()

    assert rates.rate_to_mxn(currency) == expected_rate


def test_rate_to_mxn_is_case_insensitive():
    rates = StaticExchangeRates()

    assert rates.rate_to_mxn("usd") == Decimal("16.96")


def test_rate_to_mxn_raises_unsupported_currency_for_anything_else():
    rates = StaticExchangeRates()

    with pytest.raises(UnsupportedCurrency):
        rates.rate_to_mxn("EUR")


def test_to_mxn_converts_amount_and_returns_rate_used():
    rates = StaticExchangeRates()

    converted, rate = rates.to_mxn(Decimal("10.00"), "USD")

    assert converted == Decimal("169.6000")
    assert rate == Decimal("16.96")


def test_to_mxn_with_mxn_is_a_no_op_conversion():
    rates = StaticExchangeRates()

    converted, rate = rates.to_mxn(Decimal("50.00"), "MXN")

    assert converted == Decimal("50.00")
    assert rate == Decimal("1")


def test_to_mxn_raises_unsupported_currency_and_converts_nothing():
    rates = StaticExchangeRates()

    with pytest.raises(UnsupportedCurrency):
        rates.to_mxn(Decimal("10.00"), "EUR")
