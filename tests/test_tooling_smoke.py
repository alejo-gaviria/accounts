"""Smoke test proving the pytest + pytest-asyncio toolchain is wired up.

This is intentionally infra-free: it exists to prove task 1.2 (test runner
setup) before any domain/application code exists. Domain and application
tests are added in the following phase following RED -> GREEN.
"""

import pytest


def test_pytest_runs() -> None:
    assert 1 + 1 == 2


@pytest.mark.asyncio
async def test_pytest_asyncio_runs() -> None:
    async def _identity(x: int) -> int:
        return x

    assert await _identity(42) == 42
