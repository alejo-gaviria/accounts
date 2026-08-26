"""RED -> GREEN: mutation validation + error-to-HTTP mapping.

Spec: balance-mutation-api / Mutation Validation scenarios. Design:
400 InvalidAmount, 404 UnknownAccount, 409 InsufficientFunds, error
body shape {error: {code, message}}.
"""

from decimal import Decimal
from uuid import uuid4

import pytest

from src.modules.account_balance.domain.account import Account


@pytest.mark.asyncio
async def test_zero_amount_rejected_with_400(client, valid_headers, accounts_store):
    account = Account(id=uuid4(), balance=Decimal("10"))
    accounts_store[account.id] = account

    resp = await client.post(
        f"/v1/accounts/{account.id}/credit",
        json={"amount": "0"},
        headers=valid_headers,
    )

    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "invalid_amount"


@pytest.mark.asyncio
async def test_negative_amount_rejected_with_400(client, valid_headers, accounts_store):
    account = Account(id=uuid4(), balance=Decimal("10"))
    accounts_store[account.id] = account

    resp = await client.post(
        f"/v1/accounts/{account.id}/debit",
        json={"amount": "-5"},
        headers=valid_headers,
    )

    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "invalid_amount"


@pytest.mark.asyncio
async def test_unknown_account_returns_404(client, valid_headers):
    resp = await client.post(
        f"/v1/accounts/{uuid4()}/credit",
        json={"amount": "10"},
        headers=valid_headers,
    )

    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "unknown_account"


@pytest.mark.asyncio
async def test_insufficient_funds_returns_409(client, valid_headers, accounts_store):
    account = Account(id=uuid4(), balance=Decimal("5"))
    accounts_store[account.id] = account

    resp = await client.post(
        f"/v1/accounts/{account.id}/debit",
        json={"amount": "10"},
        headers=valid_headers,
    )

    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "insufficient_funds"


@pytest.mark.asyncio
async def test_missing_idempotency_key_returns_400(client, accounts_store):
    account = Account(id=uuid4(), balance=Decimal("10"))
    accounts_store[account.id] = account

    from src.config import settings

    resp = await client.post(
        f"/v1/accounts/{account.id}/credit",
        json={"amount": "5"},
        headers={"X-API-Key": settings.api_key},
    )

    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_successful_credit_returns_200_with_new_balance(
    client, valid_headers, accounts_store
):
    account = Account(id=uuid4(), balance=Decimal("10"))
    accounts_store[account.id] = account

    resp = await client.post(
        f"/v1/accounts/{account.id}/credit",
        json={"amount": "5"},
        headers=valid_headers,
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["balance"] == "15.00" or Decimal(body["balance"]) == Decimal("15")


@pytest.mark.asyncio
async def test_get_account_returns_current_balance(client, accounts_store):
    account = Account(id=uuid4(), balance=Decimal("42.50"))
    accounts_store[account.id] = account

    resp = await client.get(f"/v1/accounts/{account.id}")

    assert resp.status_code == 200
    assert Decimal(resp.json()["balance"]) == Decimal("42.50")


@pytest.mark.asyncio
async def test_credit_in_usd_converts_to_mxn_before_applying(
    client, valid_headers, accounts_store
):
    account = Account(id=uuid4(), balance=Decimal("0"))
    accounts_store[account.id] = account

    resp = await client.post(
        f"/v1/accounts/{account.id}/credit",
        json={"amount": "10.00", "currency": "USD"},
        headers=valid_headers,
    )

    assert resp.status_code == 200
    # 10 USD * 16.96 MXN/USD = 169.60 MXN.
    assert Decimal(resp.json()["balance"]) == Decimal("169.6000")


@pytest.mark.asyncio
async def test_unsupported_currency_rejected_with_400(
    client, valid_headers, accounts_store
):
    account = Account(id=uuid4(), balance=Decimal("10"))
    accounts_store[account.id] = account

    resp = await client.post(
        f"/v1/accounts/{account.id}/credit",
        json={"amount": "10.00", "currency": "EUR"},
        headers=valid_headers,
    )

    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "unsupported_currency"
