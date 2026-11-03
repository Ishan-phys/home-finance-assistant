"""Owner sign-in: the password is stored as a hash, sessions last five days, every route is locked,
and repeated wrong passwords lock the form for a while."""

from __future__ import annotations

from datetime import date

import pytest
from cfo.api import auth
from cfo.api.app import create_app
from cfo.api.config import Settings
from cfo.ledger.repositories.db import Database
from cfo.testing import SeedClient
from cfo.testing.api import OWNER_PASSWORD, OWNER_USERNAME, TEST_BASE_URL, signed_in_client
from fastapi.testclient import TestClient

TODAY = date(2026, 10, 3)
SECRET = "test-session-secret-that-is-long-enough"


def app_for(database: Database) -> object:
    return create_app(db=database, client=SeedClient(), clock=lambda: TODAY)


def anonymous(app: object) -> TestClient:
    return TestClient(app, base_url=TEST_BASE_URL)  # type: ignore[arg-type]


def test_the_password_is_stored_as_a_salted_hash_never_as_text() -> None:
    stored = auth.hash_password(OWNER_PASSWORD)
    assert OWNER_PASSWORD not in stored
    assert auth.verify_password(OWNER_PASSWORD, stored)
    assert not auth.verify_password("something else", stored)
    assert auth.hash_password(OWNER_PASSWORD) != stored  # a fresh salt each time


def test_a_malformed_stored_hash_refuses_rather_than_raising() -> None:
    assert not auth.verify_password("x", "not-a-hash")
    assert not auth.verify_password("x", "scrypt$1$2$3$!!$!!")


def test_a_session_expires_after_five_days_and_is_tied_to_user_secret_and_password() -> None:
    token = auth.make_session(OWNER_USERNAME, SECRET, "hash-a", now=1_000.0)
    check = dict(username=OWNER_USERNAME, secret=SECRET, password_hash="hash-a")
    assert auth.session_is_valid(token, now=1_000.0, **check)
    assert auth.session_is_valid(token, now=1_000.0 + 5 * 24 * 3600 - 1, **check)
    assert not auth.session_is_valid(token, now=1_000.0 + 5 * 24 * 3600 + 1, **check)
    assert not auth.session_is_valid(token, now=1_000.0, **{**check, "secret": "other" * 8})
    assert not auth.session_is_valid(token, now=1_000.0, **{**check, "password_hash": "hash-b"})
    assert not auth.session_is_valid(token, now=1_000.0, **{**check, "username": "someone"})


def test_a_tampered_session_is_refused() -> None:
    payload, sig = auth.make_session(OWNER_USERNAME, SECRET, "hash-a", now=1_000.0).split(".")
    forged = auth._b64(b'{"u":"owner","e":99999999999}')  # a far-future expiry, old signature
    for token in (f"{forged}.{sig}", f"{payload}.AAAA", "nodot", ""):
        assert not auth.session_is_valid(
            token, username=OWNER_USERNAME, secret=SECRET, password_hash="hash-a", now=1_000.0
        )


def test_signing_in_sets_a_five_day_hardened_cookie_and_it_is_honoured(
    database: Database,
) -> None:
    c = TestClient(app_for(database), base_url=TEST_BASE_URL)
    res = c.post("/auth/login", json={"username": OWNER_USERNAME, "password": OWNER_PASSWORD})
    assert res.status_code == 200 and res.json() == {"username": OWNER_USERNAME}
    cookie = res.headers["set-cookie"].lower()
    assert "cfo_session=" in cookie and "httponly" in cookie and "secure" in cookie
    assert "samesite=lax" in cookie and "max-age=432000" in cookie  # 5 days
    assert c.get("/auth/me").json() == {"username": OWNER_USERNAME}


def test_a_wrong_password_or_wrong_username_gets_the_same_refusal(database: Database) -> None:
    c = anonymous(app_for(database))
    for body in (
        {"username": OWNER_USERNAME, "password": "wrong-password-here"},
        {"username": "someone-else", "password": OWNER_PASSWORD},
    ):
        res = c.post("/auth/login", json=body)
        assert res.status_code == 401
        assert res.json()["error"]["code"] == "INVALID_CREDENTIALS"
        assert "set-cookie" not in res.headers


def test_locked_routes_refuse_without_a_session_and_health_stays_public(
    database: Database,
) -> None:
    c = anonymous(app_for(database))
    assert c.get("/health").json() == {"status": "ok"}
    res = c.get("/people")
    assert res.status_code == 401 and res.json()["error"]["code"] == "NOT_SIGNED_IN"
    assert c.get("/catalog").status_code == 401
    assert c.get("/auth/me").status_code == 401


def test_every_route_but_the_public_ones_refuses_a_signed_out_caller(database: Database) -> None:
    app = app_for(database)
    c = anonymous(app)
    public = {("get", "/health"), ("post", "/auth/login"), ("post", "/auth/logout")}
    seen = 0
    for path, methods in app.openapi()["paths"].items():  # type: ignore[attr-defined]
        url = path.replace("{person_id}", "00000000-0000-0000-0000-000000000000")
        for method in methods:
            if (method, path) in public:
                continue
            seen += 1
            res = c.request(method.upper(), url)
            body = (
                res.json()
                if res.headers.get("content-type", "").startswith("application/json")
                else {}
            )
            assert (
                res.status_code == 401 and body.get("error", {}).get("code") == "NOT_SIGNED_IN"
            ), (
                method,
                path,
                res.status_code,
            )
    assert seen > 20  # the check covered the ledger's routes, not just a handful


def test_a_session_survives_a_restart_but_a_new_secret_or_password_signs_out(
    database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = signed_in_client(app_for(database))
    token = c.cookies["cfo_session"]

    fresh = app_for(database)  # same settings: a restart changes nothing
    fresh_client = anonymous(fresh)
    fresh_client.cookies.set("cfo_session", token)
    assert fresh_client.get("/auth/me").status_code == 200

    monkeypatch.setenv("SESSION_SECRET", "a-different-secret-that-is-also-long-enough")
    rotated = anonymous(app_for(database))
    rotated.cookies.set("cfo_session", token)
    assert rotated.get("/auth/me").status_code == 401


def test_logout_clears_the_cookie_in_the_browser(database: Database) -> None:
    c = signed_in_client(app_for(database))
    res = c.post("/auth/logout")
    assert res.status_code == 204
    assert "cfo_session=" in res.headers["set-cookie"]
    assert "max-age=0" in res.headers["set-cookie"].lower()


def test_repeated_wrong_passwords_lock_the_form_even_for_the_right_one(
    database: Database,
) -> None:
    app = app_for(database)
    now = [10_000.0]
    app.state.auth.now = lambda: now[0]  # type: ignore[attr-defined]
    c = anonymous(app)
    for _ in range(auth.LOCK_AFTER):
        c.post("/auth/login", json={"username": OWNER_USERNAME, "password": "nope-nope-nope"})
    locked = c.post("/auth/login", json={"username": OWNER_USERNAME, "password": OWNER_PASSWORD})
    assert locked.status_code == 429 and locked.json()["error"]["code"] == "TOO_MANY_ATTEMPTS"

    now[0] += auth.LOCK_SECONDS + 1  # the window passes
    ok = c.post("/auth/login", json={"username": OWNER_USERNAME, "password": OWNER_PASSWORD})
    assert ok.status_code == 200


def test_an_unset_owner_or_short_secret_refuses_everything(
    database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OWNER_PASSWORD_HASH", "")
    c = anonymous(app_for(database))
    res = c.post("/auth/login", json={"username": OWNER_USERNAME, "password": OWNER_PASSWORD})
    assert res.status_code == 503 and res.json()["error"]["code"] == "SIGN_IN_NOT_SET_UP"
    assert c.get("/people").status_code == 503
    assert c.get("/health").status_code == 200  # the health check does not depend on sign-in

    monkeypatch.setenv("OWNER_PASSWORD_HASH", auth.hash_password(OWNER_PASSWORD))
    monkeypatch.setenv("SESSION_SECRET", "too-short")
    assert auth.SignIn(Settings.from_env()).problem is not None


def test_the_cookie_flag_follows_the_setting_for_the_test_stack(
    database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
    assert Settings.from_env().session_cookie_secure is False
    monkeypatch.delenv("SESSION_COOKIE_SECURE")
    assert Settings.from_env().session_cookie_secure is True  # secure unless turned off


def test_the_api_schema_and_docs_pages_need_the_session_too(database: Database) -> None:
    """FastAPI serves /docs, /redoc and /openapi.json unprotected unless they are rebuilt."""
    app = app_for(database)
    anon = anonymous(app)
    for path in ("/docs", "/openapi.json"):
        res = anon.get(path)
        assert res.status_code == 401 and res.json()["error"]["code"] == "NOT_SIGNED_IN", path
    assert anon.get("/redoc").status_code == 404  # not offered at all

    owner = signed_in_client(app)
    assert "/people" in owner.get("/openapi.json").json()["paths"]
    assert "swagger" in owner.get("/docs").text.lower()
