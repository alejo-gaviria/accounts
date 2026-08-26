"""App-wide HTTPException -> JSON body normalization.

FastAPI's default handler wraps HTTPException.detail as
`{"detail": <detail>}`. This module raises HTTPException(detail=
{"error": {...}}) throughout, so this handler unwraps it back to the
flat `{error: {code, message}}` shape, with a same-shaped fallback for
anything raised without that structure (e.g. Starlette's own 404 for
an unmatched route).
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def _http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        if isinstance(exc.detail, dict) and "error" in exc.detail:
            return JSONResponse(status_code=exc.status_code, content=exc.detail)
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": "http_error", "message": str(exc.detail)}},
        )
