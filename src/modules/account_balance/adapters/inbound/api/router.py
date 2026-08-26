"""Inbound HTTP API — credit/debit/transfer/get, the source of truth
for balance mutations (spec: balance-mutation-api).
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from src.modules.account_balance.adapters.inbound.api.dependencies import (
    get_unit_of_work,
    require_api_key,
    require_idempotency_key,
)
from src.modules.account_balance.adapters.inbound.api.schemas import (
    AccountResponse,
    MutationRequest,
    MutationResponse,
    TransferRequest,
    TransferResponse,
)
from src.modules.account_balance.application.gateways.unit_of_work import UnitOfWork
from src.modules.account_balance.application.use_cases.credit import (
    credit as credit_use_case,
)
from src.modules.account_balance.application.use_cases.debit import (
    debit as debit_use_case,
)
from src.modules.account_balance.application.use_cases.transfer import (
    transfer as transfer_use_case,
)
from src.modules.account_balance.domain.errors import (
    InsufficientFunds,
    InvalidAmount,
    UnknownAccount,
)
from src.modules.account_balance.domain.money import Money

router = APIRouter(prefix="/v1")

_DOMAIN_ERROR_HTTP_STATUS = {
    InvalidAmount: (400, "invalid_amount"),
    UnknownAccount: (404, "unknown_account"),
    InsufficientFunds: (409, "insufficient_funds"),
}


def _to_http_error(exc: Exception) -> HTTPException:
    for error_type, (status_code, code) in _DOMAIN_ERROR_HTTP_STATUS.items():
        if isinstance(exc, error_type):
            return HTTPException(
                status_code=status_code,
                detail={"error": {"code": code, "message": str(exc)}},
            )
    raise exc


@router.post(
    "/accounts/{account_id}/credit",
    response_model=MutationResponse,
    dependencies=[Depends(require_api_key)],
)
async def credit_account(
    account_id: UUID,
    body: MutationRequest,
    idempotency_key: str = Depends(require_idempotency_key),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> MutationResponse:
    try:
        money = Money(body.amount, body.currency)
        entry = await credit_use_case(uow, account_id, money, idempotency_key)
    except (InvalidAmount, UnknownAccount, InsufficientFunds) as exc:
        raise _to_http_error(exc) from exc
    return MutationResponse(
        account_id=account_id, balance=entry.balance_after, entry_id=entry.id
    )


@router.post(
    "/accounts/{account_id}/debit",
    response_model=MutationResponse,
    dependencies=[Depends(require_api_key)],
)
async def debit_account(
    account_id: UUID,
    body: MutationRequest,
    idempotency_key: str = Depends(require_idempotency_key),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> MutationResponse:
    try:
        money = Money(body.amount, body.currency)
        entry = await debit_use_case(uow, account_id, money, idempotency_key)
    except (InvalidAmount, UnknownAccount, InsufficientFunds) as exc:
        raise _to_http_error(exc) from exc
    return MutationResponse(
        account_id=account_id, balance=entry.balance_after, entry_id=entry.id
    )


@router.post(
    "/transfers",
    response_model=TransferResponse,
    dependencies=[Depends(require_api_key)],
)
async def create_transfer(
    body: TransferRequest,
    idempotency_key: str = Depends(require_idempotency_key),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> TransferResponse:
    try:
        money = Money(body.amount, body.currency)
        result = await transfer_use_case(
            uow,
            body.from_account_id,
            body.to_account_id,
            money,
            idempotency_key,
        )
    except (InvalidAmount, UnknownAccount, InsufficientFunds) as exc:
        raise _to_http_error(exc) from exc
    return TransferResponse(
        transfer_id=result.transfer_id,
        from_balance=result.debit_entry.balance_after,
        to_balance=result.credit_entry.balance_after if result.credit_entry else None,
    )


@router.get("/accounts/{account_id}", response_model=AccountResponse)
async def get_account(
    account_id: UUID,
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> AccountResponse:
    try:
        async with uow:
            account = await uow.accounts.get_for_update(account_id)
            # Read-only: release the lock immediately, nothing to commit.
            await uow.rollback()
    except UnknownAccount as exc:
        raise _to_http_error(exc) from exc
    return AccountResponse(
        id=account.id, balance=account.balance, currency=account.currency
    )
