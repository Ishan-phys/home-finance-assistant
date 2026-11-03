"""A TestClient that speaks for one person: every path is prefixed with /people/{id}."""

from __future__ import annotations

from typing import Any

UNSCOPED = ("/health", "/sample", "/people", "/catalog", "/auth")

# The owner the test app is set up with (see api/tests/conftest.py). Test-only values.
OWNER_USERNAME = "owner"
OWNER_PASSWORD = "test-owner-password"
TEST_BASE_URL = "https://testserver"  # the session cookie is Secure, so the test client is HTTPS


class PersonClient:
    def __init__(self, client: Any, person_id: Any) -> None:
        self.client, self.person_id = client, person_id

    def url(self, path: str) -> str:
        if path.startswith(UNSCOPED):
            return path
        return f"/people/{self.person_id}{path}"

    def request(self, method: str, path: str, **kw: Any) -> Any:
        return self.client.request(method, self.url(path), **kw)

    def get(self, path: str, **kw: Any) -> Any:
        return self.request("GET", path, **kw)

    def post(self, path: str, **kw: Any) -> Any:
        return self.request("POST", path, **kw)

    def put(self, path: str, **kw: Any) -> Any:
        return self.request("PUT", path, **kw)

    def patch(self, path: str, **kw: Any) -> Any:
        return self.request("PATCH", path, **kw)

    def delete(self, path: str, **kw: Any) -> Any:
        return self.request("DELETE", path, **kw)

    def stream(self, method: str, path: str, **kw: Any) -> Any:
        return self.client.stream(method, self.url(path), **kw)

    def headers_of(self, path: str) -> Any:
        return self.client.get(self.url(path)).headers


def signed_in_client(app: Any, **kw: Any) -> Any:
    """A TestClient already signed in as the test owner."""
    from fastapi.testclient import TestClient

    kw.setdefault("base_url", TEST_BASE_URL)
    client = TestClient(app, **kw)
    res = client.post("/auth/login", json={"username": OWNER_USERNAME, "password": OWNER_PASSWORD})
    assert res.status_code == 200, res.text
    return client


def person_client(database: Any, app: Any, **kw: Any) -> PersonClient:
    """The default test person's client for an app built over `database`, signed in."""
    return PersonClient(signed_in_client(app, **kw), database.default_person_id)
