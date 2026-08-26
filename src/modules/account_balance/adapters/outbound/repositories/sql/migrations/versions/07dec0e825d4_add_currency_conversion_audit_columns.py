"""add currency conversion audit columns

Revision ID: 07dec0e825d4
Revises: 3f8f816fa633
Create Date: 2026-08-26 15:58:08.631804

Additive schema change for the "Currency Conversion" capability
(design.md) — does NOT edit the already-applied 3f8f816fa633 migration.
Every account balance is now canonically MXN; ledger_entries.amount
stays MXN (post-conversion) and gains three audit-only columns
recording what the caller actually requested before conversion.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '07dec0e825d4'
down_revision: Union[str, Sequence[str], None] = '3f8f816fa633'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add the two audit columns nullable first, backfill, then tighten
    # to NOT NULL — this table may already have rows (dev/test data;
    # this is a greenfield module with no production data) and a plain
    # ADD COLUMN ... NOT NULL with no default fails against a non-empty
    # table.
    op.add_column(
        "ledger_entries",
        sa.Column("original_amount", sa.Numeric(20, 4), nullable=True),
    )
    op.add_column(
        "ledger_entries",
        sa.Column("original_currency", sa.CHAR(3), nullable=True),
    )
    op.add_column(
        "ledger_entries",
        sa.Column(
            "fx_rate", sa.Numeric(20, 8), nullable=False, server_default="1"
        ),
    )

    # Backfill: every row that existed before this migration was
    # created before conversion existed at all, so by definition no
    # conversion happened for it — original_amount/original_currency
    # equal the existing amount/currency, fx_rate is already defaulted
    # to 1 above.
    op.execute(
        "UPDATE ledger_entries "
        "SET original_amount = amount, original_currency = currency "
        "WHERE original_amount IS NULL"
    )

    op.alter_column("ledger_entries", "original_amount", nullable=False)
    op.alter_column("ledger_entries", "original_currency", nullable=False)

    # Canonical currency is now MXN, not USD.
    op.alter_column("accounts", "currency", server_default="MXN")
    op.alter_column("ledger_entries", "currency", server_default="MXN")


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column("ledger_entries", "currency", server_default=None)
    op.alter_column("accounts", "currency", server_default="USD")

    op.drop_column("ledger_entries", "fx_rate")
    op.drop_column("ledger_entries", "original_currency")
    op.drop_column("ledger_entries", "original_amount")
