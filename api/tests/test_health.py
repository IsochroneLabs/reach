"""Health endpoint, build SHA, CORS allowlist and error handlers."""

from __future__ import annotations

import psycopg
from fastapi.testclient import TestClient

from reach_api.main import app, create_app
from reach_api.valhalla import NoRouteError, ValhallaError, ValhallaTimeout

from .conftest import FakeDatabase, make_deps


def test_health_without_environment() -> None:
    # The module-level app imports without DATABASE_URL_API; health needs no database.
    response = TestClient(app).get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_health_reports_build_sha(client: TestClient, db: FakeDatabase) -> None:
    body = client.get("/api/health").json()
    assert body["build_sha"] == "abc1234" and body["version"]
    assert client.head("/api/health").status_code == 200
    assert db.calls == []  # liveness never touches the database


def test_cors_allows_only_configured_origins(client: TestClient) -> None:
    allowed = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:5173"
    other = client.get("/api/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in other.headers


def test_error_handlers(db: FakeDatabase) -> None:
    test_app = create_app(make_deps(db))
    errors = {
        "/no-route": NoRouteError("x"),
        "/timeout": ValhallaTimeout("x"),
        "/valhalla": ValhallaError("x"),
        "/db": psycopg.OperationalError("x"),
    }

    def raising(exc: Exception):
        def boom() -> None:
            raise exc

        return boom

    for path, exc in errors.items():
        test_app.add_api_route(path, raising(exc))
    with TestClient(test_app, raise_server_exceptions=False) as c:
        codes = {path: c.get(path).status_code for path in errors}
    assert codes == {"/no-route": 422, "/timeout": 504, "/valhalla": 502, "/db": 503}
