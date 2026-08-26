# AI Usage Log — account-balances

This service was built with Claude Code (Anthropic), using a Spec-Driven
Development (SDD) workflow: explore → propose → spec → design → tasks →
apply, with an orchestrating agent directing specialized sub-agents for
each phase. Every prompt below was a direct instruction ("do X", "use Y",
"reject this approach") rather than a request for the AI to decide the
approach on its own — architectural direction, trade-off decisions, and
scope calls were made by the human; the AI executed, proposed options
where a real trade-off existed, and pushed back with evidence when asked
to verify a claim.

This log lists every prompt given to the AI in this session, in order,
verbatim, together with a summary of what the AI did or decided in
response. Multi-choice questions the AI asked back (via a structured
question tool) are noted inline with the option the human picked.

---

## 1. Project initialization

**Prompt:**
> /sdd-init
> que pasó

**Response:** Ran the `sdd-init` skill against the `effex` project: detected
a git-less, greenfield FastAPI monorepo with one scaffolded hexagonal
module (`accounts/src/modules/account_balance`), no implementation, no
test tooling. Persisted the detected stack/context to Engram for reuse in
later phases.

---

## 2. Feature kickoff

**Prompt:**
> Usa /sdd-new
> Eres un ingeniero experto en arquitectura hexagonal y desarrollo en
> python. Debemos crear un nuevo servicio el cual será encargado de
> gestionar los saldos de las cuentas de los clientes; por tanto, es
> razonable asumir que se trata de un servicio crítico en el que deben
> implementarse diversas medidas y estrategias para garantizar un
> funcionamiento correcto. Al fin y al cabo, asegurar el dinero de los
> clientes es fundamental para la continuidad del negocio.
>
> instrucciones:
> - Es solo un microservicio que debe correr en la nube (llamado
>   account-balances)
> - Ten en cuenta que se trata de un servicio crítico en el ámbito
>   financiero; reflexiona sobre las acciones necesarias para garantizar
>   una concurrencia segura, la seguridad, la consistencia de los datos,
>   etc.
> - Quiero meter una base de datos postgres simulada con docker.
> - Debe ser un servicio cloud native, podemos hacerle deploy en vercel
> - La arquitectura a seguir está en el archivo Architecture.md en el
>   repo

**Response:** Started the SDD chain for change `account-balances`. Asked
two clarifying questions (execution mode, delivery strategy) — human
picked **Interactive** and **ask-on-risk**. Ran `sdd-explore`: read
`Architecture.md`, the scaffold, and the real dependency set
(FastAPI/SQLAlchemy-async/asyncpg/Pydantic v2), and surfaced open risks
before any decision was made — most importantly that Vercel's stateless
serverless model conflicts with a persistent async Postgres connection
pool, and that the scaffold's `vercel.json` entrypoint pointed at a
nonexistent module.

---

## 3. Deploy target and datastore correction

**Prompt (as answers to the exploration findings):**
> 1. No lo hagamos en postgres, que haga deploy en aws, no lo va a hacer
>    pero que sea un fastapi que se pueda correr local
> 2. hay que hacerlo
> 3. hagamoslo a aws
> 4. 5. No uses stripe, se quedó ahi de un pyproject que tenía
>
> Sigamos con la propuesta

**Response:** The first line was ambiguous (could have meant "drop
Postgres" or "drop Vercel"), so the AI asked a clarifying question instead
of guessing — human confirmed **Postgres stays**, only the deploy target
changes (AWS, not Vercel; no actual deployment executed, service must run
locally). Then asked three more targeted business questions (ownership
model, idempotency requirement, audit/ledger requirement) before writing
the proposal — human answered **own API as source of truth**,
**idempotency mandatory**, **immutable ledger required**. `sdd-propose`
then produced the proposal: ECS/Fargate over Lambda (avoids reintroducing
the same connection-pool problem that ruled out Vercel), pessimistic
row-locking, `Idempotency-Key` + unique constraint, append-only ledger
with a cached balance projection, `uv` as package manager, `stripe`
dependency removed.

---

## 4. Spec and design

**Prompt:**
> ya quedó el repo, sigue con la fase de sdd-spec y design

**Response:** Verified the claim before acting on it (`git status` at the
project root showed no repo — found the real one at `accounts/.git`
instead) and proceeded on that basis. Ran `sdd-spec` and `sdd-design` in
parallel: formal requirements/scenarios for the ledger, mutation API,
idempotency, and concurrency-safety domains; and a concrete technical
design (DB schema, `SELECT ... FOR UPDATE` transaction protocol,
deterministic ascending-ID lock ordering for transfers to avoid deadlock,
FastAPI route contracts, Dockerfile/docker-compose shape).

---

## 5. Auth and migrations decisions

**Prompt:**
> auth pongamosle un api-key que sea uuid de puro ceros, migraciones con
> alembic

**Response:** Folded both decisions into the tasks breakdown: a static
all-zero-UUID API key explicitly documented as a v1/local-only
placeholder (not silently left as an undocumented TODO), and Alembic for
migrations. `sdd-tasks` produced 37 tasks across 8 phases; the review
forecast flagged ~900–1300 changed lines (over the review budget), so the
AI stopped and asked how to deliver it — human chose **one PR, with an
accepted size exception** rather than splitting into chained PRs.

---

## 6. Implementation

`sdd-apply` implemented all 37 tasks: tooling/infra, schema + migration,
domain layer, application layer, SQL adapters, inbound API, wiring, docs —
on a `feat/account-balances` branch, one commit per work phase. No
additional human prompt was needed for this pass; the AI proceeded
autonomously within the scope already agreed. It correctly stopped and
reported when it hit a genuine blocker (see next section) rather than
guessing.

---

## 7. Infrastructure blocker: Engram artifact truncation

Mid-implementation, `sdd-apply` reported that the stored spec/design/tasks
artifacts were being silently truncated on read by the memory backend,
and refused to guess at the missing schema/API details rather than
risk building on invented information. The AI diagnosed the truncation as
a tool-level bug (confirmed independently, not just trusting the
sub-agent's claim), then had the phase agents that still held the full
content in their own context write it verbatim to files on disk instead —
unblocking the implementation without regenerating any work. This was an
autonomous recovery, not something the human needed to intervene in.

---

## 8. Dependency injection correction

**Prompt (pasted a real `SharedContainer` example from another internal
service, then):**
> No me gusta que el caso de uso sea metodos, deberían ser clases con sus
> inyecciones de depencencias con dependency-injectors, esto en el
> adapters/config

**Response:** Rejected the function-based use cases the first `sdd-apply`
pass had produced. Converted `CreditAccountUseCase` / `DebitAccountUseCase`
/ `TransferUseCase` into classes wired through a new
`AccountBalanceContainer` (`dependency-injector`), matching the pasted
house convention.

---

## 9. Rejecting an ambient-state workaround

**Prompt (pasted code showing a `get_current_session()` call inside a
repository, then):**
> Por qué no inyectas la sesion desde el contenedor, eso y el logger,
> todo debe ser por inyección

**Response:** Agreed this was a real anti-pattern — the prior pass had
made repositories container-level singletons, which can't hold a
per-request DB session, and had worked around that with a `contextvar`
(disguised global state). Reverted to the correct fix: the
`UnitOfWork` (not the repositories) is the container-injected object; it
owns `session_factory` and `logger` via its constructor and builds
fresh, explicitly-constructed repositories inside its own
`__aenter__`, once per transaction. No contextvar, no ambient lookups
anywhere.

---

## 10. Naming convention correction

**Prompt:**
> No me gustó los models de la db, deberían ser en la carpeta dbos, no

**Response:** Moved the flat `models.py` into a `dbos/` package, split
one file per entity (`account.py`, `ledger_entry.py`, `base.py`),
matching the existing per-entity convention already used for
repositories.

---

## 11. First local run + real bugs found

**Prompt:**
> Como lo corro local

**Response:** Gave the local-dev recipe, then actually ran it end-to-end
(not just described it) — which surfaced a real bug: a system-level
Postgres already listening on port 5432 was silently intercepting the
Docker container's connections, causing a role-not-found error at
migration time. Diagnosed the port collision, remapped the dev Postgres
service to 5442, and re-verified: migration applies cleanly, DB-level
grants match the design exactly (append-only enforced by revoked
UPDATE/DELETE), and — critically — the one integration test that failed
on the first real run against live Postgres turned out to be a test-harness
bug (reusing an `asyncpg` connection after `asyncio.wait_for` had
abandoned an in-flight query on it), not an application bug. Fixed the
test, not the application code, after isolating the root cause with a
standalone reproduction script.

---

## 12. Testing without an account-creation endpoint

**Prompt:**
> actualmente los endpoints solo te dejan crear un credito, debito o
> transfer, como hago para probar

**Response:** Explained that v1 deliberately has no account-provisioning
endpoint (out of scope), and how to seed a row directly via `psql` in the
meantime, then ran a full credit → replay → debit → insufficient-funds →
transfer flow live against the running app and Postgres to prove it end
to end.

---

## 13. Dev convenience endpoint

**Prompt:**
> hazme un endpoint para crear dummies

**Response:** Added `POST /v1/accounts`, explicitly documented as a
dev/test convenience (no KYC, no customer linkage — not a real
onboarding flow) so `credit`/`debit`/`transfer` can be exercised without
hand-seeding rows.

---

## 14. Currency validation gap identified and closed

**Prompt:**
> el currency no sirve no? Solo es USD

**Response:** Verified the claim in the actual code before answering (per
standing instruction to never agree with a claim without checking) —
confirmed `currency` was stored but never validated anywhere: credit/debit
did raw numeric math regardless of currency, and transfer never checked
the two accounts' currencies matched despite the design doc's own stated
intent to reject a mismatch. Asked whether to fix it now or defer it.

**Follow-up prompt (chose "Other" on the multiple-choice question):**
> Hay algun api para saber el tipo de cambio? Y que todo esté en MX y se
> haga el cambio

**Response:** This reopened an explicit non-goal ("single-currency MVP")
from the original proposal, so the AI treated it as a real scope decision
rather than a quick fix — asked which FX source and confirmed the
conversion model. Human picked **Banco de México's official SIE API**,
and confirmed **every balance is canonically MXN, converted on write**.
The AI researched Banxico's actual API (base URL, real series IDs for
USD/EUR/GBP/JPY/CAD, token auth) via web search before designing against
it, rather than guessing at an API shape.

**Follow-up prompt (mid-turn correction, before implementation started):**
> hagamoslo mas sencillo, una clase sencilla con tipos de cambio de dolar
> canadiense, mexico, peso colombiano, dolar y moneda china

**Response:** Simplified the design from a live external API integration
down to a hardcoded `StaticExchangeRates` class covering MXN, USD, CAD,
COP, CNY (with real approximate August 2026 rates looked up rather than
invented). Updated spec/design docs to match before implementing —
`ledger_entries` gained `original_amount`/`original_currency`/`fx_rate`
audit columns, `POST /v1/accounts` dropped its now-meaningless `currency`
parameter (same decorative-field problem this fix was for), and every
mutation converts to MXN once before touching the domain layer. Verified
live: crediting 10 USD to an account correctly landed a balance of
169.60 MXN, and an unsupported currency was correctly rejected with 400.

---

## 15. Infrastructure folder convention

**Prompt (mid-turn, while the AI was investigating an unrelated
uncommitted diff it found in the working tree):**
> dejalos, eso debe ir en infrastructure

**Response:** Confirmed and kept a manual `src/main.py` →
`src/infrastructure/main.py` (and `db.py`) move the human had made
directly in the working tree, fixed the resulting stale
`src.main:app` references in the Dockerfile/README, and committed it as
an established convention for future service-root infrastructure files.

---

## 16. Repository construction convention

**Prompt (pasted a code diff showing `AccountRow.from_domain(account)`,
then):**
> Hice unos cambios, me gusta que los dbos vengan de un from domain, ya
> quedó para account repo, puedes ajustar?

**Response:** Confirmed the pattern was already correctly applied to
`AccountRow`, and extended the same `from_domain` classmethod convention
to `LedgerEntryRow`/`ledger_repo.py` for consistency.

---

## 17. Comment cleanup, pass 1

**Prompt:**
> quita todos los comentarios hechos por ia, quiero que quede limpio el
> código solo con la documentación necesaria

**Response:** Stripped narration-style comments (task/spec citations,
"the coordinator said" framing, restating-the-obvious comments) across
every file touched this session, keeping short docstrings and comments
that capture a genuinely non-obvious invariant (e.g. the deadlock-avoidance
lock ordering, the asyncpg cancellation gotcha). Verified the diff was
comment-only and the suite was unaffected (67/67 before and after).

---

## 18. Comment cleanup, pass 2 (stricter)

**Prompt:**
> quiero que quites TODOS los comentarios, string docs. agrega unos muy
> muy cortos que describan el proceso

**Response:** Went further: deleted essentially all docstrings and
multi-line comments, keeping only single-line survivors for the handful
of facts that are genuinely load-bearing for a future reader. This pass
was interrupted partway by a session/API limit; the AI verified the
partially-completed work was safe (pure deletions, tests still 67/67),
committed it as an explicit work-in-progress checkpoint rather than
leaving it uncommitted or silently dropping it, and flagged exactly which
files still need the same treatment.
