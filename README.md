# SuperCool Finances-accounts

Critical financial microservice that owns customer account balances. Every balance is denominated in MXN. All mutations (credit, debit, transfer) are idempotent and recorded as immutable ledger entries.

---

## Setup

**Prerequisites:** [uv](https://docs.astral.sh/uv/), Docker with Compose.

```bash
# 1. Install dependencies
uv sync

# 2. Start Postgres (dev DB on port 5442)
make up

# 3. Apply migrations and create the restricted app role
make migrate

# 4. Start the server
uv run uvicorn src.infrastructure.main:app --reload
```

The server starts at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

No `.env` file needed for local dev — defaults in `src/config.py` match `docker-compose.yml` out of the box.

---

## Authentication

Every request requires an `X-API-Key` header.

```
X-API-Key: 00000000-0000-0000-0000-000000000000
```

> **Note:** This is a static v1/local-only placeholder. Replace with real auth before deploying.

---

## Endpoints

### Create an account (dev convenience)

```bash
curl -s -X POST http://localhost:8000/v1/accounts \
  -H "X-API-Key: 00000000-0000-0000-0000-000000000000" \
  -H "Content-Type: application/json" \
  -d '{"initial_balance": "100.00"}'
```

```json
{"id": "f47ac10b-...", "balance": "100.00", "currency": "MXN"}
```

> This is a dev/test convenience — no KYC, no customer linkage. Use the returned `id` in the requests below.

---

### Get account balance

```bash
curl -s http://localhost:8000/v1/accounts/<account_id>
```

```json
{"id": "f47ac10b-...", "balance": "100.00", "currency": "MXN"}
```

No auth required for reads.

---

### Credit (add funds)

Requires `Idempotency-Key` header — use any unique string per operation.

```bash
curl -s -X POST http://localhost:8000/v1/accounts/<account_id>/credit \
  -H "X-API-Key: 00000000-0000-0000-0000-000000000000" \
  -H "Idempotency-Key: my-unique-op-1" \
  -H "Content-Type: application/json" \
  -d '{"amount": "50.00", "currency": "MXN"}'
```

```json
{"account_id": "f47ac10b-...", "balance": "150.00", "entry_id": "a1b2c3d4-..."}
```

Credit in USD (auto-converted to MXN at the static rate):

```bash
-d '{"amount": "10.00", "currency": "USD"}'
# 10 USD × 16.96 = 169.60 MXN added
```

---

### Debit (remove funds)

Same structure as credit. Returns `409` if balance is insufficient.

```bash
curl -s -X POST http://localhost:8000/v1/accounts/<account_id>/debit \
  -H "X-API-Key: 00000000-0000-0000-0000-000000000000" \
  -H "Idempotency-Key: my-unique-op-2" \
  -H "Content-Type: application/json" \
  -d '{"amount": "30.00", "currency": "MXN"}'
```

```json
{"account_id": "f47ac10b-...", "balance": "120.00", "entry_id": "b2c3d4e5-..."}
```

---

### Transfer

Moves funds atomically between two accounts. Both accounts are locked in ascending UUID order to prevent deadlocks.

```bash
curl -s -X POST http://localhost:8000/v1/transfers \
  -H "X-API-Key: 00000000-0000-0000-0000-000000000000" \
  -H "Idempotency-Key: my-unique-op-3" \
  -H "Content-Type: application/json" \
  -d '{
    "from_account_id": "f47ac10b-...",
    "to_account_id":   "a1b2c3d4-...",
    "amount": "25.00",
    "currency": "MXN"
  }'
```

```json
{"transfer_id": "c3d4e5f6-...", "from_balance": "95.00", "to_balance": "125.00"}
```

---

## Idempotency

`credit`, `debit`, and `transfer` all require a `Idempotency-Key` header. Replaying the same key returns the original response — the operation is not re-executed.

```bash
# First call: applies the credit
curl ... -H "Idempotency-Key: op-123" -d '{"amount": "50.00"}'
# => 200, balance increases

# Same key again: returns the same result, balance unchanged
curl ... -H "Idempotency-Key: op-123" -d '{"amount": "50.00"}'
# => 200, same entry_id, same balance
```

---

## Currency conversion

All balances are stored in MXN. The `currency` field on request body specifies the *input* amount's currency — it is converted to MXN before being applied.

| Currency | MXN per 1 unit |
|----------|----------------|
| MXN      | 1.00           |
| USD      | 16.96          |
| CAD      | 12.22          |
| COP      | 0.00549        |
| CNY      | 2.52           |

Unsupported currencies return `400 {"error": {"code": "unsupported_currency", ...}}`.

The ledger records `original_amount`, `original_currency`, and `fx_rate` on every entry so the caller's original intent is always reconstructable.

---

## Error responses

All errors follow the same shape:

```json
{"error": {"code": "<code>", "message": "<human-readable>"}}
```

| HTTP | Code | When |
|------|------|------|
| 400 | `invalid_amount` | Amount ≤ 0 |
| 400 | `unsupported_currency` | Currency not in the rate table |
| 400 | `missing_idempotency_key` | Header absent or blank |
| 401 | `unauthorized` | Missing or wrong `X-API-Key` |
| 404 | `unknown_account` | Account ID not found |
| 409 | `insufficient_funds` | Debit/transfer exceeds balance |

---

## Tests

```bash
# Fast: domain + application (pure, no infra)
uv run pytest

# Full suite including integration and E2E (needs Postgres)
make test
```

`make test` brings up `db-test` (a separate Postgres on port 5433, tmpfs-backed, starts empty each run), runs migrations against it, then runs the full suite. Integration and E2E tests self-skip — not fail — if `db-test` is unreachable.

---

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://accounts:accounts@localhost:5442/accounts` | Migration/owner role connection |
| `APP_DB_ROLE` | `accounts_app` | Restricted app role (INSERT/SELECT only on ledger) |
| `APP_DB_PASSWORD` | `accounts_app` | Password for `APP_DB_ROLE` |
| `API_KEY` | `00000000-0000-0000-0000-000000000000` | Static API key (v1 placeholder) |

Copy `.env.example` to `.env` to override any of these.

---

## Make targets

| Target | What it does |
|--------|-------------|
| `make up` | Start dev Postgres (`db` service, port 5442) |
| `make down` | Stop and remove containers |
| `make migrate` | Run `alembic upgrade head` against dev DB |
| `make test` | Bring up `db-test`, run full test suite, tear down |

---

## Architecture notes

- **Hexagonal (ports and adapters)**: domain has zero infrastructure imports. Application layer coordinates use cases. SQL adapters live in `adapters/outbound/`.
- **Immutable ledger**: the `accounts_app` Postgres role has `UPDATE`/`DELETE` revoked on `ledger_entries` at the DB level. Balance is a cached projection updated in the same transaction that appends the ledger row — it is always rebuildable via `SUM(ledger_entries)`.
- **Concurrency**: mutations acquire a `SELECT ... FOR UPDATE` row lock. Transfers lock both rows in ascending UUID order to avoid deadlocks.
- **Dependency injection**: `dependency-injector` containers wire use cases. `SharedContainer` owns logger, session factory, and UoW; `AccountBalanceContainer` composes it.

Full technical design: `.sdd/account-balances/design.md`
Behavioral spec: `.sdd/account-balances/spec.md`
AI usage log: `docs/PROMPTS.md`
