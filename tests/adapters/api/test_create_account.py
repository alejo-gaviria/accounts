"""POST /v1/accounts tests — dev/test convenience endpoint: happy path
creates a fresh account and returns 201; a negative initial_balance is
rejected the same way credit/debit reject a negative amount (400,
InvalidAmount, same error body shape). No `currency` field at all —
every account is MXN by construction.
"""

from decimal import Decimal

import pytest


@pytest.mark.asyncio
async def test_create_account_with_defaults_returns_201(client, valid_headers):
    resp = await client.post("/v1/accounts", json={}, headers=valid_headers)

    assert resp.status_code == 201
    body = resp.json()
    assert body["currency"] == "MXN"
    assert Decimal(body["balance"]) == Decimal("0")
    assert "id" in body


@pytest.mark.asyncio
async def test_create_account_with_initial_balance(client, valid_headers):
    resp = await client.post(
        "/v1/accounts",
        json={"initial_balance": "100.00"},
        headers=valid_headers,
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["currency"] == "MXN"
    assert Decimal(body["balance"]) == Decimal("100.00")


@pytest.mark.asyncio
async def test_create_account_ignores_a_currency_field_if_sent(
    client, valid_headers
):
    # Pydantic silently drops unknown fields, so this must not change
    # the outcome: still MXN, regardless of what the caller sends.
    resp = await client.post(
        "/v1/accounts",
        json={"currency": "USD", "initial_balance": "10.00"},
        headers=valid_headers,
    )

    assert resp.status_code == 201
    assert resp.json()["currency"] == "MXN"


@pytest.mark.asyncio
async def test_create_account_negative_initial_balance_rejected_with_400(
    client, valid_headers
):
    resp = await client.post(
        "/v1/accounts",
        json={"initial_balance": "-1.00"},
        headers=valid_headers,
    )

    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "invalid_amount"


@pytest.mark.asyncio
async def test_create_account_without_api_key_returns_401(client):
    resp = await client.post("/v1/accounts", json={})

    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_created_account_can_immediately_receive_a_credit(
    client, valid_headers
):
    create_resp = await client.post(
        "/v1/accounts",
        json={"initial_balance": "10.00"},
        headers=valid_headers,
    )
    account_id = create_resp.json()["id"]

    credit_resp = await client.post(
        f"/v1/accounts/{account_id}/credit",
        json={"amount": "5.00"},
        headers=valid_headers,
    )

    assert credit_resp.status_code == 200
    assert Decimal(credit_resp.json()["balance"]) == Decimal("15.00")
