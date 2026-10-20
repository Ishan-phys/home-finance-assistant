"""Error envelope: every error body carries a code and a correlation id (spec 4.8)."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable

from cfo.api import friendly
from cfo.api.friendly import Friendly
from cfo.core.errors import (
    CategoryInUse,
    ConflictError,
    InvalidInput,
    NotFoundError,
    RedactionFailed,
    SetupRequired,
)
from cfo.parse.base import ParseFailed, PasswordInvalid, PasswordRequired, ValidationFailed
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

log = logging.getLogger("cfo.api")
HEADER = "X-Correlation-ID"


def _body(
    request: Request,
    code: str,
    message: str,
    hint: str | None = None,
    detail: str | None = None,
) -> dict[str, object]:
    """`message` and `hint` are for the owner; `detail` is the technical reason, for support."""
    return {
        "error": {
            "code": code,
            "message": message,
            "hint": hint,
            "detail": detail,
            "correlation_id": getattr(request.state, "correlation_id", None),
        }
    }


class CorrelationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        request.state.correlation_id = request.headers.get(HEADER) or uuid.uuid4().hex
        response = await call_next(request)
        response.headers[HEADER] = request.state.correlation_id
        return response


def install(app: FastAPI) -> None:
    app.add_middleware(CorrelationMiddleware)

    def handler(status: int, code: str, words: Callable[[str], Friendly] | Friendly | None = None):  # type: ignore[no-untyped-def]
        async def _handle(request: Request, exc: Exception) -> JSONResponse:
            text = str(exc)
            said = words(text) if callable(words) else words
            if said is None:
                return JSONResponse(_body(request, code, text), status_code=status)
            return JSONResponse(
                _body(request, code, said.message, said.hint, text), status_code=status
            )

        return _handle

    app.add_exception_handler(ParseFailed, handler(422, "PARSE_FAILED", friendly.parse_failure))
    app.add_exception_handler(
        PasswordRequired, handler(422, "PASSWORD_REQUIRED", friendly.PASSWORD_REQUIRED)
    )
    app.add_exception_handler(
        PasswordInvalid, handler(422, "PASSWORD_INVALID", friendly.PASSWORD_INVALID)
    )
    app.add_exception_handler(
        ValidationFailed, handler(422, "VALIDATION_FAILED", friendly.validation_failure)
    )
    app.add_exception_handler(
        RedactionFailed, handler(422, "REDACTION_FAILED", friendly.REDACTION_FAILED)
    )
    app.add_exception_handler(NotFoundError, handler(404, "NOT_FOUND"))
    app.add_exception_handler(ConflictError, handler(409, "CONFLICT"))
    app.add_exception_handler(
        SetupRequired, handler(409, "SETUP_REQUIRED", friendly.SETUP_REQUIRED)
    )
    app.add_exception_handler(
        CategoryInUse, handler(409, "CATEGORY_IN_USE", friendly.CATEGORY_IN_USE)
    )
    app.add_exception_handler(InvalidInput, handler(422, "INVALID_INPUT"))

    async def invalid(request: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, RequestValidationError)
        first = exc.errors()[0] if exc.errors() else {}
        where = ".".join(str(p) for p in first.get("loc", ()) if p != "body")
        raw = f"{where}: {first.get('msg', 'invalid request')}"
        said = friendly.request_failure(where, str(first.get("msg", "invalid request")))
        return JSONResponse(
            _body(request, "VALIDATION_FAILED", said.message, said.hint, raw), status_code=422
        )

    app.add_exception_handler(RequestValidationError, invalid)

    async def unexpected(request: Request, exc: Exception) -> JSONResponse:
        # Generic body only; the database transaction already rolled back.
        log.exception("unhandled error", extra={"correlation_id": request.state.correlation_id})
        return JSONResponse(
            _body(request, "INTERNAL", friendly.INTERNAL.message, friendly.INTERNAL.hint),
            status_code=500,
            headers={HEADER: request.state.correlation_id},
        )

    app.add_exception_handler(Exception, unexpected)
