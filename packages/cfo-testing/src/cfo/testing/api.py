"""A TestClient that speaks for one person: every path is prefixed with /people/{id}."""

from __future__ import annotations

from typing import Any

UNSCOPED = ("/health", "/sample", "/people", "/catalog")


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


def person_client(database: Any, app: Any, **kw: Any) -> PersonClient:
    """The default test person's client for an app built over `database`."""
    from fastapi.testclient import TestClient

    return PersonClient(TestClient(app, **kw), database.default_person_id)
