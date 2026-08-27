from fastapi import FastAPI

from src.modules.account_balance.adapters.config.container import (
    AccountBalanceContainer,
)
from src.modules.account_balance.adapters.inbound.api.error_handlers import (
    register_error_handlers,
)
from src.modules.account_balance.adapters.inbound.api.router import (
    router as account_balance_router,
)

_WIRED_MODULES = [
    "src.modules.account_balance.adapters.inbound.api.router",
]


def create_app() -> FastAPI:
    container = AccountBalanceContainer()
    container.wire(modules=_WIRED_MODULES)

    app = FastAPI(title="supercool-finances-accounts", version="0.1.0", description="Accounts")
    app.container = container  # exposed for tests to override providers
    register_error_handlers(app)
    app.include_router(account_balance_router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
