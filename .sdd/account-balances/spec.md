# Spec: account-balances

New greenfield specs (no prior behavior). Four capability domains per proposal.

## Domain: account-balance-ledger

### Requirement: Append-Only Ledger

The system MUST record every balance mutation as an immutable `ledger_entries` row. The database role used by the application MUST NOT hold UPDATE or DELETE grants on `ledger_entries`.

#### Scenario: Mutation creates ledger entry
- GIVEN a valid credit/debit/transfer request
- WHEN the mutation is applied
- THEN a new `ledger_entries` row is inserted recording account, amount, direction, and idempotency key

#### Scenario: Ledger row cannot be altered
- GIVEN an existing ledger entry
- WHEN the app's DB role attempts UPDATE or DELETE on `ledger_entries`
- THEN the database rejects the statement due to missing grants

### Requirement: Balance as Ledger Projection

Current balance MUST be derived as a projection over ledger entries, not an independently mutated value.

#### Scenario: Balance reflects ledger sum
- GIVEN an account with prior ledger entries
- WHEN the balance is queried
- THEN it equals the sum of all ledger entries for that account

## Domain: balance-mutation-api

### Requirement: Credit, Debit, Transfer Endpoints

The service MUST expose its own inbound HTTP endpoints for credit, debit, and transfer as the source of truth (no writes via another service).

#### Scenario: Successful credit
- GIVEN a known account
- WHEN a credit request with positive amount is submitted
- THEN the balance increases by the amount and a ledger entry is created

#### Scenario: Successful transfer
- GIVEN two known accounts with sufficient source balance
- WHEN a transfer request is submitted
- THEN source debits and destination credits atomically with two linked ledger entries

### Requirement: Mutation Validation

The system MUST reject invalid mutation requests before persisting any ledger entry.

#### Scenario: Zero or negative amount rejected
- GIVEN a mutation request with amount <= 0
- WHEN submitted
- THEN the request is rejected with no ledger entry created

#### Scenario: Insufficient funds on debit/transfer
- GIVEN an account balance lower than the requested debit/transfer amount
- WHEN the mutation is submitted
- THEN it is rejected with an insufficient-funds error and no state change

#### Scenario: Unknown account
- GIVEN an account ID that does not exist
- WHEN a mutation targets it
- THEN the request is rejected with a not-found error and no ledger entry created

## Domain: idempotency

### Requirement: Idempotency-Key Enforcement

Every mutation request MUST include an `Idempotency-Key`, persisted with a unique constraint and checked within the mutation transaction.

#### Scenario: Duplicate request returns original result
- GIVEN a mutation already applied under key K
- WHEN a new request with the same key K and same account arrives
- THEN no new ledger entry is created and the original result is returned

#### Scenario: Missing or malformed key rejected
- GIVEN a mutation request without a valid `Idempotency-Key` header
- WHEN submitted
- THEN the request is rejected before any persistence occurs

## Domain: concurrency-safety

### Requirement: Pessimistic Row Locking

Concurrent mutation requests against the same account MUST serialize via `SELECT ... FOR UPDATE` on the account aggregate row.

#### Scenario: Concurrent mutations serialize correctly
- GIVEN two concurrent mutation requests on the same account
- WHEN both execute
- THEN they apply sequentially with no lost update and the final balance reflects both

#### Scenario: Concurrent duplicate-key retries do not double-apply
- GIVEN two concurrent requests with the same Idempotency-Key racing under lock
- WHEN both execute
- THEN only one ledger entry is created and both callers receive the same result

### Requirement: Atomic Ledger and Balance Update

Ledger entry insertion and balance projection update MUST occur in one database transaction.

#### Scenario: Partial failure rolls back fully
- GIVEN a mutation transaction that fails after the ledger insert but before the balance update commits
- WHEN the failure occurs
- THEN the transaction rolls back entirely — no orphaned ledger entry, no stale balance

## Domain: currency-conversion

**Supersedes the original "single-currency MVP" non-goal below** — the user
explicitly reopened this after noting `currency` was stored but never
validated or acted on. Every account balance is now canonically denominated
in MXN. Requests may arrive in a supported foreign currency; they are
converted to MXN using a simple static, hardcoded exchange-rate table (no
external API call) before being applied.

### Requirement: MXN as Canonical Balance Currency

Every account balance MUST be denominated and stored in MXN. Account
creation MUST NOT accept a currency parameter (removed — it was a
decorative field with no enforcement, same class of problem as the
mutation-currency gap this domain fixes).

#### Scenario: Non-MXN credit is converted before applying
- GIVEN a known account with an MXN balance
- WHEN a credit request arrives with `currency: "USD"` and a positive amount
- THEN the amount is converted to MXN at the current Banxico rate before the ledger entry is created and the balance is updated
- AND the ledger entry records the original amount, original currency, and the exact rate used

#### Scenario: MXN request applies with no conversion
- GIVEN a known account
- WHEN a credit/debit/transfer request arrives with `currency: "MXN"`
- THEN no external rate lookup occurs and the amount is applied as-is

#### Scenario: Transfer between MXN balances never needs conversion
- GIVEN two known accounts (both MXN-denominated, as all accounts are)
- WHEN a transfer request is submitted with a non-MXN `currency`
- THEN the amount is converted to MXN once and both legs apply the same converted MXN amount — no per-leg re-conversion, no mismatch possible (since both accounts share the same canonical currency)

### Requirement: Only Currencies In The Static Table Are Accepted

The system MUST reject a mutation request whose `currency` has no entry in the static exchange-rate table (v1 supported set: MXN, USD, CAD, COP, CNY), rather than silently guessing or defaulting a rate.

#### Scenario: Unsupported currency rejected
- GIVEN a mutation request with `currency: "EUR"` (or any code outside the v1 supported set)
- WHEN submitted
- THEN the request is rejected with an unsupported-currency error and no ledger entry created

## Non-Goals (out of scope for this spec)
- No event publication or dual-write to other services in v1.
- ~~No multi-currency logic (single-currency MVP; `currency` column reserved structurally only).~~ Superseded — see "currency-conversion" domain above.
- No AWS deployment execution — structure only.
- No support for currencies outside the v1 static-table set (MXN, USD, CAD, COP, CNY) — adding one is a one-line change to the static table, not automatic for v1.
- No live/external exchange-rate source — rates are a hardcoded static table, manually updated, not fetched from any API. No historical/point-in-time rate lookups either.
