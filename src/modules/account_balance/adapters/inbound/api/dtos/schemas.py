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
    initial_balance: Decimal = Decimal("0")


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail
