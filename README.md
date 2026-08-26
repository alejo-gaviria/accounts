# effex-accounts

Account balances microservice. Hexagonal `account_balance` module:
domain owns the `Account` aggregate and immutable `LedgerEntry` rows;
balance is a cached projection updated in the same DB transaction that
appends the ledger row. Mutations (credit/debit/transfer) are owned by
this service's own HTTP API, Postgres-backed, idempotent (via a
required `Idempotency-Key` header), and concurrency-safe via
pessimistic row locks (`SELECT ... FOR UPDATE`).

See `.sdd/account-balances/design.md` for the full technical design
(schema, concurrency protocol, API contract) and `.sdd/account-balances/spec.md`
for the behavioral spec.

## Local dev

Prerequisites: [uv](https://docs.astral.sh/uv/), Docker (with `docker compose`).

```bash
# Install dependencies (creates .venv, reads uv.lock)
uv sync

# Start Postgres (dev service, port 5432)
make up          # == docker compose up -d db

# Run migrations
make migrate      # == uv run alembic upgrade head

# Run the app
uv run uvicorn src.infrastructure.main:app --reload
```

Configuration is read from environment variables / a local `.env` file
(see `.env.example`) via `src/config.py`. Defaults match
`docker-compose.yml`'s `db` service, so a bare `uv sync && make up && make migrate`
works out of the box with no `.env` file.

The initial migration also creates a restricted `accounts_app` Postgres
role (INSERT/SELECT-only on `ledger_entries` — no UPDATE/DELETE,
enforcing the append-only ledger invariant at the database level;
INSERT/SELECT/UPDATE on `accounts`; no DDL rights at all). The running
application always connects as `accounts_app`, never as the
owner/migration role used to run Alembic.

### Smoke-testing credit/debit/transfer

Credit/debit/transfer all operate on an existing account, so you need
one to point them at. The easiest way is `POST /v1/accounts` — a
**dev/test convenience endpoint, not a real account-onboarding flow**
(no KYC, no customer linkage, it just inserts a row):

```bash
curl -X POST http://localhost:8000/v1/accounts \
  -H "X-API-Key: 00000000-0000-0000-0000-000000000000" \
  -H "Content-Type: application/json" \
  -d '{"currency": "USD", "initial_balance": "100.00"}'
# => 201 {"id": "<uuid>", "balance": "100.00", "currency": "USD"}

curl -X POST http://localhost:8000/v1/accounts/<uuid>/credit \
  -H "X-API-Key: 00000000-0000-0000-0000-000000000000" \
  -H "Idempotency-Key: smoke-1" \
  -H "Content-Type: application/json" \
  -d '{"amount": "10.00"}'
```

**Fallback / alternative**: if you'd rather seed a row directly (e.g.
to test with a specific known UUID, or against a DB where the app
isn't running yet), connect with `psql` and insert manually:

```bash
psql postgresql://accounts:accounts@localhost:5442/accounts \
  -c "INSERT INTO accounts (id, balance, currency) VALUES (gen_random_uuid(), 100.00, 'USD') RETURNING id;"
```

Both approaches land in the same `accounts` table — the API endpoint
is just faster for routine local testing since it doesn't require a
`psql` session.

## Tests

```bash
uv run pytest                       # domain + application (pure, no infra)
make test                            # also brings up db-test and runs
                                      # the full suite including
                                      # @pytest.mark.integration /
                                      # tests/e2e (needs a live db-test)
```

Test-database strategy: a separate `db-test` compose service (Postgres
16, port 5433, tmpfs-backed so each run starts from empty) keeps
integration/e2e tests fully isolated from the dev `db` service and its
data. Integration and E2E tests self-skip (not fail) if `db-test` isn't
reachable.

## Container / deployment shape

`Dockerfile` builds a `python:3.12-slim` image (`uv sync --frozen --no-dev`,
`CMD uvicorn src.infrastructure.main:app --host 0.0.0.0 --port 8000`). The AWS target
shape (not provisioned by anything in this repo) is ECS/Fargate running
that image against a managed RDS Postgres 16 instance, with
`DATABASE_URL`/`APP_DB_PASSWORD` etc. injected via Secrets Manager.

## Known risks (tracked, not yet resolved)

- **API-key auth is a v1/local-only placeholder.** `adapters/inbound/api/dependencies.py`'s
  `require_api_key` compares a single static `X-API-Key` value
  (`API_KEY` env var, default `00000000-0000-0000-0000-000000000000`)
  in plain Python — no hashing, no rotation, no per-client scoping, no
  rate limiting. **Do not deploy this anywhere other than local
  development without replacing it** with real credential issuance
  (JWT or another proper service-to-service auth mechanism).
- Live-Postgres verification: `make up && make migrate && make test`
  has been run end-to-end successfully (migration applies cleanly,
  `accounts_app` grants are exactly as designed, full test suite
  including `@pytest.mark.integration`/`tests/e2e` passes against a
  real `db`/`db-test`), and the app has been booted with `uvicorn` and
  smoke-tested live via `curl` (including `POST /v1/accounts` ->
  `POST .../credit`). Re-verify after any change to the schema,
  migration, or connection settings before trusting a given commit in
  a shared environment.
- `.env.example` was not updated as part of this change (blocked by
  this environment's own file-permission policy on dotenv paths, not a
  design decision) — see the apply-progress notes for the intended
  content (`DATABASE_URL`, `APP_DB_ROLE`, `APP_DB_PASSWORD`, `API_KEY`).
