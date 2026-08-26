"""Pydantic request/response models for credit/debit/transfer/get.

Amount is intentionally NOT constrained with Pydantic's `gt=0` here —
validation is delegated to the domain's Money value object so every
invalid-amount rejection goes through the same error-to-HTTP mapping
(router.py `_to_http_error`) and returns design.md's exact
`{error: {code, message}}` body + 400 status, instead of FastAPI's
default 422 schema-validation response.

Currency Conversion (design.md): `currency` on the mutation requests
below is now real and enforced — it's the currency of the request
amount, converted to MXN via StaticExchangeRates before being applied
(an unsupported currency is rejected with 400, same as an invalid
amount). Defaults to "MXN" (was "USD" pre-conversion, back when the
field was accepted but never actually enforced) so that existing
callers who don't care about currency conversion get amount-in,
amount-applied semantics unchanged (MXN's rate is exactly 1).
"""

from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel


class MutationRequest(BaseModel):
    amount: Decimal
    currency: str = "MXN"


class MutationResponse(BaseModel):
    account_id: UUID
    balance: Decimal
    entry_id: UUID


class TransferRequest(BaseModel):
    from_account_id: UUID
    to_account_id: UUID
    amount: Decimal
    currency: str = "MXN"


class TransferResponse(BaseModel):
    transfer_id: UUID
    from_balance: Decimal
    to_balance: Decimal | None = None


class AccountResponse(BaseModel):
    id: UUID
    balance: Decimal
    currency: str


class CreateAccountRequest(BaseModel):
    """Dev/test convenience only — see CreateDummyAccountUseCase's
    docstring. No `currency` field at all — every account is MXN by
    construction now (Currency Conversion, design.md), nothing to
    choose. initial_balance is NOT constrained with Pydantic's `ge=0`
    for the same reason MutationRequest.amount isn't constrained with
    `gt=0`: validation is delegated to the domain (Account's
    __post_init__) so a negative value goes through the same
    error-to-HTTP mapping as every other domain error.
    """

    initial_balance: Decimal = Decimal("0")


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail
