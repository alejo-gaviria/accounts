from fastapi import Header, HTTPException

from src.config import settings


async def require_api_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> None:
    # static v1 key, not production-grade
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
