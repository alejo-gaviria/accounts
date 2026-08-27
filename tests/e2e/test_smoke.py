from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from src.config import settings

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_full_stack_credit_debit_transfer_and_get(app, engine):
    from_account_id = uuid4()
    to_account_id = uuid4()
    async with engine.begin() as conn:
        await conn.execute(
            text("INSERT INTO accounts (id, balance) VALUES (:id, 100)"),
            {"id": str(from_account_id)},
        )
        await conn.execute(
            text("INSERT INTO accounts (id, balance) VALUES (:id, 0)"),
            {"id": str(to_account_id)},
        )

    headers = {"X-API-Key": settings.api_key}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200

        resp = await client.post(
            f"/v1/accounts/{from_account_id}/credit",
            json={"amount": "25.00"},
            headers={**headers, "Idempotency-Key": "e2e-credit"},
        )
        assert resp.status_code == 200, resp.text
        assert Decimal(resp.json()["balance"]) == Decimal("125.00")

        resp = await client.post(
            f"/v1/accounts/{from_account_id}/debit",
            json={"amount": "5.00"},
            headers={**headers, "Idempotency-Key": "e2e-debit"},
        )
        assert resp.status_code == 200, resp.text
        assert Decimal(resp.json()["balance"]) == Decimal("120.00")

        resp = await client.post(
            "/v1/transfers",
            json={
                "from_account_id": str(from_account_id),
                "to_account_id": str(to_account_id),
                "amount": "20.00",
            },
            headers={**headers, "Idempotency-Key": "e2e-transfer"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert Decimal(body["from_balance"]) == Decimal("100.00")
        assert Decimal(body["to_balance"]) == Decimal("20.00")

        resp = await client.get(f"/v1/accounts/{from_account_id}")
        assert resp.status_code == 200
        assert Decimal(resp.json()["balance"]) == Decimal("100.00")

        # duplicate Idempotency-Key replays the original result instead of re-applying
        resp = await client.post(
            f"/v1/accounts/{from_account_id}/credit",
            json={"amount": "25.00"},
            headers={**headers, "Idempotency-Key": "e2e-credit"},
        )
        assert resp.status_code == 200
        assert Decimal(resp.json()["balance"]) == Decimal("125.00")  # unchanged
