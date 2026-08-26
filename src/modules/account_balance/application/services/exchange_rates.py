"""Static currency conversion: a hardcoded rate table, no external API,
no HTTP call, no caching, no network-failure handling.

`UnsupportedCurrency` lives in domain/errors.py alongside the other
domain errors, since router.py's error-to-HTTP mapping is a single
dict keyed on domain.errors types.
"""

from decimal import Decimal

from src.modules.account_balance.domain.errors import UnsupportedCurrency

# MXN per 1 unit of currency. Hardcoded, manually maintained - not a
# live feed. Approximate rates as of Aug 2026; revisit periodically.
_RATES_TO_MXN: dict[str, Decimal] = {
    "MXN": Decimal("1"),
    "USD": Decimal("16.96"),
    "CAD": Decimal("12.22"),
    "COP": Decimal("0.00549"),
    "CNY": Decimal("2.52"),
}


class StaticExchangeRates:
    """Pure/stateless - safe to wire as a container-level
    `providers.Singleton` (unlike the SQL repositories, it holds no
    per-request DB session)."""

    def rate_to_mxn(self, currency: str) -> Decimal:
        try:
            return _RATES_TO_MXN[currency.upper()]
        except KeyError:
            raise UnsupportedCurrency(currency) from None

    def to_mxn(self, amount: Decimal, currency: str) -> tuple[Decimal, Decimal]:
        """Returns (converted_amount, rate_used)."""
        rate = self.rate_to_mxn(currency)
        return amount * rate, rate
