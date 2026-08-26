"""Pydantic request/response models for credit/debit/transfer/get.

Amount is intentionally NOT constrained with Pydantic's `gt=0` here —
validation is delegated to the domain's Money value object so every
invalid-amount rejection goes through the same error-to-HTTP mapping
(router.py `_to_http_error`) and returns design.md's exact
`{error: {code, message}}` body + 400 status, instead of FastAPI's
default 422 schema-validation response.
"""

from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel


class MutationRequest(BaseModel):
    amount: Decimal
    currency: str = "USD"


class MutationResponse(BaseModel):
    account_id: UUID
    balance: Decimal
    entry_id: UUID


class TransferRequest(BaseModel):
    from_account_id: UUID
    to_account_id: UUID
    amount: Decimal
    currency: str = "USD"


class TransferResponse(BaseModel):
    transfer_id: UUID
    from_balance: Decimal
    to_balance: Decimal | None = None


class AccountResponse(BaseModel):
    id: UUID
    balance: Decimal
    currency: str


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail
