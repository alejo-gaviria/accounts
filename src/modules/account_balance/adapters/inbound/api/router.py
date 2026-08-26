"""Inbound HTTP API — credit/debit/transfer/get, the source of truth
for balance mutations (spec: balance-mutation-api).

Use cases are resolved through AccountBalanceContainer via `@inject` +
`Provide[...]` (design.md "Dependency Injection") — routes never
import/construct use-case classes directly. The container is wired to
this module in src/main.py's `create_app()` at startup.
"""

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
    MutationRequest,
    MutationResponse,
    TransferRequest,
    TransferResponse,
)
from src.modules.account_balance.application.gateways.account_repository import (
    AccountRepository,
)
from src.modules.account_balance.application.gateways.unit_of_work import UnitOfWork
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
        money = Money(body.amount, body.currency)
        entry = await use_case.execute(account_id, money, idempotency_key)
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
        money = Money(body.amount, body.currency)
        entry = await use_case.execute(account_id, money, idempotency_key)
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
@inject
async def create_transfer(
    body: TransferRequest,
    idempotency_key: str = Depends(require_idempotency_key),
    use_case: TransferUseCase = Depends(
        Provide[AccountBalanceContainer.transfer_use_case_provider]
    ),
) -> TransferResponse:
    try:
        money = Money(body.amount, body.currency)
        result = await use_case.execute(
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
@inject
async def get_account(
    account_id: UUID,
    uow: UnitOfWork = Depends(Provide[AccountBalanceContainer.unit_of_work_provider]),
    account_repository: AccountRepository = Depends(
        Provide[AccountBalanceContainer.account_repository_provider]
    ),
) -> AccountResponse:
    # No dedicated read use case for a single-repo lookup (no separate
    # non-locking read method exists on the port either — see
    # account_repo.py); reuses get_for_update()+immediate rollback,
    # same as before the DI refactor.
    try:
        async with uow:
            account = await account_repository.get_for_update(account_id)
            await uow.rollback()
    except UnknownAccount as exc:
        raise _to_http_error(exc) from exc
    return AccountResponse(
        id=account.id, balance=account.balance, currency=account.currency
    )
