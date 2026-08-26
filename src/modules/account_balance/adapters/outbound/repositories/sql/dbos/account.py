"""DBO (Database Object) for the `accounts` table — the aggregate +
balance projection row.

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
from src.modules.account_balance.domain.account import Account


class AccountRow(Base):
    __tablename__ = "accounts"
    __table_args__ = (
        sa.CheckConstraint("balance >= 0", name="ck_accounts_balance_non_negative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    currency: Mapped[str] = mapped_column(
        sa.CHAR(3), nullable=False, server_default="MXN"
    )
    balance: Mapped[Decimal] = mapped_column(
        sa.Numeric(20, 4), nullable=False, server_default="0"
    )
    version: Mapped[int] = mapped_column(
        sa.BigInteger, nullable=False, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")
    )

    @classmethod
    def from_domain(cls, account: Account) -> "AccountRow":
        """Populate this DBO from a domain Account aggregate."""
        return cls(
            id=account.id,
            currency=account.currency,
            balance=account.balance,
            version=account.version,
        )
