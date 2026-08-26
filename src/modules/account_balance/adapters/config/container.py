"""DI wiring for the account_balance module (design.md "Dependency
Injection" — project convention, `dependency-injector`,
`SharedContainer`-style: `providers.Singleton` for stateful/shared
things, `providers.Factory` for per-request instances).

Everything is injected, nothing ambient — including the DB session and
the logger. Repositories are deliberately NOT wired here as
container-level providers: a singleton repo can't safely hold a
per-request DB session/transaction. Instead only `session_factory_provider`
(Singleton — reuses src/db.py's existing async_sessionmaker/engine
setup) and `logger_provider` (Factory) are injected into
`unit_of_work_provider` (Factory — a fresh SqlUnitOfWork, and therefore
a fresh transaction, per resolution). SqlUnitOfWork.__aenter__
constructs SqlAccountRepository/SqlLedgerRepository itself, passing
them the session + logger — see unit_of_work.py's port docstring.

Scope stays local to this module: session factory, UoW, use cases only
— no AWS/S3/SNS/SQS/Redis/JWT providers, none of those are v1 scope
here.
"""

import logging

from dependency_injector import containers, providers

from src.db import async_session_factory
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
    # Named (not root) logger, still injected rather than grabbed via a
    # module-level `logging.getLogger(__name__)` anywhere in this module.
    logger_provider = providers.Factory(logging.getLogger, "account_balance")

    # Wraps the sessionmaker/engine already set up in src/db.py (which
    # connects as the restricted accounts_app role) rather than building
    # a second one here.
    session_factory_provider = providers.Object(async_session_factory)

    unit_of_work_provider = providers.Factory(
        SqlUnitOfWork,
        session_factory=session_factory_provider,
        logger=logger_provider,
    )

    credit_use_case_provider = providers.Factory(
        CreditAccountUseCase,
        uow=unit_of_work_provider,
    )
    debit_use_case_provider = providers.Factory(
        DebitAccountUseCase,
        uow=unit_of_work_provider,
    )
    transfer_use_case_provider = providers.Factory(
        TransferUseCase,
        uow=unit_of_work_provider,
    )
