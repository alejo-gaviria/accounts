import logging

from dependency_injector import containers, providers

from src.infrastructure.db import build_session_factory
from src.modules.shared.adapters.outbound.sql.unit_of_work import SqlUnitOfWork


class SharedContainer(containers.DeclarativeContainer):
    logger_provider = providers.Factory(logging.getLogger)

    session_factory_provider = providers.Singleton(build_session_factory)

    unit_of_work_provider = providers.Factory(
        SqlUnitOfWork,
        session_factory=session_factory_provider,
        logger=logger_provider,
    )
