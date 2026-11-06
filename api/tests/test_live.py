"""Live endpoints with Valhalla mocked from recorded responses."""

from __future__ import annotations

import json
from typing import Any

import httpx
import respx
from fastapi.testclient import TestClient

from reach_api.main import create_app

RUN_ID = "20261105T184022Z"
CELL = "CRS3035RES100mN2823400E4251200"
FakeDatabase = Any  # conftest.FakeDatabase (not importable with --import-mode=importlib)

INSPECT = {"lon": 9.0568, "lat": 48.5204, "profile": "walking_339"}


def test_inspect(client: TestClient, valhalla: respx.MockRouter, rec: dict[str, Any]) -> None:
    r = client.post("/api/inspect", json=INSPECT)
    assert r.status_code == 200
    body = r.json()
    assert body["run_id"] == RUN_ID and body["cached"] is False
    assert body["cell"]["cell_id"] == CELL and body["cell"]["scored"] is True
    # Precomputed values come from the views; the weakest category is the one in "lack".
    assert body["precomputed"]["transit"]["class"] == "high"
    assert body["weakest_category"] == "pharmacy"

    iso = body["isochrone"]
    assert iso["type"] == "FeatureCollection"
    assert [f["properties"] for f in iso["features"]] == [
        {"contour_min": 5.0},
        {"contour_min": 10.0},
        {"contour_min": 15.0},
    ]
    assert all(f["geometry"]["type"] == "Polygon" for f in iso["features"])

    grocery = next(c for c in body["categories"] if c["category"] == "grocery")
    # Recorded times 1780, 1712, 145, 225 s: only the two within 900 s are reachable.
    assert [f["time_s"] for f in grocery["reachable"]] == [145, 225]
    route = grocery["nearest_route"]
    assert route["geometry"]["type"] == "LineString"
    lon, lat = route["geometry"]["coordinates"][0]
    assert abs(lon - rec["origin"][0]) < 1e-3 and abs(lat - rec["origin"][1]) < 1e-3
    pharmacy = next(c for c in body["categories"] if c["category"] == "pharmacy")
    assert pharmacy["reachable"] == [] and pharmacy["nearest_route"] is None

    # Scored cell: list from current.reachable, no matrix; one isochrone (all contours) and
    # one route per category with a reachable facility.
    assert body["source"] == "precomputed"
    assert valhalla["isochrone"].call_count == 1
    assert valhalla["matrix"].call_count == 0
    assert valhalla["route"].call_count == 1


def test_live_matrix_uses_run_costing(
    client: TestClient, db: FakeDatabase, valhalla: respx.MockRouter
) -> None:
    db.scored = False  # only grid cells without residents call the live matrix
    body = client.post("/api/inspect", json=INSPECT).json()
    assert body["source"] == "live" and valhalla["matrix"].call_count == 1
    sent = json.loads(valhalla["matrix"].calls.last.request.content)
    assert sent["costing"] == "pedestrian"
    assert sent["costing_options"] == {"pedestrian": {"walking_speed": 3.39}}
    assert sent["verbose"] is False


def test_cache_hit_avoids_second_call(client: TestClient, valhalla: respx.MockRouter) -> None:
    first = client.post("/api/inspect", json=INSPECT).json()
    calls = valhalla.calls.call_count
    second = client.post("/api/inspect", json={**INSPECT, "lon": 9.05685}).json()
    assert second["cached"] is True
    assert valhalla.calls.call_count == calls
    assert {**second, "cached": False} == first


def test_outside_boundary_rejected_before_valhalla(
    client: TestClient, db: FakeDatabase, valhalla: respx.MockRouter
) -> None:
    db.allowed = False
    for path, body in [
        ("/api/inspect", INSPECT),
        ("/api/expansion", INSPECT),
        ("/api/catchment", INSPECT),
    ]:
        r = client.post(path, json=body)
        assert r.status_code == 422, path
        assert "outside the urban boundary" in r.json()["detail"]
    assert valhalla.calls.call_count == 0


def test_unscored_cell_snapped_and_cached(
    client: TestClient, db: FakeDatabase, valhalla: respx.MockRouter
) -> None:
    db.scored = False
    body = client.post("/api/inspect", json=INSPECT).json()
    assert body["cell"]["scored"] is False and body["precomputed"] is None
    assert body["weakest_category"] is None
    calls = valhalla.calls.call_count
    assert client.post("/api/inspect", json=INSPECT).json()["cached"] is True
    assert valhalla.calls.call_count == calls


def test_scored_cell_lists_published_facilities(client: TestClient, db: FakeDatabase) -> None:
    body = client.post("/api/inspect", json=INSPECT).json()
    grocery = next(c for c in body["categories"] if c["category"] == "grocery")
    assert grocery["count"] == 2 and grocery["count_source"] == "precomputed"
    assert [f["time_s"] for f in grocery["reachable"]] == [145, 225]
    assert "reachable" in db.calls and "facility_points_near" not in db.calls


def test_live_matrix_timeout_is_504(
    db: FakeDatabase, valhalla: respx.MockRouter, make_deps: Any
) -> None:
    from reach_api.settings import LiveValhalla

    db.scored = False
    slow = LiveValhalla(concurrency=1, timeout_s=1, retries=0, backoff_s=0)
    deps = make_deps(db, live_matrix=slow)
    assert deps.live_matrix.cfg.concurrency == 1 and deps.live_matrix.cfg.timeout_s == 1
    valhalla["matrix"].mock(side_effect=httpx.ReadTimeout("slow"))
    with TestClient(create_app(deps)) as c:
        r = c.post("/api/inspect", json=INSPECT)
    assert r.status_code == 504 and valhalla["matrix"].call_count == 1  # no retry configured


def test_unscored_cell_shows_live_count(client: TestClient, db: FakeDatabase) -> None:
    db.scored = False
    body = client.post("/api/inspect", json=INSPECT).json()
    grocery = next(c for c in body["categories"] if c["category"] == "grocery")
    assert body["source"] == "live"
    assert grocery["count"] == 2 and grocery["count_source"] == "live"


def test_unknown_profile(client: TestClient, valhalla: respx.MockRouter) -> None:
    assert client.post("/api/inspect", json={**INSPECT, "profile": "car"}).status_code == 422
    assert valhalla.calls.call_count == 0


def test_catchment_facility(
    client: TestClient, rec: dict[str, Any], valhalla: respx.MockRouter
) -> None:
    facility = rec["points"][-1]
    r = client.post(
        "/api/catchment", json={"facility_id": facility["facility_id"], "profile": "walking_339"}
    )
    assert r.status_code == 200
    body = r.json()
    # Recorded times 210, 302, 270 s from the three cells: all within the budget.
    assert body["cells"] == 3
    assert body["residents"] == sum(c["population"] for c in rec["cells"])
    assert body["residents_by_class"] == {"grocery": {"sufficient": 400}}
    assert body["target"]["kind"] == "facility"
    iso = json.loads(valhalla["isochrone"].calls.last.request.content)
    assert iso["reverse"] is True  # cells reaching the facility, not the other way round
    sent = json.loads(valhalla["matrix"].calls.last.request.content)
    assert len(sent["sources"]) == 3 and len(sent["targets"]) == 1  # cells -> facility


def test_catchment_point_and_validation(client: TestClient) -> None:
    body = client.post("/api/catchment", json=INSPECT).json()
    assert body["target"]["kind"] == "cell" and body["target"]["cell_id"] == CELL
    assert client.post("/api/catchment", json={"profile": "walking_339"}).status_code == 422
    assert (
        client.post(
            "/api/catchment", json={"facility_id": "n0", "profile": "walking_339"}
        ).status_code
        == 404
    )


def test_catchment_of_a_recommended_zone(
    client: TestClient, db: Any, rec: dict[str, Any], valhalla: respx.MockRouter
) -> None:
    db.recommendations = [
        {
            "properties": {
                "category": "pharmacy",
                "profile_id": "walking_339",
                "rank": 1,
                "candidate_id": "CRS3035RES100mN2823400E4251200",
                "population_gain": 163.0,
                "residents_gaining_access": 163,
                "residents_to_sufficient": 163,
                "point": [9.0568, 48.5204],
            }
        }
    ]
    req = {
        "candidate_id": "CRS3035RES100mN2823400E4251200",
        "category": "pharmacy",
        "profile": "walking_339",
    }
    r = client.post("/api/catchment", json=req)
    assert r.status_code == 200
    body = r.json()
    # the stored catchment of the recommender, no live matrix
    assert body["source"] == "precomputed" and not valhalla["matrix"].called
    assert body["cell_ids"] == [c["cell_id"] for c in rec["cells"]] and body["residents"] == 812
    assert body["target"]["kind"] == "candidate" and body["target"]["rank"] == 1
    assert body["residents_by_class"] == {"pharmacy": {"sufficient": 400}}
    iso = json.loads(valhalla["isochrone"].calls.last.request.content)
    assert iso["reverse"] is True
    assert client.post("/api/catchment", json=req).json()["cached"] is True
    for bad, status in [
        ({**req, "category": "grocery"}, 404),  # not recommended for this category
        ({**req, "category": "nope"}, 422),
        ({"candidate_id": req["candidate_id"], "profile": "walking_339"}, 422),  # no category
        ({**req, "facility_id": "n1"}, 422),  # two targets
    ]:
        assert client.post("/api/catchment", json=bad).status_code == status, bad


def test_expansion(client: TestClient, valhalla: respx.MockRouter) -> None:
    body = client.post("/api/expansion", json=INSPECT).json()
    assert body["type"] == "FeatureCollection" and body["budget_min"] == 15.0
    assert body["features"][0]["geometry"]["type"] == "LineString"
    sent = json.loads(valhalla["expansion"].calls.last.request.content)
    assert sent["action"] == "isochrone" and sent["contours"] == [{"time": 15.0}]
    assert client.post("/api/expansion", json=INSPECT).json()["cached"] is True
    assert valhalla["expansion"].call_count == 1


def test_valhalla_errors(
    client: TestClient, valhalla: respx.MockRouter, rec: dict[str, Any]
) -> None:
    valhalla["isochrone"].mock(return_value=httpx.Response(400, json=rec["no_edges"]))
    r = client.post("/api/inspect", json=INSPECT)
    assert r.status_code == 422 and "No suitable edges" in r.json()["detail"]
    valhalla["isochrone"].mock(return_value=httpx.Response(503, text="busy"))
    assert client.post("/api/inspect", json=INSPECT).status_code == 502


def test_rate_limit(db: FakeDatabase, valhalla: respx.MockRouter, make_deps: Any) -> None:
    from reach_api.settings import RateLimit

    deps = make_deps(db, rate_limit=RateLimit(burst=2, per_minute=1, max_clients=100))
    with TestClient(create_app(deps)) as c:
        assert c.post("/api/inspect", json=INSPECT).status_code == 200
        assert c.post("/api/inspect", json=INSPECT).status_code == 200
        r = c.post("/api/inspect", json=INSPECT)
        assert r.status_code == 429 and int(r.headers["retry-after"]) >= 1
        # Read endpoints are not rate-limited.
        assert c.get("/api/meta").status_code == 200


def test_forwarded_for_ignored_from_untrusted_peer(
    db: FakeDatabase, valhalla: respx.MockRouter, make_deps: Any
) -> None:
    from reach_api.settings import RateLimit

    deps = make_deps(db, rate_limit=RateLimit(burst=1, per_minute=1, max_clients=100))
    with TestClient(create_app(deps)) as c:
        # The TestClient peer ("testclient") is no trusted proxy: a spoofed header must not
        # give it a fresh bucket.
        assert (
            c.post("/api/inspect", json=INSPECT, headers={"X-Forwarded-For": "1.1.1.1"}).status_code
            == 200
        )
        assert (
            c.post("/api/inspect", json=INSPECT, headers={"X-Forwarded-For": "2.2.2.2"}).status_code
            == 429
        )
