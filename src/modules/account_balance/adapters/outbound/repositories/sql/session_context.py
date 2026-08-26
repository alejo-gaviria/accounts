"""Ambient-session propagation for the SQL repository singletons.

The DI convention (design.md "Dependency Injection") wires
SqlAccountRepository/SqlLedgerRepository as `providers.Singleton` — one
shared, stateless instance for the process lifetime. But every mutation
needs the account lock and the ledger insert to happen on the exact
same DB transaction/session as the SqlUnitOfWork that opened it (spec:
atomic ledger+balance update, FOR UPDATE serialization).

A contextvar bridges that: SqlUnitOfWork.__aenter__ sets the session
that's "active" for the current asyncio task; the repository singletons
read it back via get_current_session(). asyncio Tasks (one per FastAPI
request) each get their own copy of the contextvar context, so this is
request-isolated despite the repos being shared singletons.
"""

import contextvars

from sqlalchemy.ext.asyncio import AsyncSession

_current_session: contextvars.ContextVar[AsyncSession | None] = contextvars.ContextVar(
    "account_balance_current_session", default=None
)


class NoActiveSession(RuntimeError):
    def __init__(self) -> None:
        super().__init__(
            "No active DB session for this task - repository methods must "
            "be called inside `async with unit_of_work:`"
        )


def get_current_session() -> AsyncSession:
    session = _current_session.get()
    if session is None:
        raise NoActiveSession
    return session


def set_current_session(session: AsyncSession) -> contextvars.Token:
    return _current_session.set(session)


def reset_current_session(token: contextvars.Token) -> None:
    _current_session.reset(token)
