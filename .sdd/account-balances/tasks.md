# Tasks: account-balances

Git root: `accounts/.git` (branch main). All paths relative to `accounts/`.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~900–1300 (uv.lock/alembic boilerplate excluded as generated) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR1 → PR2 → PR3 → PR4 |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | PR | Focused test command | Runtime harness | Rollback boundary |
|---|---|---|---|---|---|
| 1 | Tooling+infra: uv, docker-compose Postgres 16 (dev+test), prune scaffolds, Alembic init+initial migration | PR1 | `alembic upgrade head` against test compose | `docker compose up db` | Revert compose/pyproject/migrations dir only |
| 2 | Domain+application layer (Account, LedgerEntry, use cases, idempotency) | PR2 | `pytest tests/domain tests/application` | N/A — pure logic, no live infra needed | Revert `domain/`,`application/` |
| 3 | SQL adapters (repos, UoW, row locks, grants) | PR3 | `pytest tests/adapters/sql -m integration` | `docker compose up db-test` + integration suite | Revert `adapters/outbound/repositories/sql/` |
| 4 | Inbound API+auth placeholder, wiring, entrypoint, docs | PR4 | `pytest tests/adapters/api` | `uvicorn src.main:app` + `curl` smoke against compose | Revert `adapters/inbound/api/`, `src/main.py` |

## Phase 1: Tooling & Infra Foundation
- [ ] 1.1 Switch `accounts/pyproject.toml` to `uv`; generate `uv.lock`; remove `requirements.txt`, `stripe` dep, `[tool.vercel]`, `api.index:app` ref.
- [ ] 1.2 Add pytest, pytest-asyncio, httpx dev deps; define test-db strategy (docker-compose Postgres test service).
- [ ] 1.3 Add `docker-compose.yml`: Postgres 16 dev + test services.
- [ ] 1.4 Prune `.gitkeep`-only dirs: `cron/`, `sqs/`, `dynamo/`, `redis/` under `modules/account_balance/`.
- [ ] 1.5 `alembic init` under `adapters/outbound/repositories/sql/migrations/`; wire `alembic.ini` to config DB URL.

## Phase 2: Schema & Migration
- [ ] 2.1 Revision: create `accounts` (UUID PK, currency CHAR(3), `balance NUMERIC(20,4) CHECK (balance >= 0)`, version, timestamps).
- [ ] 2.2 Revision: create `ledger_entries` (append-only, FK account_id, unique `(account_id, idempotency_key)`).
- [ ] 2.3 Revision: REVOKE UPDATE/DELETE, GRANT INSERT/SELECT-only on `ledger_entries` for app role.
- [ ] 2.4 Add `make migrate` / compose step running `alembic upgrade head` in local dev.

## Phase 3: Domain Layer (RED→GREEN)
- [ ] 3.1 RED: `Account` rejects mutation resulting in balance < 0.
- [ ] 3.2 GREEN: `domain/account.py` aggregate + invariants.
- [ ] 3.3 RED: `LedgerEntry` immutable after construction.
- [ ] 3.4 GREEN: `domain/ledger_entry.py`, `domain/money.py`, `domain/errors.py`.

## Phase 4: Application Layer (RED→GREEN)
- [ ] 4.1 RED: credit increases balance + writes ledger row.
- [ ] 4.2 GREEN: `use_cases/credit.py`.
- [ ] 4.3 RED: debit raises `InsufficientFunds`, writes no ledger row.
- [ ] 4.4 GREEN: `use_cases/debit.py`.
- [ ] 4.5 RED: transfer locks both accounts ascending-`id` order; concurrent opposite-order transfers don't deadlock; two linked ledger rows written atomically.
- [ ] 4.6 GREEN: `use_cases/transfer.py`.
- [ ] 4.7 RED: duplicate `Idempotency-Key` returns original result, no re-apply.
- [ ] 4.8 GREEN: `application/services/idempotency.py`.
- [ ] 4.9 Define ports: `gateways/account_repository.py`, `ledger_repository.py`, `unit_of_work.py`.

## Phase 5: Outbound SQL Adapters
- [ ] 5.1 `sql/models.py` SQLAlchemy models for Account, LedgerEntry.
- [ ] 5.2 `sql/account_repo.py` — `SELECT ... FOR UPDATE` per mutation.
- [ ] 5.3 `sql/ledger_repo.py` — insert/select only, no update/delete methods.
- [ ] 5.4 `sql/uow.py` — tx boundary, ascending-id lock order for transfer.
- [ ] 5.5 Integration test against compose Postgres: verify lock behavior + DB-level grant rejection (UPDATE/DELETE on ledger_entries fails).

## Phase 6: Inbound API + Auth
- [ ] 6.1 RED: requests without/with-wrong `X-API-Key` → 401.
- [ ] 6.2 GREEN: `api/dependencies.py` static key check vs `00000000-0000-0000-0000-000000000000`; code comment flagging this as a v1/local-only placeholder, NOT production-grade — replace with real credential issuance (JWT/service-to-service auth) before real deployment.
- [ ] 6.3 `api/schemas.py` request/response models for credit/debit/transfer.
- [ ] 6.4 RED: validation scenarios — zero/negative amount, unknown account, insufficient funds → correct error codes.
- [ ] 6.5 GREEN: `api/router.py` wired to use cases + error-to-HTTP mapping.

## Phase 7: Wiring & Entrypoint
- [ ] 7.1 `src/main.py` FastAPI app factory registering router; `src/config.py` (pydantic-settings), `src/db.py` async engine/session.
- [ ] 7.2 Fix entrypoint to `src.main:app` in pyproject + Dockerfile CMD (uvicorn, local + container).
- [ ] 7.3 E2E smoke: boot via `uvicorn src.main:app` against compose Postgres, run migrations, exercise all three endpoints.

## Phase 8: Cleanup
- [ ] 8.1 Update `accounts/README.md`: local dev (uv, docker-compose, alembic); explicitly flag API-key auth as a tracked pre-production risk.
- [ ] 8.2 Confirm all changes scoped under `accounts/`; no stray root-level edits outside the `accounts/.git` tree.
