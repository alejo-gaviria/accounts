from dependency_injector import containers, providers

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
from src.modules.shared.adapters.config.container import SharedContainer


class AccountBalanceContainer(containers.DeclarativeContainer):
    shared = providers.Container(SharedContainer)

    exchange_rates_provider = providers.Singleton(StaticExchangeRates)

    credit_use_case_provider = providers.Factory(
        CreditAccountUseCase,
        uow=shared.unit_of_work_provider,
        logger=shared.logger_provider,
        exchange_rates=exchange_rates_provider,
    )
    debit_use_case_provider = providers.Factory(
        DebitAccountUseCase,
        uow=shared.unit_of_work_provider,
        logger=shared.logger_provider,
        exchange_rates=exchange_rates_provider,
    )
    transfer_use_case_provider = providers.Factory(
        TransferUseCase,
        uow=shared.unit_of_work_provider,
        logger=shared.logger_provider,
        exchange_rates=exchange_rates_provider,
    )
    create_dummy_account_use_case_provider = providers.Factory(
        CreateDummyAccountUseCase,
        uow=shared.unit_of_work_provider,
        logger=shared.logger_provider,
    )
