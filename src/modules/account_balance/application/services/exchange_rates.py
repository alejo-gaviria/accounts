"""Hardcoded currency conversion rates, no external API."""

from decimal import Decimal

from src.modules.account_balance.domain.errors import UnsupportedCurrency

# MXN per 1 unit of currency.
_RATES_TO_MXN: dict[str, Decimal] = {
    "MXN": Decimal("1"),
    "USD": Decimal("16.96"),
    "CAD": Decimal("12.22"),
    "COP": Decimal("0.00549"),
    "CNY": Decimal("2.52"),
}


class StaticExchangeRates:
    def rate_to_mxn(self, currency: str) -> Decimal:
        try:
            return _RATES_TO_MXN[currency.upper()]
        except KeyError:
            raise UnsupportedCurrency(currency) from None

    def to_mxn(self, amount: Decimal, currency: str) -> tuple[Decimal, Decimal]:
        """Returns (converted_amount, rate_used)."""
        rate = self.rate_to_mxn(currency)
        return amount * rate, rate
