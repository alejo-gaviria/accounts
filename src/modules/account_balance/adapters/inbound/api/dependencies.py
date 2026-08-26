"""FastAPI dependencies: auth guard and Idempotency-Key extraction.

The UnitOfWork/use-case factory used to live here too; it now lives in
AccountBalanceContainer (adapters/config/container.py) per the
dependency-injector refactor (design.md "Dependency Injection") —
routes resolve those via `@inject` + `Provide[...]`, not through a
plain FastAPI `Depends(get_unit_of_work)` function.
"""

from fastapi import Header, HTTPException

from src.config import settings


async def require_api_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> None:
    """v1/local-only placeholder auth guard: a single shared static key
    compared in plain Python — no hashing, no rotation, no per-client
    scoping, no rate limiting.

    NOT PRODUCTION-GRADE. This exists only so the service isn't
    completely open locally. Replace with real credential issuance
    (JWT / proper service-to-service auth, per design.md's "Security"
    section deferred items) before deploying anywhere that isn't purely
    local development. Tracked in README.md "Known risks".
    """
    if x_api_key is None or x_api_key != settings.api_key:
        raise HTTPException(
            status_code=401,
            detail={
                "error": {
                    "code": "unauthorized",
                    "message": "Missing or invalid X-API-Key",
                }
            },
        )


async def require_idempotency_key(
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> str:
    if idempotency_key is None or not idempotency_key.strip():
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "missing_idempotency_key",
                    "message": "Missing or malformed Idempotency-Key header",
                }
            },
        )
    return idempotency_key
