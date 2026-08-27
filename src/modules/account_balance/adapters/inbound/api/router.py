import logging
from uuid import UUID

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException

from src.modules.account_balance.adapters.config.container import (
    AccountBalanceContainer,
)
from src.modules.account_balance.adapters.inbound.api.dependencies import (
    require_api_key,
    require_idempotency_key,
)
from src.modules.account_balance.adapters.inbound.api.schemas import (
    AccountResponse,
    CreateAccountRequest,
    MutationRequest,
    MutationResponse,
    TransferRequest,
    TransferResponse,
)
from src.modules.account_balance.adapters.outbound.repositories.sql.account_repo import (
    SqlAccountRepository,
)
from src.modules.account_balance.application.use_cases.create_dummy_account import (
    CreateDummyAccountUseCase,
)
from src.modules.account_balance.application.use_cases.credit import (
    CreditAccountUseCase,
)
from src.modules.account_balance.application.use_cases.debit import (
    DebitAccountUseCase,
)
from src.modules.account_balance.application.use_cases.transfer import TransferUseCase
from src.modules.account_balance.domain.errors import (
    InsufficientFunds,
    InvalidAmount,
    UnknownAccount,
    UnsupportedCurrency,
)
from src.modules.shared.application.ports.unit_of_work import UnitOfWork

router = APIRouter(prefix="/v1")

_DOMAIN_ERROR_HTTP_STATUS = {
    InvalidAmount: (400, "invalid_amount"),
    UnknownAccount: (404, "unknown_account"),
    InsufficientFunds: (409, "insufficient_funds"),
    UnsupportedCurrency: (400, "unsupported_currency"),
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
@inject
async def credit_account(
    account_id: UUID,
    body: MutationRequest,
    idempotency_key: str = Depends(require_idempotency_key),
    use_case: CreditAccountUseCase = Depends(
        Provide[AccountBalanceContainer.credit_use_case_provider]
    ),
) -> MutationResponse:
    try:
        entry = await use_case.execute(
            account_id, body.amount, body.currency, idempotency_key
        )
    except (
        InvalidAmount,
        UnknownAccount,
        InsufficientFunds,
        UnsupportedCurrency,
    ) as exc:
        raise _to_http_error(exc) from exc
    return MutationResponse(
        account_id=account_id, balance=entry.balance_after, entry_id=entry.id
    )


@router.post(
    "/accounts/{account_id}/debit",
    response_model=MutationResponse,
    dependencies=[Depends(require_api_key)],
)
@inject
async def debit_account(
    account_id: UUID,
    body: MutationRequest,
    idempotency_key: str = Depends(require_idempotency_key),
    use_case: DebitAccountUseCase = Depends(
        Provide[AccountBalanceContainer.debit_use_case_provider]
    ),
) -> MutationResponse:
    try:
        entry = await use_case.execute(
            account_id, body.amount, body.currency, idempotency_key
        )
    except (
        InvalidAmount,
        UnknownAccount,
        InsufficientFunds,
        UnsupportedCurrency,
    ) as exc:
        raise _to_http_error(exc) from exc
    return MutationResponse(
        account_id=account_id, balance=entry.balance_after, entry_id=entry.id
    )


@router.post(
    "/transfers",
    response_model=TransferResponse,
    dependencies=[Depends(require_api_key)],
)
@inject
async def create_transfer(
    body: TransferRequest,
    idempotency_key: str = Depends(require_idempotency_key),
    use_case: TransferUseCase = Depends(
        Provide[AccountBalanceContainer.transfer_use_case_provider]
    ),
) -> TransferResponse:
    try:
        result = await use_case.execute(
            body.from_account_id,
            body.to_account_id,
            body.amount,
            body.currency,
            idempotency_key,
        )
    except (
        InvalidAmount,
        UnknownAccount,
        InsufficientFunds,
        UnsupportedCurrency,
    ) as exc:
        raise _to_http_error(exc) from exc
    return TransferResponse(
        transfer_id=result.transfer_id,
        from_balance=result.debit_entry.balance_after,
        to_balance=result.credit_entry.balance_after if result.credit_entry else None,
    )


@router.post(
    "/accounts",
    response_model=AccountResponse,
    status_code=201,
    dependencies=[Depends(require_api_key)],
)
@inject
async def create_dummy_account(
    body: CreateAccountRequest,
    use_case: CreateDummyAccountUseCase = Depends(
        Provide[AccountBalanceContainer.create_dummy_account_use_case_provider]
    ),
) -> AccountResponse:
    # dev/test convenience only, no Idempotency-Key required
    try:
        account = await use_case.execute(body.initial_balance)
    except InvalidAmount as exc:
        raise _to_http_error(exc) from exc
    return AccountResponse(
        id=account.id, balance=account.balance, currency=account.currency
    )


@router.get("/accounts/{account_id}", response_model=AccountResponse)
@inject
async def get_account(
    account_id: UUID,
    uow: UnitOfWork = Depends(Provide[AccountBalanceContainer.shared.unit_of_work_provider]),
    logger: logging.Logger = Depends(Provide[AccountBalanceContainer.shared.logger_provider]),
) -> AccountResponse:
    try:
        async with uow as uow:
            accounts = SqlAccountRepository(session=uow.session, logger=logger)
            account = await accounts.get_for_update(account_id)
    except UnknownAccount as exc:
        raise _to_http_error(exc) from exc
    return AccountResponse(
        id=account.id, balance=account.balance, currency=account.currency
    )
