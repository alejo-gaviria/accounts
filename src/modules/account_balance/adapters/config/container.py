"""DI wiring for the account_balance module (design.md "Dependency
Injection" — project convention, `dependency-injector`,
`SharedContainer`-style: `providers.Singleton` for stateful/shared
things, `providers.Factory` for per-request instances).

Scope stays local to this module: DB session pool, repos, and use
cases only — no AWS/S3/SNS/SQS/Redis/JWT providers, none of those are
v1 scope here.

Deviation from the illustrative pseudocode in design.md, disclosed
explicitly: `account_repository_provider`/`ledger_repository_provider`
are wired with NO constructor args here (not `db_pool=...`). This
module's repos resolve the ambient DB session via a contextvar that
SqlUnitOfWork sets for the duration of `async with uow:` (see
adapters/outbound/repositories/sql/session_context.py) rather than
opening their own connection from the pool directly — that's what lets
them be genuine, safely-shared Singletons while still guaranteeing
every repository call in a given request runs on the exact same
transaction as the UnitOfWork (required for `FOR UPDATE` locking and
atomic ledger+balance commits). `db_session_provider` (the pool itself)
is still wired and still feeds `unit_of_work_provider`, which is the
one thing that actually needs it.
"""

from dependency_injector import containers, providers

from src.db import async_session_factory
from src.modules.account_balance.adapters.outbound.repositories.sql.account_repo import (
    SqlAccountRepository,
)
from src.modules.account_balance.adapters.outbound.repositories.sql.ledger_repo import (
    SqlLedgerRepository,
)
from src.modules.account_balance.adapters.outbound.repositories.sql.uow import (
    SqlUnitOfWork,
)
from src.modules.account_balance.application.use_cases.credit import (
    CreditAccountUseCase,
)
from src.modules.account_balance.application.use_cases.debit import (
    DebitAccountUseCase,
)
from src.modules.account_balance.application.use_cases.transfer import TransferUseCase


class AccountBalanceContainer(containers.DeclarativeContainer):
    # Stateful/shared for the process lifetime: the async sessionmaker
    # bound to src/db.py's engine (itself backed by a real asyncpg
    # connection pool).
    db_session_provider = providers.Object(async_session_factory)

    account_repository_provider = providers.Singleton(SqlAccountRepository)
    ledger_repository_provider = providers.Singleton(SqlLedgerRepository)

    # Per-request: a fresh session/transaction for every use-case call.
    unit_of_work_provider = providers.Factory(
        SqlUnitOfWork,
        session_factory=db_session_provider,
    )

    credit_use_case_provider = providers.Factory(
        CreditAccountUseCase,
        uow=unit_of_work_provider,
        account_repository=account_repository_provider,
        ledger_repository=ledger_repository_provider,
    )
    debit_use_case_provider = providers.Factory(
        DebitAccountUseCase,
        uow=unit_of_work_provider,
        account_repository=account_repository_provider,
        ledger_repository=ledger_repository_provider,
    )
    transfer_use_case_provider = providers.Factory(
        TransferUseCase,
        uow=unit_of_work_provider,
        account_repository=account_repository_provider,
        ledger_repository=ledger_repository_provider,
    )
