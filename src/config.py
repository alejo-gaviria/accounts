from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # owner/migration role; port 5442 avoids local Postgres conflicts
    database_url: str = "postgresql+asyncpg://accounts:accounts@localhost:5442/accounts"

    app_db_role: str = "accounts_app"
    app_db_password: str = "accounts_app"

    @property
    def app_database_url(self) -> str:
        owner_prefix, _, host_and_db = self.database_url.partition("@")
        scheme = owner_prefix.split("://", 1)[0]
        return f"{scheme}://{self.app_db_role}:{self.app_db_password}@{host_and_db}"

    # v1/local-only placeholder
    api_key: str = "00000000-0000-0000-0000-000000000000"


settings = Settings()
