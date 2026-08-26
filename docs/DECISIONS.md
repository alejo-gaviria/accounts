# Design Rationale — account-balances

This document explains *why* the service is built the way it is: the
architecture, the technology choices, and — most importantly for a
money-holding service — the strategies used for concurrency safety, data
consistency, and idempotency, along with the trade-offs considered at
each decision point.

## 1. What kind of system this is, and why that dictates everything else

`account-balances` owns customer account balances. A wrong balance isn't
a cosmetic bug — it's either money the business loses or money a customer
is wrongly denied. That single fact drove every non-obvious choice below:
correctness and auditability were prioritized over raw throughput,
implementation speed, or infrastructure minimalism, everywhere those
came into tension.

## 2. Architecture: hexagonal, with a real dependency-injection boundary

**Choice:** Ports-and-adapters (hexagonal) layering — `domain/` (pure,
no I/O), `application/` (use cases orchestrating ports), `adapters/`
(inbound HTTP, outbound SQL) — with every dependency wired through a
`dependency-injector` `DeclarativeContainer`, not constructed ad hoc.

**Why:**
- The domain layer (`Account`, `LedgerEntry`, the balance/insufficient-funds
  invariants) has zero knowledge of Postgres, FastAPI, or SQLAlchemy. It
  can be unit-tested with no infrastructure at all, which matters for a
  service where the *business rule* (never let a balance go negative,
  never lose a ledger entry) is the thing that must never regress.
- Every dependency — the DB session, the logger, the exchange-rate
  service — is passed in explicitly through a constructor, never fetched
  from a global, a module-level singleton, or a `contextvar`. This was
  not a stylistic preference; it was corrected mid-build after an
  intermediate version used a `contextvar` to give repositories access to
  "the current" DB session. That pattern is a disguised global: it makes
  the true dependency graph invisible, and — concretely — it made it
  impossible to reason confidently about which transaction a repository
  call was actually running against. The fix was to make the
  `UnitOfWork` (not the repositories) the container-managed object: it
  owns a `session_factory` and constructs fresh, explicitly-scoped
  repositories inside its own `__aenter__`, once per transaction. Every
  repository's session is a constructor argument, always.

**Trade-off considered:** A simpler, function-based application layer
(use cases as plain async functions taking a session parameter) would
have been less code and faster to write. It was rejected in favor of
class-based use cases with constructor injection because it matches an
established convention across other services in this organization, and
because constructor injection makes unit tests trivial — a use case can
be instantiated directly with fake repositories, no container, no
monkeypatching.

## 3. Datastore: PostgreSQL, not a NoSQL or eventually-consistent store

**Choice:** PostgreSQL, accessed via SQLAlchemy's async engine (`asyncpg`
driver), with row-level locking as the concurrency primitive.

**Why:** A balance is a value with a strict invariant (never negative)
that must be enforced under concurrent writes, and every mutation must
be auditable after the fact. Postgres gives three things for free that
would otherwise have to be built by hand: `SELECT ... FOR UPDATE` row
locking (see §5), real ACID transactions spanning the ledger insert and
the balance update together (see §6), and DB-level grant enforcement
that can make the ledger *physically* append-only, not just
append-only-by-convention in application code (see §4).

**Trade-off considered:** A NoSQL store (DynamoDB, which the original
scaffold even had a placeholder folder for) would have scaled writes
more easily horizontally, but conditional/transactional multi-item
writes and row-level locking are far more awkward to get right there,
and for this service's access pattern (single-account and two-account
transactions, not massive fan-out) Postgres's transactional guarantees
were judged more valuable than DynamoDB's horizontal scalability. The
unused `dynamo/`/`redis/` scaffold folders were deliberately pruned
rather than left as speculative dead code.

## 4. The ledger: append-only, balance as a derived projection

**Choice:** Every balance change is recorded as an immutable row in
`ledger_entries`. The `accounts.balance` column is a *cached projection*
over that ledger, not an independently-mutable source of truth. The
database role the application connects as has `INSERT`/`SELECT` only on
`ledger_entries` — no `UPDATE`, no `DELETE` — enforced by Postgres grants,
not just by "the code doesn't do that."

**Why:** This is standard practice in financial systems for a concrete
reason: if the balance were the only stored fact, a bug (or an
unauthorized actor) could silently corrue history — there would be no way
to prove after the fact what happened. With an append-only ledger, the
balance can always be rebuilt from scratch by summing entries, and every
past state is reconstructable. Enforcing "no UPDATE/DELETE" at the
database grant level, not just in application code, matters because it
means even a bug in the application, or a compromised app-role
credential, physically cannot rewrite history — Postgres itself refuses
the statement.

**Trade-off considered:** Storing only the current balance would be
simpler and would need no reconciliation logic. It was rejected outright,
not weighed as a close call — for a "critical financial service" (the
explicit framing of this project from the start), losing the ability to
answer "how did this balance get here" is not an acceptable trade for
simplicity.

## 5. Concurrency: pessimistic row locking, not optimistic

**Choice:** Every mutation acquires `SELECT ... FOR UPDATE` on the target
account row before reading its balance, and holds that lock for the
duration of the transaction (read balance → validate → insert ledger
entry → update projection → commit).

**Why — and why not optimistic concurrency:** Optimistic concurrency
(read a version number, write with `WHERE version = X`, retry on
conflict) is usually the higher-throughput choice, because it doesn't
block readers/writers against each other under low contention. It was
considered and rejected for this specific access pattern: mutations
against the *same account* are inherently sequential from a business
standpoint — you cannot correctly credit and debit the same account
"in parallel" and reconcile afterward, the second operation's correctness
literally depends on the first one's result. Given that, optimistic
concurrency would only add retry-storm risk on hot accounts (many
competing writers all failing their compare-and-swap and retrying)
without buying any real parallelism, since the work was serial anyway.
Pessimistic locking makes that existing serialization explicit and lets
Postgres arbitrate it directly, with no retry loop in application code.

**Deadlock avoidance in transfers:** A transfer touches two account rows.
Two concurrent transfers moving money in opposite directions between the
same two accounts (A→B and B→A at the same time) would deadlock if each
transaction locked "source, then destination" in request order — each
would hold one lock and wait forever on the other. The fix is a
deterministic lock order: both legs of any transfer lock the two account
rows in ascending ID order, regardless of which one is the source. This
guarantees every transaction attempts to acquire the same two locks in
the same order, so one always wins and the other simply waits its turn
— no deadlock is possible, and no deadlock-detection/retry logic is
needed.

## 6. Atomicity: ledger insert and balance update, one transaction

**Choice:** The ledger row insert and the balance projection update
happen inside the exact same database transaction, which commits or
rolls back as one unit.

**Why:** If these were two separate transactions, a crash between them
would leave either an orphaned ledger entry with no matching balance
change, or a balance change with no audit trail explaining it — both are
silent corruption for a financial ledger. A single transaction makes
that failure mode structurally impossible: Postgres guarantees both
writes land together or neither does.

## 7. Idempotency: mandatory, and checked before mutation

**Choice:** Every mutating request must include a client-supplied
`Idempotency-Key`. It is persisted with a unique constraint on
`(account_id, idempotency_key)`. A duplicate request (same key, same
account) returns the original result instead of re-applying the
operation.

**Why:** Network calls fail and get retried — a client that times out
waiting for a credit response has no way to know whether the credit
actually landed, and *will* retry. Without idempotency, a retried credit
becomes a double credit; a retried debit becomes a double debit. For a
balance-holding service, this is not an edge case worth deferring, it is
one of the most common real failure modes in production financial
systems.

**Where the check happens, and why that changed during the build:** The
first implementation followed the more common "insert-first" pattern —
attempt to insert the ledger row, let the unique constraint reject a
duplicate, and treat that rejection as "this was a replay." That was
corrected to a "check-first" pattern instead: look up an existing entry
for that idempotency key *before* mutating the in-memory account
aggregate at all. The reason was a concrete bug the check-first version
fixes: under insert-first, a replayed request would still run the
domain mutation (`account.apply_credit(...)`) against the in-memory
object before discovering it was a duplicate, which is wasted work at
best and a source of subtle bugs at worst if that mutated object were
ever reused. Check-first avoids mutating anything for a request that
turns out to be a pure replay. This is race-safe specifically *because*
the row lock (§5) is acquired before the idempotency check — two
concurrent requests with the same key cannot race past the check
simultaneously, since only one can hold the row lock at a time. The
unique constraint remains as a second line of defense in case that
reasoning is ever wrong.

## 8. Deployment target: reconsidered from Vercel to ECS/Fargate

**Choice:** The service is structured to be AWS-deployable (containerized,
via ECS/Fargate against a managed RDS Postgres instance), though no
actual cloud deployment was executed as part of this build — it runs
locally via Docker Compose.

**Why the change from the original ask (Vercel):** Vercel's serverless
Python functions are effectively stateless per invocation — there is no
guarantee of a warm, reusable process between requests, which conflicts
directly with SQLAlchemy's async engine wanting a long-lived connection
pool. Running this service on Vercel would mean either fighting that
model with an external connection pooler, or accepting connection-storm
risk against Postgres under load. A long-running container target
(ECS/Fargate) sidesteps the problem entirely: one warm process, one real
connection pool, no per-invocation cold-start tax. AWS Lambda was also
considered and rejected for the same underlying reason — it reintroduces
the identical stateless-execution problem that ruled out Vercel, and
would need the same kind of external pooler (e.g. RDS Proxy) to be safe.

## 9. Currency handling: static conversion table, MXN canonical

**Choice:** Every account balance is canonically denominated in MXN.
Mutation requests may specify MXN, USD, CAD, COP, or CNY; the amount is
converted to MXN via a small hardcoded rate table before being applied.
The ledger records the original amount, original currency, and the exact
rate used, in addition to the MXN amount actually applied — so "what did
the customer actually send" is never lost even though the stored balance
is MXN-only.

**Why this exists at all:** The initial build stored a `currency` field
on both accounts and ledger entries but never validated or acted on it —
a credit request in any currency string was simply added to the balance
as a raw number. That is a real correctness gap for a service branded as
financial-critical, not a cosmetic one: it would silently mix currencies
in the same balance. Fixing it was prioritized once identified, rather
than deferred.

**Trade-off considered — live FX API vs. static table:** A real-time
lookup against Banco de México's official exchange-rate API was
investigated first (the real API shape — base URL, per-currency series
IDs, token authentication — was confirmed before any design work went
into it). It was deliberately not built: a live external dependency adds
a failure mode (what happens to a credit request if the rate API is
down?) and operational complexity (caching, staleness policy) that
wasn't judged worth it for the actual requirement, once simplified to a
small, fixed currency set. The static table is simpler, has zero
external failure modes, and is trivially auditable — but it is
explicitly *not* a live feed and needs manual updates to stay accurate;
that trade-off is intentional and documented in-code, not accidental.

## 10. Security posture, and what's deliberately deferred

**Choice:** v1 authentication is a single static API key (a placeholder
value), checked against every mutating and read route. The database role
the application uses has the narrowest grants that satisfy the
append-only ledger requirement (§4) and nothing more.

**Why a placeholder, explicitly:** Building real service-to-service auth
(JWT issuance, rotation, per-client scoping) was judged out of scope for
proving out the core financial-correctness guarantees (locking,
idempotency, atomicity, auditability) that are the actual hard problem
here. Rather than silently shipping something that looks production-ready
but isn't, the placeholder is loudly documented — in code, in the
README, and here — as something that must be replaced before any real
deployment. A financial service papering over a known gap is worse than
one that names it clearly.

## 11. What was explicitly left out, and why

- **Event publication to other services** (dual-write from this
  service's own DB transaction to a message bus) was deferred. Doing it
  correctly requires an outbox pattern or CDC, which is real additional
  infrastructure; nothing in the current scope has a consumer waiting for
  those events, so building it now would be speculative.
- **Account onboarding / KYC** was never in scope — `POST /v1/accounts`
  exists purely as a development/testing convenience and is documented
  as such, not as a real customer-facing flow.
- **Multi-currency beyond the five supported codes** and **live FX
  rates** were both explicitly scoped out (§9) in favor of the simpler,
  fully-understood static table.
- **Real AWS provisioning** was not executed — the service is structured
  to deploy to ECS/Fargate, but no infrastructure was actually stood up,
  since that was outside what this exercise needed to prove.

Each of these was a conscious scope boundary, not an oversight — the
guiding principle throughout was to get the parts that are hard to fix
later (data model, concurrency, auditability, idempotency) right first,
and to defer anything that's comparatively cheap to add on top later.
