from cfo.api.app import create_app
from cfo.ledger.repositories.db import Database
from fastapi.testclient import TestClient


def test_health() -> None:
    app = create_app(db=Database("postgresql+psycopg://x:y@localhost:1/none"))  # never connected
    assert TestClient(app).get("/health").json() == {"status": "ok"}
