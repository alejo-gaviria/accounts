import pytest


def test_pytest_runs() -> None:
    assert 1 + 1 == 2


@pytest.mark.asyncio
async def test_pytest_asyncio_runs() -> None:
    async def _identity(x: int) -> int:
        return x

    assert await _identity(42) == 42
