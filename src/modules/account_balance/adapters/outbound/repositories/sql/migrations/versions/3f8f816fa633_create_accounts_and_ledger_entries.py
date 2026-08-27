"""create accounts and ledger_entries"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from src.config import settings

# revision identifiers, used by Alembic.
revision: str = "3f8f816fa633"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')

    op.create_table(
        "accounts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("currency", sa.CHAR(3), nullable=False, server_default="USD"),
        sa.Column(
            "balance",
            sa.Numeric(20, 4),
            nullable=False,
            server_default="0",
        ),
        sa.Column("version", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("balance >= 0", name="ck_accounts_balance_non_negative"),
    )

    op.create_table(
        "ledger_entries",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("accounts.id"),
            nullable=False,
        ),
        sa.Column("entry_type", sa.Text(), nullable=False),
        sa.Column("amount", sa.Numeric(20, 4), nullable=False),
        sa.Column("currency", sa.CHAR(3), nullable=False),
        sa.Column("balance_after", sa.Numeric(20, 4), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("transfer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "entry_type IN ('credit', 'debit')", name="ck_ledger_entry_type"
        ),
        sa.CheckConstraint("amount > 0", name="ck_ledger_amount_positive"),
        sa.UniqueConstraint(
            "account_id", "idempotency_key", name="uq_ledger_acct_idem"
        ),
    )
    op.create_index(
        "ix_ledger_account_created",
        "ledger_entries",
        ["account_id", "created_at"],
    )

    # append-only enforced via grants below
    op.execute(f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT FROM pg_catalog.pg_roles WHERE rolname = '{settings.app_db_role}'
            ) THEN
                CREATE ROLE {settings.app_db_role}
                    LOGIN PASSWORD '{settings.app_db_password}';
            END IF;
        END
        $$;
        """)
    op.execute(f"GRANT USAGE ON SCHEMA public TO {settings.app_db_role}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON accounts TO {settings.app_db_role}")
    # no UPDATE/DELETE grant: append-only
    op.execute(f"GRANT SELECT, INSERT ON ledger_entries TO {settings.app_db_role}")
    op.execute(f"REVOKE UPDATE, DELETE ON ledger_entries FROM {settings.app_db_role}")


def downgrade() -> None:
    op.execute(f"REVOKE ALL ON ledger_entries FROM {settings.app_db_role}")
    op.execute(f"REVOKE ALL ON accounts FROM {settings.app_db_role}")
    op.drop_index("ix_ledger_account_created", table_name="ledger_entries")
    op.drop_table("ledger_entries")
    op.drop_table("accounts")
