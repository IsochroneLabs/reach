"""Routes of S1.10 on the hand-made model of test_fit.py (no database: canned rows)."""

from __future__ import annotations

import time
from typing import Any

from fastapi.testclient import TestClient

from reach_api import db as q
from reach_api import pois
from reach_api.main import create_app
from reach_api.routes import _words, persona_profile

from .conftest import FakeDatabase, make_deps
from .test_fit import PROFILE, _model


class RowsDatabase(FakeDatabase):
    def __init__(self, rows: dict[str, list[dict[str, Any]]]) -> None:
        super().__init__()
        self.rows = rows
        self.params: list[Any] = []

    async def fetch(self, query: str, params: Any = None) -> list[dict[str, Any]]:
        self.params.append(params)
        return self.rows.get(query, [])


TRIP = {
    "cell_id": "A",
    "trip_window": "night_return",
    "time_s": 1200,
    "departure": "00:47",
    "access_s": 120,
    "wait_s": 60,
    "in_vehicle_s": 900,
    "egress_s": 120,
    "transfers": 0,
    "first_stop": "Uhlandstraße",
    "first_route": "N95",
    "walk_only": False,
}


def _client(rows: dict) -> tuple[TestClient, RowsDatabase]:
    db = RowsDatabase(rows)
    deps = make_deps(db)
    deps.models._model = _model()
    deps.models._checked = time.monotonic() + 3600
    client = TestClient(create_app(deps))
    client.__enter__()  # runs the lifespan that puts deps on app.state
    return client, db


def test_fit_and_cache() -> None:
    client, _ = _client({})
    r = client.post("/api/fit", json=PROFILE)
    assert r.status_code == 200 and r.json()["cells"]["A"][0] == 90
    assert client.post("/api/fit", json=PROFILE).json() == r.json()
    bad = client.post("/api/fit", json=dict(PROFILE, modes=["bike"]))
    assert bad.status_code == 422 and "modes" in bad.json()["detail"]
    extra = client.post("/api/fit", json=dict(PROFILE, email="x@y"))
    assert extra.status_code == 422


def test_cell_detail_with_legs() -> None:
    rows = {
        q.Q_CELL_TRIPS: [
            dict(TRIP, destination_id="nightlife:n9", mode="transit"),
            dict(TRIP, destination_id="nightlife:n9", mode="walk", time_s=1500, first_stop=None),
        ]
    }
    client, db = _client(rows)
    body = dict(PROFILE, modes=["walk", "transit"])
    r = client.post("/api/cell/A", json=body)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["district"] == "West" and d["populated"] is True and d["fit"] is not None
    transit = next(t for t in d["trips"] if t["mode"] == "transit")
    assert transit["legs"]["last_departure"] == "00:47" and transit["legs"]["in_vehicle_min"] == 15
    assert "legs" not in next(t for t in d["trips"] if t["mode"] == "walk")
    trip_params = next(p for p in db.params if isinstance(p, list) and p and p[0] == "A")
    assert "nightlife:n9" in trip_params[1]


def test_cell_trips_carry_points_shares_and_opening_hours() -> None:
    rows = {
        q.Q_CELL_TRIPS: [
            dict(TRIP, destination_id="campus_site:morgenstelle", mode="walk", time_s=720),
            dict(TRIP, destination_id="nightlife:n9", mode="walk", time_s=1500, first_stop=None),
        ],
        pois.Q_DETAILS_EXIST: [{"ok": True}],
        pois.Q_POINTS_DETAILS: [
            {"destination_id": "campus_site:morgenstelle", "lon": 9.0352, "lat": 48.5371},
            {
                "destination_id": "nightlife:n9",
                "lon": 9.0571,
                "lat": 48.5203,
                "opening_hours": "Th-Sa 21:00-03:00",
                "website": None,
                "wheelchair": "no",
            },
        ],
    }
    client, _ = _client(rows)
    trips = client.post("/api/cell/A", json=PROFILE).json()["trips"]
    campus = next(t for t in trips if t["destination_id"] == "campus_site:morgenstelle")
    bar = next(t for t in trips if t["destination_id"] == "nightlife:n9")
    assert campus["share"] == 1 and campus["point"] == [9.0352, 48.5371]
    assert bar["opening_hours"] == "Th-Sa 21:00-03:00" and "website" not in bar
    assert "share" not in bar
    assert client.post("/api/cell/ZZZ", json=PROFILE).status_code == 404


def test_reference_routes_and_search() -> None:
    rows = {
        q.Q_SEARCH: [
            {"label": "Wilhelmstr. 5, Tübingen", "cell_id": "A", "lon": 9.06, "lat": 48.5}
        ],
        q.Q_SITES: [
            {"site_id": "morgenstelle", "name": "M", "lon": 9.0, "lat": 48.5, "default_share": 0.5}
        ],
    }
    client, db = _client(rows)
    types = {t["destination_type"]: t for t in client.get("/api/destination-types").json()}
    assert [lab["label"] for lab in types["sport"]["labels"]] == ["tennis"]
    assert types["grocery"]["labels"][0]["kind"] == "brand"
    sites = client.get("/api/campus-sites").json()
    assert sites[0]["programmes"] == ["biology"]
    assert client.get("/api/programmes").json()[0]["sites"] == ["morgenstelle"]
    hits = client.post("/api/addresses/search", json={"q": "Wilhelmstraße 5"}).json()
    assert hits[0]["cell_id"] == "A" and db.params[-1][0] == ["%wilhelmstr%", "%5%"]
    assert client.post("/api/addresses/search", json={"q": "ab"}).status_code == 422


def test_helpers() -> None:
    assert _words("Hölderlinstr. 10") == ["%hölderlinstr%", "%10%"]
    prof = persona_profile({"modes": ["bike"], "destinations": {"mensa": 2}, "programme": "law"})
    assert prof == {
        "modes": ["bike"],
        "destinations": {"mensa": {"importance": 2}},
        "programme": "law",
    }
