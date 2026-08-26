"""Static currency conversion — no external API (design.md "Currency
Conversion", explicit user request to keep this simple: no Banxico
integration, no HTTP call, no caching, no network-failure handling).

Deviation from design.md's illustrative code sketch, disclosed
explicitly: `UnsupportedCurrency` is NOT a bespoke `Exception` defined
in this module (as the sketch showed) - it lives in domain/errors.py
alongside InsufficientFunds/InvalidAmount/UnknownAccount, per the
explicit instruction to add it there. This also keeps it consistent
with everything else in this codebase: router.py's error-to-HTTP
mapping (_DOMAIN_ERROR_HTTP_STATUS) is a single dict keyed on
domain.errors types, and duplicating that pattern for a one-off
exception class defined elsewhere would have been inconsistent with
every other domain error in this module.
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
