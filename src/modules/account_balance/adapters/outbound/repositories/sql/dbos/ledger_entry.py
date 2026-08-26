"""DBO (Database Object) for the `ledger_entries` table — immutable,
append-only.

Kept 1:1 with the hand-written migrations rather than the other way
around — this project doesn't autogenerate revisions from these DBOs.
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
from src.modules.account_balance.domain.ledger_entry import LedgerEntry


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
    currency: Mapped[str] = mapped_column(
        sa.CHAR(3), nullable=False, server_default="MXN"
    )
    # Audit columns: what the caller actually requested, before
    # conversion to the canonical MXN amount above. fx_rate defaults to
    # 1 (no conversion); original_amount/original_currency have no
    # DB-level default since they must always be supplied explicitly.
    original_amount: Mapped[Decimal] = mapped_column(sa.Numeric(20, 4), nullable=False)
    original_currency: Mapped[str] = mapped_column(sa.CHAR(3), nullable=False)
    fx_rate: Mapped[Decimal] = mapped_column(
        sa.Numeric(20, 8), nullable=False, server_default="1"
    )
    balance_after: Mapped[Decimal] = mapped_column(sa.Numeric(20, 4), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(sa.Text, nullable=False)
    transfer_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")
    )

    @classmethod
    def from_domain(cls, entry: LedgerEntry) -> "LedgerEntryRow":
        """Populate this DBO from a domain LedgerEntry."""
        return cls(
            id=entry.id,
            account_id=entry.account_id,
            entry_type=entry.entry_type.value,
            amount=entry.amount.amount,
            currency=entry.amount.currency,
            original_amount=entry.original_amount,
            original_currency=entry.original_currency,
            fx_rate=entry.fx_rate,
            balance_after=entry.balance_after,
            idempotency_key=entry.idempotency_key,
            transfer_id=entry.transfer_id,
        )
