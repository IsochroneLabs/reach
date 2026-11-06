"""Read endpoints: GeoJSON passed through from SQL, ETag per run, validation of parameters."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi.testclient import TestClient

from reach_api.main import create_app

RUN_ID = "20261105T184022Z"
FakeDatabase = Any  # conftest.FakeDatabase (not importable with --import-mode=importlib)


def test_cells_geojson_shape_and_etag(client: TestClient, db: FakeDatabase) -> None:
    r = client.get("/api/cells", params={"category": "grocery", "profile": "walking_339"})
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/geo+json"
    body = r.json()
    assert body["type"] == "FeatureCollection" and body["run_id"] == RUN_ID
    feature = body["features"][0]
    assert feature["type"] == "Feature" and feature["geometry"]["type"] == "Polygon"
    lon, lat = feature["geometry"]["coordinates"][0][0]
    assert 8 < lon < 10 and 48 < lat < 49  # EPSG:4326, lon first
    assert r.headers["etag"] == f'W/"{RUN_ID}:cells:grocery:walking_339"'

    again = client.get(
        "/api/cells",
        params={"category": "grocery", "profile": "walking_339"},
        headers={"If-None-Match": r.headers["etag"]},
    )
    assert again.status_code == 304 and again.content == b""
    client.get("/api/cells", params={"category": "grocery", "profile": "walking_339"})
    assert db.calls.count("cells_geojson") == 1  # body cached per run


def test_new_run_changes_etag(client: TestClient, db: FakeDatabase) -> None:
    params = {"category": "grocery", "profile": "walking_339"}
    old = client.get("/api/cells", params=params).headers["etag"]
    db.run = "20261112T030000Z"
    r = client.get("/api/cells", params=params, headers={"If-None-Match": old})
    assert r.status_code == 200 and r.headers["etag"] != old
    assert r.json()["run_id"] == "20261112T030000Z"


def test_cells_rejects_unknown_values(client: TestClient) -> None:
    assert (
        client.get("/api/cells", params={"category": "bars", "profile": "walking_339"}).status_code
        == 422
    )
    assert (
        client.get("/api/cells", params={"category": "grocery", "profile": "car"}).status_code
        == 422
    )
    # Transit supply exists only for walking and wheelchair profiles (methodology §3).
    assert (
        client.get(
            "/api/cells", params={"category": "transit", "profile": "cycling_15"}
        ).status_code
        == 422
    )
    assert (
        client.get(
            "/api/cells", params={"category": "transit", "profile": "walking_339"}
        ).status_code
        == 200
    )


def test_meta(client: TestClient) -> None:
    body = client.get("/api/meta").json()
    assert body["run"]["run_id"] == RUN_ID
    assert body["validation"]["ok"] == 1 and body["validation"]["warn"] == 1
    assert [i["check"] for i in body["validation"]["issues"]] == ["monotonic"]
    assert {"id": "grocery", "name": "Grocery", "k": 2} in body["categories"]
    assert body["transit_classes"] == [{"class": "lack", "lower": 0, "upper": 0}]
    assert {p["profile_id"]: p["transit"] for p in body["profiles"]} == {
        "walking_339": True,
        "cycling_15": False,
    }
    # walking time to stops from the config, only for profiles with transit
    assert {p["profile_id"]: p["transit_budget_min"] for p in body["profiles"]} == {
        "walking_339": 10,
        "cycling_15": None,
    }


def test_meta_etag_follows_transit_budget(db: FakeDatabase, make_deps: Callable[..., Any]) -> None:
    def meta(transit: float, etag: str = "") -> Any:
        d = make_deps(db)
        budgets = d.config.time_budgets_min.model_copy(update={"transit": transit})
        d.config = d.config.model_copy(update={"time_budgets_min": budgets})
        with TestClient(create_app(d)) as c:
            return c.get("/api/meta", headers={"If-None-Match": etag} if etag else {})

    old = meta(10).headers["etag"]
    r = meta(12, old)
    assert r.status_code == 200 and r.headers["etag"] != old
    assert r.json()["profiles"][0]["transit_budget_min"] == 12


def test_districts_and_scores(client: TestClient) -> None:
    r = client.get("/api/districts")
    assert r.status_code == 200 and r.json()["type"] == "FeatureCollection"
    assert client.get("/api/districts/r1/scores").json()["name"] == "Altstadt"
    assert client.get("/api/districts/nope/scores").status_code == 404


def test_recommendations_empty_until_p7(client: TestClient) -> None:
    body = client.get("/api/recommendations").json()
    assert body == {
        "type": "FeatureCollection",
        "run_id": RUN_ID,
        "available": False,
        "features": [],
    }


def test_no_published_run(client: TestClient, db: FakeDatabase) -> None:
    db.run = None
    assert client.get("/api/meta").status_code == 503


def test_health(client: TestClient) -> None:
    assert client.get("/api/health").json()["status"] == "ok"


def test_head_on_every_get_endpoint(client: TestClient) -> None:
    for path in [
        "/api/health",
        "/api/meta",
        "/api/districts",
        "/api/districts/r1/scores",
        "/api/cells?category=grocery&profile=walking_339",
        "/api/recommendations",
    ]:
        get, head = client.get(path), client.head(path)
        assert head.status_code == get.status_code == 200, path
        assert head.content == b"", path
        assert head.headers.get("etag") == get.headers.get("etag"), path
        assert head.headers["content-type"] == get.headers["content-type"], path


def test_every_get_route_allows_head(client: TestClient) -> None:
    routes = [r for r in client.app.routes if "GET" in getattr(r, "methods", set())]
    assert routes and all("HEAD" in r.methods for r in routes), [r.path for r in routes]
