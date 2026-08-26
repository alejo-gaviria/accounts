"""DBO (Database Object) for the `ledger_entries` table — immutable,
append-only. Mirrors the DDL in the initial migration
(migrations/versions/3f8f816fa633_create_accounts_and_ledger_entries.py
and design.md's "Domain Model + DB Schema").

Kept 1:1 with the hand-written migration rather than the other way
around — this project doesn't autogenerate revisions from these DBOs
(see migrations/env.py).
"""

import uuid
from datetime import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from src.modules.account_balance.adapters.outbound.repositories.sql.dbos.base import (
    Base,
)


class LedgerEntryRow(Base):
    __tablename__ = "ledger_entries"
    __table_args__ = (
        sa.CheckConstraint(
            "entry_type IN ('credit', 'debit')", name="ck_ledger_entry_type"
        ),
        sa.CheckConstraint("amount > 0", name="ck_ledger_amount_positive"),
        sa.UniqueConstraint(
            "account_id", "idempotency_key", name="uq_ledger_acct_idem"
        ),
        sa.Index("ix_ledger_account_created", "account_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("accounts.id"), nullable=False
    )
    entry_type: Mapped[str] = mapped_column(sa.Text, nullable=False)
    amount: Mapped[Decimal] = mapped_column(sa.Numeric(20, 4), nullable=False)
    currency: Mapped[str] = mapped_column(sa.CHAR(3), nullable=False)
    balance_after: Mapped[Decimal] = mapped_column(sa.Numeric(20, 4), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(sa.Text, nullable=False)
    transfer_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")
    )
