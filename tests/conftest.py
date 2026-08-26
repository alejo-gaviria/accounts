"""Shared pytest fixtures.

Test-database strategy
-----------------------
Integration-level tests (domain/application tests remain pure and need no
database) run against the ``db-test`` service defined in
``docker-compose.yml`` (Postgres 16, isolated from the ``db`` dev service,
tmpfs-backed so each run starts empty). Start it with::

    docker compose up -d db-test

The connection string is read from ``TEST_DATABASE_URL``, defaulting to the
docker-compose ``db-test`` service's exposed port. Adapter/integration tests
should be marked with ``@pytest.mark.integration`` and are expected to be
skipped in environments without the compose stack running.
"""

import os

import pytest

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://accounts_test:accounts_test@localhost:5433/accounts_test",
)


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "integration: requires the db-test docker-compose service"
    )


@pytest.fixture(scope="session")
def test_database_url() -> str:
    return TEST_DATABASE_URL
