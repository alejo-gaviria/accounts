"""add currency conversion audit columns"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "07dec0e825d4"
down_revision: Union[str, Sequence[str], None] = "3f8f816fa633"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # nullable first: table may already have rows
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
        sa.Column("fx_rate", sa.Numeric(20, 8), nullable=False, server_default="1"),
    )

    # backfill: pre-existing rows had no conversion
    op.execute(
        "UPDATE ledger_entries "
        "SET original_amount = amount, original_currency = currency "
        "WHERE original_amount IS NULL"
    )

    op.alter_column("ledger_entries", "original_amount", nullable=False)
    op.alter_column("ledger_entries", "original_currency", nullable=False)

    op.alter_column("accounts", "currency", server_default="MXN")
    op.alter_column("ledger_entries", "currency", server_default="MXN")


def downgrade() -> None:
    op.alter_column("ledger_entries", "currency", server_default=None)
    op.alter_column("accounts", "currency", server_default="USD")

    op.drop_column("ledger_entries", "fx_rate")
    op.drop_column("ledger_entries", "original_currency")
    op.drop_column("ledger_entries", "original_amount")
