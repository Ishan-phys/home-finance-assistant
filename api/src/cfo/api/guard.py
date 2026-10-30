"""Keep other websites out of a local API.

The API has no login: it is meant to be reached from this machine only. A page on any website in
the owner's browser could still try to talk to 127.0.0.1 (a form post, or DNS rebinding that makes
an attacker's domain resolve to it). Two checks close that: the Host header must name this machine
or the web service, and a browser's Origin on a request that changes data must do the same."""

from __future__ import annotations

from collections.abc import Sequence
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import JSONResponse

DEFAULT_HOSTS = ("localhost", "127.0.0.1", "[::1]", "api", "testserver")
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


class OriginGuard(BaseHTTPMiddleware):
    def __init__(self, app, allowed: Sequence[str]) -> None:  # type: ignore[no-untyped-def]
        super().__init__(app)
        self.allowed = {h.lower() for h in allowed}

    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        origin = request.headers.get("origin")
        if origin and request.method not in _SAFE_METHODS:
            host = (urlsplit(origin).hostname or "").lower()
            host = f"[{host}]" if ":" in host else host
            if host not in self.allowed:
                return JSONResponse(
                    {
                        "error": {
                            "code": "FORBIDDEN_ORIGIN",
                            "message": "This request came from another site.",
                        }
                    },
                    status_code=403,
                )
        return await call_next(request)


def install(app: FastAPI, allowed_hosts: Sequence[str] = DEFAULT_HOSTS) -> None:
    hosts = list(allowed_hosts) or list(DEFAULT_HOSTS)
    app.add_middleware(OriginGuard, allowed=hosts)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=hosts)
