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


def test_cell_times_shape_etag_and_cache(client: TestClient, db: FakeDatabase) -> None:
    r = client.get("/api/cells/times", params={"profile": "walking_339"})
    assert r.status_code == 200 and r.headers["content-type"] == "application/json"
    body = r.json()
    assert body["run_id"] == RUN_ID and body["max_times_per_category"] == 5
    cell = body["cells"][0]
    assert cell["times"]["grocery"] == [146, 301] and cell["population"] == 62
    assert r.headers["etag"] == f'W/"{RUN_ID}:cell_times:walking_339:5"'
    again = client.get(
        "/api/cells/times",
        params={"profile": "walking_339"},
        headers={"If-None-Match": r.headers["etag"]},
    )
    assert again.status_code == 304
    client.get("/api/cells/times", params={"profile": "walking_339"})
    assert db.calls.count("cell_times") == 1
    assert client.get("/api/cells/times", params={"profile": "nope"}).status_code == 422


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
    assert {"id": "grocery", "name": "Grocery", "k": 2, "group": "food"} in body["categories"]
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


def test_recommendations_unavailable_for_a_run_without_them(client: TestClient) -> None:
    r = client.get("/api/recommendations")
    assert r.json() == {
        "type": "FeatureCollection",
        "run_id": RUN_ID,
        "available": False,
        "features": [],
    }
    assert r.headers["content-type"] == "application/geo+json"


def _recommendation(category: str, profile: str, rank: int) -> dict:
    return {
        "type": "Feature",
        "id": f"{profile}/{category}/{rank}",
        "geometry": {"type": "Polygon", "coordinates": [[[9.05, 48.52], [9.06, 48.52]]]},
        "properties": {
            "category": category,
            "profile_id": profile,
            "rank": rank,
            "candidate_id": f"CRS3035RES100mN2823{rank}00E4251200",
            "population_gain": 300.0 / rank,
            "residents_gaining_access": 250,
            "residents_to_sufficient": 250,
            "catchment_residents": 812,
            "catchment_cells": 3,
            "district_id": "r1",
            "district_name": "Altstadt",
            "point": [9.0568, 48.5204],
        },
    }


def test_recommendations_filtered(client: TestClient, db: FakeDatabase) -> None:
    db.recommendations = [
        _recommendation("pharmacy", "walking_339", 1),
        _recommendation("pharmacy", "walking_339", 2),
        _recommendation("grocery", "walking_500", 1),
    ]
    body = client.get("/api/recommendations?category=pharmacy&profile=walking_339").json()
    assert body["available"] is True
    assert [f["properties"]["rank"] for f in body["features"]] == [1, 2]
    assert len(client.get("/api/recommendations").json()["features"]) == 3
    assert client.get("/api/recommendations?category=nope").status_code == 422
    assert client.get("/api/recommendations?profile=nope").status_code == 422
    # cached per run and filter: the second identical request does not query again
    calls = db.calls.count("recommendations_geojson")
    client.get("/api/recommendations")
    assert db.calls.count("recommendations_geojson") == calls


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


def test_facilities_points_and_areas(client: TestClient, db: FakeDatabase) -> None:
    r = client.get("/api/facilities", params={"category": "grocery"})
    assert r.status_code == 200 and r.headers["content-type"] == "application/geo+json"
    body = r.json()
    assert body["run_id"] == RUN_ID and body["category"] == "grocery"
    props = [f["properties"] for f in body["features"]]
    assert {p["kind"] for p in props} == {"facility"}
    assert all(p["osm_url"].startswith("https://www.openstreetmap.org/") for p in props)
    assert any(p["tags"].get("opening_hours") for p in props)
    # geometry=area adds the outline of area facilities (and access points, in the real query)
    area = client.get("/api/facilities", params={"category": "grocery", "geometry": "area"}).json()
    assert {f["properties"]["kind"] for f in area["features"]} == {"facility", "area"}
    # read endpoint: ETag per run and parameters, 304 on revalidation, HEAD
    etag = r.headers["etag"]
    assert (
        etag
        != client.get(
            "/api/facilities", params={"category": "grocery", "geometry": "area"}
        ).headers["etag"]
    )
    assert (
        client.get(
            "/api/facilities", params={"category": "grocery"}, headers={"If-None-Match": etag}
        ).status_code
        == 304
    )
    assert client.head("/api/facilities", params={"category": "grocery"}).status_code == 200


def test_facilities_validation(client: TestClient) -> None:
    assert client.get("/api/facilities", params={"category": "nope"}).status_code == 422
    assert client.get("/api/facilities").status_code == 422
    assert (
        client.get("/api/facilities", params={"category": "grocery", "geometry": "x"}).status_code
        == 422
    )
