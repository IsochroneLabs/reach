"""The placeholder app answers the health endpoint."""

from fastapi.testclient import TestClient

from reach_api.main import app


def test_health() -> None:
    response = TestClient(app).get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
