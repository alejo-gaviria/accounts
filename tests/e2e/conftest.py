"""E2E fixtures: the REAL FastAPI app (src.main:app), REAL SqlUnitOfWork
and SQL repos - only the DB connection target is swapped (from the dev
`db` service to the test-db `engine`/`app_role_engine_url` fixtures in
the root conftest), via the same `app.dependency_overrides` mechanism
FastAPI provides for testing.
"""

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.main import app as fastapi_app
from src.modules.account_balance.adapters.inbound.api.dependencies import (
    get_unit_of_work,
)
from src.modules.account_balance.adapters.outbound.repositories.sql.uow import (
    SqlUnitOfWork,
)


@pytest.fixture
def app(engine, app_role_engine_url):
    test_app_engine = create_async_engine(app_role_engine_url)
    session_factory = async_sessionmaker(test_app_engine, expire_on_commit=False)

    def _override_uow() -> SqlUnitOfWork:
        return SqlUnitOfWork(session_factory)

    fastapi_app.dependency_overrides[get_unit_of_work] = _override_uow
    yield fastapi_app
    fastapi_app.dependency_overrides.pop(get_unit_of_work, None)
