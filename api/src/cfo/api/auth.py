"""Owner sign-in: one username and password, and a signed session cookie.

The password is never stored. OWNER_PASSWORD_HASH holds a scrypt hash, made with
`python -m cfo.api.auth`. A session is a cookie the server can check without storing anything:
a payload (username and expiry) plus an HMAC over it. The HMAC key is made from SESSION_SECRET
and the password hash together, so changing the password signs every browser out and nothing
derived from the password is stored in the cookie. A restart keeps everyone signed in; rotating
SESSION_SECRET signs everyone out. Logging out clears the cookie in the
browser only: a copy of the cookie stays valid until it expires or a secret changes.

Every route is locked unless it is listed as public here. Without a complete setup every locked
route refuses, so a missing password can never open the ledger.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import threading
import time
from collections.abc import Callable
from typing import Any

from cfo.api.config import Settings
from fastapi import APIRouter, Depends, FastAPI, Request, Response
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

COOKIE = "cfo_session"
SESSION_SECONDS = 5 * 24 * 3600
LOCK_AFTER = 5  # failed sign-ins in the window that lock the form
LOCK_SECONDS = 15 * 60
MIN_SECRET_LENGTH = 32

# scrypt cost: about 50 ms here, enough that guessing offline is slow. maxmem is raised because
# the default 32 MiB is just short of what these parameters need.
_N, _R, _P = 2**15, 8, 1
_MAXMEM = 64 * 1024 * 1024


class NotSignedIn(Exception):
    """A locked route was called without a valid session."""


class SignInNotReady(Exception):
    """Sign-in is not set up: the username, password hash or session secret is missing."""


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32, maxmem=_MAXMEM
    )
    return f"scrypt${_N}${_R}${_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        candidate = hashlib.scrypt(
            password.encode(),
            salt=_unb64(salt),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(_unb64(digest)),
            maxmem=_MAXMEM,
        )
    except ValueError:
        return False
    return hmac.compare_digest(candidate, _unb64(digest))


def _signing_key(secret: str, password_hash: str) -> bytes:
    """A key that changes when either the session secret or the password does."""
    return hmac.new(secret.encode(), password_hash.encode(), hashlib.sha256).digest()


def _sign(payload: str, key: bytes) -> str:
    return _b64(hmac.new(key, payload.encode(), hashlib.sha256).digest())


def make_session(username: str, secret: str, password_hash: str, now: float) -> str:
    payload = _b64(
        json.dumps({"u": username, "e": int(now) + SESSION_SECONDS}, separators=(",", ":")).encode()
    )
    return f"{payload}.{_sign(payload, _signing_key(secret, password_hash))}"


def session_is_valid(
    token: str, *, username: str, secret: str, password_hash: str, now: float
) -> bool:
    try:
        payload, signature = token.split(".")
        if not hmac.compare_digest(signature, _sign(payload, _signing_key(secret, password_hash))):
            return False
        data: dict[str, Any] = json.loads(_unb64(payload))
        return hmac.compare_digest(str(data["u"]), username) and float(data["e"]) > now
    except (ValueError, KeyError, TypeError):
        return False


class LoginLimit:
    """Counts failed sign-ins in a rolling window. One owner, so one counter for the whole app."""

    def __init__(self) -> None:
        self._failures: list[float] = []
        self._lock = threading.Lock()

    def seconds_locked(self, now: float) -> int:
        with self._lock:
            self._failures = [t for t in self._failures if now - t < LOCK_SECONDS]
            if len(self._failures) < LOCK_AFTER:
                return 0
            return max(1, int(self._failures[-1] + LOCK_SECONDS - now) + 1)

    def failed(self, now: float) -> None:
        with self._lock:
            self._failures.append(now)

    def succeeded(self) -> None:
        with self._lock:
            self._failures.clear()


class SignIn:
    """The sign-in state for one app: its settings, the failure counter, and the clock."""

    def __init__(self, settings: Settings, now: Callable[[], float] = time.time) -> None:
        self.settings = settings
        self.now = now
        self.limit = LoginLimit()

    @property
    def problem(self) -> str | None:
        """Why sign-in cannot work yet, or None when it is ready."""
        s = self.settings
        if not s.owner_username or not s.owner_password_hash:
            return "OWNER_USERNAME and OWNER_PASSWORD_HASH must be set in .env"
        if len(s.session_secret) < MIN_SECRET_LENGTH:
            return f"SESSION_SECRET must be at least {MIN_SECRET_LENGTH} characters"
        return None

    def valid_cookie(self, token: str | None) -> bool:
        s = self.settings
        return bool(token) and session_is_valid(
            token or "",
            username=s.owner_username,
            secret=s.session_secret,
            password_hash=s.owner_password_hash,
            now=self.now(),
        )

    def issue(self, response: Response) -> None:
        s = self.settings
        token = make_session(s.owner_username, s.session_secret, s.owner_password_hash, self.now())
        response.set_cookie(
            COOKIE,
            token,
            max_age=SESSION_SECONDS,
            httponly=True,
            secure=s.session_cookie_secure,
            samesite="lax",
            path="/",
        )


class LoginBody(BaseModel):
    username: str
    password: str


def _error(request: Request, status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        {
            "error": {
                "code": code,
                "message": message,
                "hint": None,
                "detail": None,
                "correlation_id": getattr(request.state, "correlation_id", None),
            }
        },
        status_code=status,
    )


def require_owner(request: Request) -> None:
    """The dependency every locked route carries."""
    signin: SignIn = request.app.state.auth
    if signin.problem is not None:
        raise SignInNotReady(signin.problem)
    if not signin.valid_cookie(request.cookies.get(COOKIE)):
        raise NotSignedIn()


def public_router(signin: SignIn) -> APIRouter:
    router = APIRouter()

    @router.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @router.post("/auth/login")
    def login(body: LoginBody, request: Request, response: Response) -> Any:  # dict or error
        if signin.problem is not None:
            raise SignInNotReady(signin.problem)
        wait = signin.limit.seconds_locked(signin.now())
        if wait:
            minutes = max(1, -(-wait // 60))
            return _error(
                request,
                429,
                "TOO_MANY_ATTEMPTS",
                f"Too many failed sign-in attempts. Wait {minutes} minute(s) and try again.",
            )
        s = signin.settings
        # Check the password even for a wrong username, so the reply takes the same time.
        password_ok = verify_password(body.password, s.owner_password_hash)
        same_user = hmac.compare_digest(body.username.encode(), s.owner_username.encode())
        if password_ok and same_user:
            signin.limit.succeeded()
            signin.issue(response)
            return {"username": s.owner_username}
        signin.limit.failed(signin.now())
        return _error(
            request, 401, "INVALID_CREDENTIALS", "That username or password is not right."
        )

    @router.post("/auth/logout", status_code=204)
    def logout(response: Response) -> Response:
        response.status_code = 204
        response.delete_cookie(COOKIE, path="/", secure=signin.settings.session_cookie_secure)
        return response

    @router.get("/auth/me", dependencies=[Depends(require_owner)])
    def me() -> dict[str, str]:
        return {"username": signin.settings.owner_username}

    return router


def docs_router(app: FastAPI) -> APIRouter:
    """The API's schema and Swagger page. FastAPI serves its own copies without any check, so they
    are switched off in create_app and rebuilt here to sit behind the owner's session."""
    router = APIRouter(include_in_schema=False)

    @router.get("/openapi.json")
    def schema() -> dict[str, Any]:
        return app.openapi()

    @router.get("/docs")
    def docs() -> HTMLResponse:
        return get_swagger_ui_html(openapi_url="/openapi.json", title="AI CFO API")

    return router


def install(app: FastAPI, settings: Settings) -> SignIn:
    signin = SignIn(settings)
    app.state.auth = signin

    @app.exception_handler(NotSignedIn)
    def _not_signed_in(request: Request, exc: NotSignedIn) -> JSONResponse:
        return _error(request, 401, "NOT_SIGNED_IN", "Sign in to continue.")

    @app.exception_handler(SignInNotReady)
    def _not_ready(request: Request, exc: SignInNotReady) -> JSONResponse:
        return _error(request, 503, "SIGN_IN_NOT_SET_UP", f"Sign-in is not set up: {exc}.")

    app.include_router(public_router(signin))
    return signin


if __name__ == "__main__":  # `uv run python -m cfo.api.auth` prints a hash for OWNER_PASSWORD_HASH
    import getpass

    first = getpass.getpass("Choose the owner password: ")
    if first != getpass.getpass("Type it again: "):
        raise SystemExit("The two passwords do not match.")
    if len(first) < 12:
        raise SystemExit("Use at least 12 characters.")
    print(hash_password(first))
