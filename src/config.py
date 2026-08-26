"""Application configuration.

Loaded once as a module-level ``settings`` singleton via pydantic-settings.
Values come from environment variables (or a local ``.env`` file, see
``.env.example``) with sane local-dev defaults matching
``docker-compose.yml``'s ``db`` service.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Owner/migration connection — DDL rights, used to run Alembic.
    database_url: str = "postgresql+asyncpg://accounts:accounts@localhost:5432/accounts"

    # Restricted runtime connection used by the FastAPI app (wired in
    # src/db.py). Created by the initial migration with narrow grants:
    # INSERT/SELECT-only on ledger_entries (no UPDATE/DELETE — enforces
    # append-only at the DB), INSERT/SELECT/UPDATE on accounts, no DDL.
    app_db_role: str = "accounts_app"
    app_db_password: str = "accounts_app"

    @property
    def app_database_url(self) -> str:
        owner_prefix, _, host_and_db = self.database_url.partition("@")
        scheme = owner_prefix.split("://", 1)[0]
        return f"{scheme}://{self.app_db_role}:{self.app_db_password}@{host_and_db}"

    # v1/local-only placeholder credential — see
    # adapters/inbound/api/dependencies.py for the security caveat.
    api_key: str = "00000000-0000-0000-0000-000000000000"


settings = Settings()
