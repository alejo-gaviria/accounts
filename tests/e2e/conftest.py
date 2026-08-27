import logging

import pytest
from dependency_injector import providers
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.infrastructure.main import app as fastapi_app
from src.modules.shared.adapters.outbound.sql.unit_of_work import SqlUnitOfWork

_logger = logging.getLogger("test.account_balance.e2e")


@pytest.fixture
def app(engine, app_role_engine_url):
    container = fastapi_app.container
    test_app_engine = create_async_engine(app_role_engine_url)
    session_factory = async_sessionmaker(test_app_engine, expire_on_commit=False)

    container.shared.unit_of_work_provider.override(
        providers.Factory(
            SqlUnitOfWork, session_factory=session_factory, logger=_logger
        )
    )

    yield fastapi_app

    container.shared.unit_of_work_provider.reset_override()
