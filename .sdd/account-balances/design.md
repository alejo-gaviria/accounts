# Design: account-balances microservice

## Technical Approach
Hexagonal `account_balance` module. Domain owns `Account` + immutable `LedgerEntry`; balance is a cached projection updated in the same transaction that appends the ledger row. Mutations are API-owned, Postgres-backed, idempotent, and concurrency-safe via pessimistic row locks. v1 is locally runnable (docker-compose Postgres 16) and structurally AWS-ready (ECS/Fargate + RDS + Secrets Manager) without executing any provisioning.

## Module Layout (under `accounts/src/modules/account_balance/`)
- `domain/` → `account.py` (Account aggregate, invariants), `ledger_entry.py` (immutable entry, EntryType credit/debit), `money.py` (amount/currency VO), `errors.py` (InsufficientFunds, UnknownAccount, InvalidAmount).
- `application/use_cases/` → `credit.py`, `debit.py`, `transfer.py` — each a **class** (`CreditAccountUseCase`, `DebitAccountUseCase`, `TransferUseCase`) with dependencies injected via constructor, never plain functions.
- `application/gateways/` → `account_repository.py`, `ledger_repository.py`, `unit_of_work.py` (ports/Protocols).
- `application/services/` → `idempotency.py` (replay orchestration), `exchange_rates.py` — `StaticExchangeRates`, a simple class with a fixed rate table (no external API), see "Currency Conversion" below.
- `adapters/inbound/api/` → `router.py`, `schemas.py`, `dependencies.py`.
- `adapters/outbound/repositories/sql/` → `dbos/` (SQLAlchemy declarative model classes, one per entity: `account.py`, `ledger_entry.py`, `base.py` — NOT a flat `models.py`; each DBO exposes a `@classmethod from_domain(cls, entity) -> Row` used by repos instead of manual field-by-field construction), `account_repo.py`, `ledger_repo.py`, `uow.py`, `migrations/`.
- `adapters/config/` → `container.py` — `AccountBalanceContainer(containers.DeclarativeContainer)` wiring every use case class and its dependencies (session pool, repos, clock/id-generator if needed). Routes resolve use cases through the container, never construct them directly.
- **Prune** (delete `.gitkeep` folders, not needed v1): `adapters/inbound/cron/`, `adapters/inbound/sqs/`, `adapters/outbound/repositories/dynamo/`, `adapters/outbound/repositories/redis/`.
- New service root: `src/infrastructure/main.py` (FastAPI app factory), `src/config.py` (pydantic-settings), `src/infrastructure/db.py` (async engine/session).

## Domain Model + DB Schema
`accounts` (aggregate + balance projection — **balance is always MXN**, see "Currency Conversion"):
```
id            UUID PK
currency      CHAR(3) NOT NULL DEFAULT 'MXN'   -- canonical, always MXN (v1 has no other value)
balance       NUMERIC(20,4) NOT NULL DEFAULT 0 CHECK (balance >= 0)
version       BIGINT NOT NULL DEFAULT 0         -- optimistic aux/audit
created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
```
`ledger_entries` (immutable, append-only — INSERT/SELECT only, no UPDATE/DELETE):
```
id                 UUID PK
account_id         UUID NOT NULL REFERENCES accounts(id)
entry_type         TEXT NOT NULL CHECK (entry_type IN ('credit','debit'))
amount             NUMERIC(20,4) NOT NULL CHECK (amount > 0)   -- always MXN, post-conversion
currency           CHAR(3) NOT NULL DEFAULT 'MXN'               -- always 'MXN' (matches amount)
original_amount    NUMERIC(20,4) NOT NULL                       -- what the caller actually requested
original_currency  CHAR(3) NOT NULL                              -- the caller's requested currency (may equal MXN)
fx_rate            NUMERIC(20,8) NOT NULL DEFAULT 1              -- MXN per 1 unit of original_currency; exactly 1 when original_currency='MXN'
balance_after      NUMERIC(20,4) NOT NULL          -- snapshot for audit/rebuild, MXN
idempotency_key    TEXT NOT NULL
transfer_id        UUID NULL                        -- links the two legs of a transfer
created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
UNIQUE (account_id, idempotency_key)             -- backs idempotency
```
Indexes: `ix_ledger_account_created (account_id, created_at)`; unique `uq_ledger_acct_idem (account_id, idempotency_key)`. Balance is derivable by `SUM(±amount)` (rebuild path, always in MXN) but served from the `accounts.balance` projection. `original_amount`/`original_currency`/`fx_rate` exist purely for audit — reconstructing "what did the customer actually send" from an MXN-only `amount` column would otherwise be impossible, which matters for an immutable financial ledger.

This is an additive schema change on top of the already-applied `3f8f816fa633` migration — a new Alembic revision, not an edit to the existing one (already-applied migrations must never be rewritten).

## Concurrency + Idempotency Protocol
Insert-first (let the unique constraint be the race arbiter), then lock:
```
BEGIN;
-- 1. lock aggregate
row = SELECT * FROM accounts WHERE id = :acct FOR UPDATE;   -- 404 UnknownAccount if none
-- 2. attempt append (idempotency arbiter)
try:
  INSERT INTO ledger_entries(..., idempotency_key, balance_after=<computed>);
except unique_violation(uq_ledger_acct_idem):
  ROLLBACK;                          -- replay: re-read existing entry, return 200 with same result
-- 3. domain rule: debit requires row.balance - amount >= 0 else ROLLBACK -> 409 InsufficientFunds
-- 4. UPDATE accounts SET balance = row.balance ± amount, version = version+1, updated_at=now() WHERE id=:acct;
COMMIT;
```
Ordering note: acquiring `FOR UPDATE` before the INSERT serializes concurrent mutations on the same account, so the idempotency check-then-insert cannot race across connections — a duplicate key either belongs to a committed prior request (replay) or to the holder of the lock. Transfer runs both legs in ONE transaction, locking the two account rows in a deterministic order (by `id` ascending) to avoid deadlock; both legs share one `transfer_id` and derive per-leg idempotency keys from the request `Idempotency-Key`.

## Dependency Injection (project convention — `dependency-injector`)
Use cases are classes, not functions, wired through a `dependency-injector` `containers.DeclarativeContainer` living at `adapters/config/container.py`, matching the existing house convention used across other Mattilda services (`SharedContainer`-style: `providers.Singleton` for stateful/shared things, `providers.Factory` for per-request objects, `<name>_provider` naming).

**Everything is injected — no ambient/global access, ever.** This includes the DB session and the logger. Concretely: repositories are NOT container-level `providers.Singleton`s (a singleton repo can't hold a per-request DB session/transaction). Instead, the container injects a `session_factory` (Singleton — an `async_sessionmaker`/equivalent) into the `UnitOfWork`, which is a `providers.Factory` (a fresh instance per use-case call, since each mutation needs its own transaction). The UoW's `__aenter__` creates the session from the factory and constructs the repos itself, passing `session` and `logger` into their `__init__` — classic Unit-of-Work-owns-Repositories. No `contextvar`, no `get_current_session()`, no module-level `logging.getLogger(__name__)` anywhere in this module.

```python
class AccountBalanceContainer(containers.DeclarativeContainer):
    logger_provider = providers.Factory(logging.getLogger)

    session_factory_provider: providers.Singleton[async_sessionmaker] = providers.Singleton(
        build_session_factory,  # wraps create_async_engine(...) + async_sessionmaker(...)
    )

    unit_of_work_provider = providers.Factory(
        SqlUnitOfWork,
        session_factory=session_factory_provider,
        logger=logger_provider,
    )

    credit_use_case_provider = providers.Factory(
        CreditAccountUseCase, uow=unit_of_work_provider,
    )
    debit_use_case_provider = providers.Factory(DebitAccountUseCase, uow=unit_of_work_provider)
    transfer_use_case_provider = providers.Factory(TransferUseCase, uow=unit_of_work_provider)


class SqlUnitOfWork:
    def __init__(self, session_factory: async_sessionmaker, logger: logging.Logger) -> None:
        self._session_factory = session_factory
        self._logger = logger

    async def __aenter__(self) -> "SqlUnitOfWork":
        self.session = self._session_factory()
        await self.session.begin()
        self.accounts = SqlAccountRepository(session=self.session, logger=self._logger)
        self.ledger = SqlLedgerRepository(session=self.session, logger=self._logger)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if exc_type is None:
            await self.session.commit()
        else:
            await self.session.rollback()
        await self.session.close()
```
Use cases receive only `uow` (Factory-provided) via constructor injection; inside `execute()` they do `async with self.uow as uow: await uow.accounts.get_for_update(...)`. Repos (`SqlAccountRepository`, `SqlLedgerRepository`) are plain classes taking `session` and `logger` as constructor params — built fresh by the UoW every transaction, never resolved from the container directly, never reaching for ambient state. FastAPI routes in `adapters/inbound/api/router.py` resolve use cases via `@inject` + `Provide[AccountBalanceContainer.credit_use_case_provider]` (wired in `src/main.py` app factory). Scope stays local to this module — no AWS/S3/SNS/SQS/Redis/JWT providers, since none of those are in v1 scope; only what account-balances actually needs (session factory, UoW, use cases).

## Currency Conversion (static table — no external API)
Balances are canonically in MXN (see Domain Model above). Requests may arrive in USD, CAD, COP, or CNY (or MXN itself); a simple hardcoded class converts to MXN before the amount is applied — no external HTTP call, no caching, no network-failure handling needed, by explicit user request to keep this simple.

```python
# application/services/exchange_rates.py
from decimal import Decimal

class UnsupportedCurrency(Exception):
    def __init__(self, currency: str) -> None:
        self.currency = currency
        super().__init__(f"Unsupported currency: {currency}")

class StaticExchangeRates:
    """MXN per 1 unit of currency. Hardcoded, manually maintained — not a
    live feed. Approximate rates as of Aug 2026; revisit periodically."""

    _RATES_TO_MXN: dict[str, Decimal] = {
        "MXN": Decimal("1"),
        "USD": Decimal("16.96"),
        "CAD": Decimal("12.22"),
        "COP": Decimal("0.00549"),
        "CNY": Decimal("2.52"),
    }

    def rate_to_mxn(self, currency: str) -> Decimal:
        try:
            return self._RATES_TO_MXN[currency.upper()]
        except KeyError:
            raise UnsupportedCurrency(currency) from None

    def to_mxn(self, amount: Decimal, currency: str) -> tuple[Decimal, Decimal]:
        """Returns (converted_amount, rate_used)."""
        rate = self.rate_to_mxn(currency)
        return amount * rate, rate
```
Wired into `AccountBalanceContainer` as `exchange_rates_provider = providers.Singleton(StaticExchangeRates)` (pure/stateless, safe as a singleton — unlike repos, it holds no per-request DB session) and injected into `CreditAccountUseCase`/`DebitAccountUseCase`/`TransferUseCase` alongside `uow`. Each use case calls `to_mxn(requested_amount, requested_currency)` once at the start of `execute()`, then proceeds exactly as before but with the MXN-converted amount — the domain (`Account.apply_credit`/`apply_debit`) is unchanged, it always operates in MXN and doesn't need to know conversion happened. The `(original_amount, original_currency, rate_used)` returned alongside the converted amount are threaded into the `LedgerEntry` for the new audit columns. `UnsupportedCurrency` maps to a 400 response in the API error handler, same shape as `InvalidAmount`/`UnknownAccount`.

`POST /v1/accounts` drops its `currency` parameter entirely (was accepted before, never enforced — same class of decorative-field problem this whole capability fixes) — every account is MXN by construction now, nothing to choose.

## API Surface (FastAPI, `adapters/inbound/api/router.py`)
All mutations require header `Idempotency-Key: <string>` (400 if missing). `currency` on credit/debit/transfer is now real and enforced (see "Currency Conversion" above) — it is the currency of the incoming request amount, converted to MXN before applying; it is NOT the account's own currency (every account is MXN, always).
- `POST /v1/accounts/{id}/credit` → body `{amount: Decimal>0, currency: "MXN"|"USD"|"CAD"|"COP"|"CNY"}` → 200 `{account_id, balance, entry_id}` (balance always MXN). 400 UnsupportedCurrency for anything else.
- `POST /v1/accounts/{id}/debit` → same body → 200 or 409 InsufficientFunds (funds check happens post-conversion, in MXN).
- `POST /v1/transfers` → body `{from_account_id, to_account_id, amount, currency}` → converted to MXN once, both legs apply the same MXN amount → 200 `{transfer_id, from_balance, to_balance}`.
- `GET /v1/accounts/{id}` → 200 `{id, balance, currency}` (`currency` always `"MXN"`).
- `POST /v1/accounts` → **dev/test convenience only, not a real onboarding flow** — body `{initial_balance: Decimal >= 0 = 0}` (no `currency` param — every account is MXN by construction, nothing to choose) → 201 `{id, balance, currency: "MXN"}`. Just inserts an `accounts` row (id server-generated) via a new `CreateDummyAccountUseCase` going through the same UoW/DI wiring as the other use cases. No KYC/customer linkage, no auth beyond the same `X-API-Key` v1 placeholder as every other route. Exists so `credit`/`debit`/`transfer` can be exercised without hand-seeding rows via `psql`.
Errors: 400 InvalidAmount (`amount<=0`/ missing key), 400 UnsupportedCurrency (currency not in the static table), 404 UnknownAccount, 409 InsufficientFunds, 200 idempotent replay (identical body → identical prior result). Error body `{error: {code, message}}`.

## Entrypoint, Local Dev, Deployment
- Entrypoint: replace `[tool.vercel] entrypoint=api.index:app` with `src.infrastructure.main:app`. Local: `uvicorn src.infrastructure.main:app --reload`. Container: `Dockerfile` (python:3.12-slim, `uv sync --frozen`, `CMD ["uvicorn","src.infrastructure.main:app","--host","0.0.0.0","--port","8000"]`).
- `docker-compose.yml`: service `postgres:16` (or `16-alpine`), port `5432:5432`, named volume `pgdata:/var/lib/postgresql/data`, env `POSTGRES_USER/PASSWORD/DB=accounts`. App connects via asyncpg URL `postgresql+asyncpg://...`; SQLAlchemy `create_async_engine(pool_size=10, pool_pre_ping=True)`, `AsyncSession(expire_on_commit=False)`.
- AWS (shape only, not provisioned): ECS/Fargate task def — one container (the image above), CPU/mem sizing, port 8000, health check `GET /health`, env from Secrets Manager (`DATABASE_URL`/creds), CloudWatch logs. Managed target RDS Postgres 16 — local Docker Postgres mirrors its version/params. Secrets Manager holds DB credentials injected as task-def secrets.

## Security
- AuthN/AuthZ v1: service-to-service bearer — static API key or signed JWT validated in `dependencies.py` (FastAPI dependency guarding all mutation routes). Deferred: per-customer OAuth, fine-grained scopes, rate limiting.
- DB roles: app role has `INSERT, SELECT` on `ledger_entries` (NO UPDATE/DELETE — enforces append-only at the DB); `INSERT, SELECT, UPDATE` on `accounts` (projection); no DDL. Migration/owner role separate.

## Dependency Management
Adopt `uv` + committed `uv.lock`. Remove `requirements.txt`, the `stripe` dependency, and the `[tool.vercel]` section from `pyproject.toml`. Add container/runtime deps only (no Mangum). Add dev group: `pytest`, `pytest-asyncio`, `httpx`, `alembic` (or raw SQL migrations).

## File Changes (summary)
Create: domain/application/adapter modules above, `src/infrastructure/main.py`, `src/config.py`, `src/infrastructure/db.py`, `docker-compose.yml`, `Dockerfile`, `.env.example`, migrations, `uv.lock`. Modify: `pyproject.toml` (entrypoint/deps cleanup). Delete: 4 scaffold folders' `.gitkeep`, `requirements.txt`.

## Testing Strategy
- Unit: domain invariants (debit>=0, amount>0), balance math, transfer leg derivation.
- Integration: real Postgres (docker) — idempotent replay returns identical result; concurrent debit race yields exactly one success; FOR UPDATE serialization; append-only enforced (UPDATE on ledger rejected).
- E2E: API happy paths + 400/404/409 contracts, missing Idempotency-Key.
Prerequisite risk (tasks/apply): no test runner/CI exists yet.

## Threat Matrix
N/A — no routing, shell, subprocess, VCS/PR automation, executable-file classification, or process-integration boundary. (In-process HTTP API + DB only.)

## Migration / Rollout
Greenfield module; initial schema via migration. No data migration. No feature flags in v1.

## Open Questions
- [x] JWT vs static API key for v1 service auth — resolved: static API key (all-zero UUID placeholder).
- [x] Migration tool: Alembic vs plain SQL files — resolved: Alembic.
- [x] Currency handling on transfer when accounts differ — resolved differently than originally framed: accounts no longer have their own currency at all (always MXN), so there's no "accounts differ" case for transfers. Incoming request currency is converted once via the static rate table (see "Currency Conversion").
