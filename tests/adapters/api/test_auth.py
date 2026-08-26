"""X-API-Key placeholder auth guard on mutation routes: requests
without/with-wrong X-API-Key get 401. GET (read-only) is intentionally
not guarded.
"""

from uuid import uuid4

import pytest


@pytest.mark.asyncio
async def test_credit_without_api_key_returns_401(client):
    resp = await client.post(
        f"/v1/accounts/{uuid4()}/credit",
        json={"amount": "10.00"},
        headers={"Idempotency-Key": "k1"},
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"


@pytest.mark.asyncio
async def test_credit_with_wrong_api_key_returns_401(client):
    resp = await client.post(
        f"/v1/accounts/{uuid4()}/credit",
        json={"amount": "10.00"},
        headers={"X-API-Key": "wrong-key", "Idempotency-Key": "k1"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_debit_without_api_key_returns_401(client):
    resp = await client.post(
        f"/v1/accounts/{uuid4()}/debit",
        json={"amount": "10.00"},
        headers={"Idempotency-Key": "k1"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_transfer_without_api_key_returns_401(client):
    resp = await client.post(
        "/v1/transfers",
        json={
            "from_account_id": str(uuid4()),
            "to_account_id": str(uuid4()),
            "amount": "1.00",
        },
        headers={"Idempotency-Key": "k1"},
    )
    assert resp.status_code == 401
