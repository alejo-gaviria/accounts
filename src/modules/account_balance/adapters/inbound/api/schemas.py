"""Pydantic request/response models for credit/debit/transfer/get.

Amount is intentionally NOT constrained with Pydantic's `gt=0` here —
validation is delegated to the domain's Money value object so every
invalid-amount rejection goes through the same error-to-HTTP mapping
and returns the exact `{error: {code, message}}` body + 400 status,
instead of FastAPI's default 422 schema-validation response.

`currency` on the mutation requests below is the currency of the
request amount, converted to MXN via StaticExchangeRates before being
applied — not the account's own currency (every account is MXN).
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
    """Dev/test convenience only. No `currency` field — every account
    is MXN by construction. initial_balance is NOT constrained with
    Pydantic's `ge=0`; validation is delegated to the domain so a
    negative value goes through the same error-to-HTTP mapping as
    every other domain error.
    """

    initial_balance: Decimal = Decimal("0")


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail
