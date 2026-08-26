import logging

from dependency_injector import containers, providers

from src.infrastructure.db import async_session_factory
from src.modules.account_balance.adapters.outbound.repositories.sql.uow import (
    SqlUnitOfWork,
)
from src.modules.account_balance.application.services.exchange_rates import (
    StaticExchangeRates,
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


class AccountBalanceContainer(containers.DeclarativeContainer):
    logger_provider = providers.Factory(logging.getLogger, "account_balance")

    session_factory_provider = providers.Object(async_session_factory)

    unit_of_work_provider = providers.Factory(
        SqlUnitOfWork,
        session_factory=session_factory_provider,
        logger=logger_provider,
    )

    exchange_rates_provider = providers.Singleton(StaticExchangeRates)

    credit_use_case_provider = providers.Factory(
        CreditAccountUseCase,
        uow=unit_of_work_provider,
        exchange_rates=exchange_rates_provider,
    )
    debit_use_case_provider = providers.Factory(
        DebitAccountUseCase,
        uow=unit_of_work_provider,
        exchange_rates=exchange_rates_provider,
    )
    transfer_use_case_provider = providers.Factory(
        TransferUseCase,
        uow=unit_of_work_provider,
        exchange_rates=exchange_rates_provider,
    )
    create_dummy_account_use_case_provider = providers.Factory(
        CreateDummyAccountUseCase,
        uow=unit_of_work_provider,
    )
