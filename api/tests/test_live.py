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

    # Scored cell: list from current.reachable (no matrix for it); one isochrone (all contours),
    # one route per category with a reachable facility, one matrix for the next facility of the
    # category in "lack" and its route.
    assert body["source"] == "precomputed"
    assert valhalla["isochrone"].call_count == 1
    assert valhalla["matrix"].call_count == 1
    assert valhalla["route"].call_count == 2


def test_live_matrix_uses_run_costing(
    client: TestClient, db: FakeDatabase, valhalla: respx.MockRouter
) -> None:
    db.scored = False  # only grid cells without residents call the live matrix
    body = client.post("/api/inspect", json=INSPECT).json()
    # the facilities within the budget, then the next facility of the category in "lack"
    assert body["source"] == "live" and valhalla["matrix"].call_count == 2
    for call in valhalla["matrix"].calls:
        sent = json.loads(call.request.content)
        assert sent["costing"] == "pedestrian"
    sent = json.loads(valhalla["matrix"].calls[0].request.content)
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


def test_outside_city_rejected_before_valhalla(
    client: TestClient, db: FakeDatabase, valhalla: respx.MockRouter
) -> None:
    db.scored = db.in_city = db.click_in_city = False
    for path, body in [
        ("/api/inspect", INSPECT),
        ("/api/expansion", INSPECT),
        ("/api/catchment", INSPECT),
        ("/api/isochrone", {**INSPECT, "direction": "reverse"}),
    ]:
        r = client.post(path, json=body)
        assert r.status_code == 422, path
        assert "outside the city boundary" in r.json()["detail"]
    assert valhalla.calls.call_count == 0


def test_cell_status(client: TestClient, db: FakeDatabase, valhalla: respx.MockRouter) -> None:
    # scored (Marktplatz), unpopulated (field near Hagelloch: centre in the city, no residents),
    # outside_city (edge cell in Unterjesingen: click in the city, centre outside); each answered
    for scored, in_city, status, source in [
        (True, True, "scored", "precomputed"),
        (False, True, "unpopulated", "live"),
        (False, False, "outside_city", "live"),
    ]:
        db.scored, db.in_city = scored, in_city
        inspect = client.post("/api/inspect", json=INSPECT).json()
        assert inspect["cell"]["status"] == status and inspect["source"] == source
        iso = client.post("/api/isochrone", json=INSPECT).json()
        assert iso["cell"]["status"] == status
    # a cell whose centre lies in the city is accepted even if the click is just outside
    db.click_in_city = False
    db.in_city = True
    assert client.post("/api/inspect", json=INSPECT).json()["cell"]["status"] == "unpopulated"


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


def test_isochrone_directions(
    client: TestClient, valhalla: respx.MockRouter, rec: dict[str, Any]
) -> None:
    reverse = client.post("/api/isochrone", json={**INSPECT, "direction": "reverse"})
    assert reverse.status_code == 200
    body = reverse.json()
    assert body["direction"] == "reverse" and body["cell"]["cell_id"] == CELL
    assert body["cached"] is False
    assert json.loads(valhalla["isochrone"].calls.last.request.content)["reverse"] is True
    assert len(body["isochrone"]["features"]) == len(rec["isochrone_reverse"]["features"])
    assert [f["properties"]["contour_min"] for f in body["isochrone"]["features"]] == [
        5.0,
        10.0,
        15.0,
    ]
    # forward is the default and cached separately from reverse
    forward = client.post("/api/isochrone", json=INSPECT).json()
    assert forward["direction"] == "forward" and forward["cached"] is False
    assert forward["isochrone"] != body["isochrone"]
    calls = valhalla["isochrone"].call_count
    again = client.post("/api/isochrone", json={**INSPECT, "direction": "reverse"}).json()
    assert again["cached"] is True and valhalla["isochrone"].call_count == calls
    assert {**again, "cached": False} == body


def test_isochrone_validation(client: TestClient, valhalla: respx.MockRouter) -> None:
    assert client.post("/api/isochrone", json={**INSPECT, "direction": "up"}).status_code == 422
    assert client.post("/api/isochrone", json={**INSPECT, "profile": "car"}).status_code == 422
    assert valhalla.calls.call_count == 0


def _category(body: dict[str, Any], category: str) -> dict[str, Any]:
    return next(c for c in body["categories"] if c["category"] == category)


def test_reachable_facilities_carry_their_point(client: TestClient, rec: dict[str, Any]) -> None:
    grocery = _category(client.post("/api/inspect", json=INSPECT).json(), "grocery")
    near = rec["points"][2:]
    assert [f["point"] for f in grocery["reachable"]] == [
        [round(p["lon"], 6), round(p["lat"], 6)] for p in near
    ]
    assert all(
        set(f) == {"facility_id", "name", "time_s", "time_min", "point"}
        for f in grocery["reachable"]
    )


def test_next_facility_beyond_the_budget(
    client: TestClient, valhalla: respx.MockRouter, rec: dict[str, Any]
) -> None:
    body = client.post("/api/inspect", json=INSPECT).json()
    # grocery is sufficient (2 of 2): nothing to look for
    assert _category(body, "grocery")["next_facility"] is None
    assert _category(body, "grocery")["next_note"] is None
    # pharmacy is in "lack": the fastest of the two candidates (recorded 1780 s and 1712 s)
    pharmacy = _category(body, "pharmacy")
    nxt = pharmacy["next_facility"]
    assert pharmacy["next_note"] is None
    assert nxt["facility_id"] == "w396807347" and nxt["name"] == "E-Center Haid"
    assert nxt["time_s"] == 1712 and nxt["time_min"] == 28.53
    assert nxt["within_budget"] is False
    assert nxt["point"] == [round(rec["points"][1]["lon"], 6), round(rec["points"][1]["lat"], 6)]
    assert nxt["route"]["geometry"]["type"] == "LineString"
    # one matrix from the origin to both candidates, the costing of the run
    sent = json.loads(valhalla["matrix"].calls.last.request.content)
    assert len(sent["sources"]) == 1 and len(sent["targets"]) == 2
    assert sent["costing_options"] == {"pedestrian": {"walking_speed": 3.39}}


def test_next_facility_within_the_budget_for_an_insufficient_category(
    client: TestClient, db: FakeDatabase, valhalla: respx.MockRouter
) -> None:
    # grocery 1 of 2: the counted facility is excluded, the fastest of the others is the next
    # one (225 s: inside the budget, e.g. a cell whose count was thinned by the budget edge)
    db.reachable_n = 1
    db.scores[0] = {**db.scores[0], "count": 1, "class": "insufficient", "deficit": 80.0}
    body = client.post("/api/inspect", json=INSPECT).json()
    grocery = _category(body, "grocery")
    assert [f["facility_id"] for f in grocery["reachable"]] == ["n2978948434"]
    nxt = grocery["next_facility"]
    assert nxt["facility_id"] == "n5183783736" and nxt["time_s"] == 225
    assert nxt["within_budget"] is True
    # all categories with a missing facility share one matrix (1 grocery + 2 pharmacy points)
    assert valhalla["matrix"].call_count == 1
    sent = json.loads(valhalla["matrix"].calls.last.request.content)
    assert len(sent["targets"]) == 3


def test_next_facility_none_within_max_time(
    db: FakeDatabase, valhalla: respx.MockRouter, make_deps: Any
) -> None:
    from reach_api.settings import NextFacility

    deps = make_deps(db, next_facility=NextFacility(candidates=8, max_time_min=20))
    with TestClient(create_app(deps)) as c:
        pharmacy = _category(c.post("/api/inspect", json=INSPECT).json(), "pharmacy")
    # the fastest candidate needs 28.5 min
    assert pharmacy["next_facility"] is None
    assert pharmacy["next_note"] == "No facility of this category within 20 min."


def test_next_facility_candidate_limit(
    db: FakeDatabase, valhalla: respx.MockRouter, make_deps: Any
) -> None:
    from reach_api.settings import NextFacility

    deps = make_deps(db, next_facility=NextFacility(candidates=1, max_time_min=60))
    with TestClient(create_app(deps)) as c:
        c.post("/api/inspect", json=INSPECT)
    sent = json.loads(valhalla["matrix"].calls.last.request.content)
    assert len(sent["targets"]) == 1


def test_next_facility_failure_keeps_the_rest(
    client: TestClient, valhalla: respx.MockRouter
) -> None:
    valhalla["matrix"].mock(return_value=httpx.Response(400, json={"error": "no edges"}))
    r = client.post("/api/inspect", json=INSPECT)
    assert r.status_code == 200
    pharmacy = _category(r.json(), "pharmacy")
    assert pharmacy["next_facility"] is None
    assert pharmacy["next_note"] == "The next facility could not be calculated right now."
    assert len(_category(r.json(), "grocery")["reachable"]) == 2


def test_next_facility_for_an_unscored_cell(client: TestClient, db: FakeDatabase) -> None:
    db.scored = False
    pharmacy = _category(client.post("/api/inspect", json=INSPECT).json(), "pharmacy")
    assert pharmacy["next_facility"]["time_s"] == 1712


def test_route_to_a_facility(
    client: TestClient, valhalla: respx.MockRouter, rec: dict[str, Any]
) -> None:
    last = rec["points"][-1]
    body = {**INSPECT, "facility_id": last["facility_id"]}
    r = client.post("/api/route", json=body)
    assert r.status_code == 200
    answer = r.json()
    assert answer["cell"]["cell_id"] == CELL and answer["cached"] is False
    assert answer["facility"]["name"] == last["name"]
    assert answer["facility"]["point"] == [round(last["lon"], 6), round(last["lat"], 6)]
    assert answer["route"]["geometry"]["type"] == "LineString"
    assert answer["within_budget"] is True  # recorded route: 226 s
    sent = json.loads(valhalla["route"].calls.last.request.content)
    assert sent["costing"] == "pedestrian"
    # cached per (run, cell, profile, facility)
    calls = valhalla["route"].call_count
    again = client.post("/api/route", json=body).json()
    assert again["cached"] is True and valhalla["route"].call_count == calls


def test_route_validation(client: TestClient, db: FakeDatabase, valhalla: respx.MockRouter) -> None:
    body = {**INSPECT, "facility_id": "w1"}
    assert client.post("/api/route", json=body).status_code == 404  # unknown facility
    assert client.post("/api/route", json=INSPECT).status_code == 422  # facility_id missing
    assert client.post("/api/route", json={**body, "profile": "car"}).status_code == 422
    db.in_city = db.click_in_city = db.scored = False
    assert client.post("/api/route", json=body).status_code == 422  # outside the city
    assert valhalla.calls.call_count == 0
