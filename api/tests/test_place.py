"""POST /api/place (F4.5): target selection, engines and the fit from point times."""

from __future__ import annotations

import time
from datetime import date
from typing import Any

import numpy as np
from fastapi.testclient import TestClient

from reach_api import db as q
from reach_api.main import create_app
from reach_api.otp import OtpTrip
from reach_api.place import Target, _terms

from .conftest import FakeDatabase, make_deps
from .test_fit import PROFILE, _model

WINDOWS = [
    {
        "trip_window": "morning_lecture",
        "time": "08:10",
        "kind": "arrive_by",
        "direction": "to",
        "reference_date": date(2026, 11, 24),
    },
    {
        "trip_window": "midday",
        "time": "12:00",
        "kind": "depart_at",
        "direction": "to",
        "reference_date": date(2026, 11, 24),
    },
    {
        "trip_window": "evening",
        "time": "18:00",
        "kind": "depart_at",
        "direction": "to",
        "reference_date": date(2026, 11, 24),
    },
    {
        "trip_window": "night_return",
        "time": "00:30",
        "kind": "depart_at",
        "direction": "back",
        "reference_date": date(2026, 11, 24),
    },
]

TYPE_ROWS = {
    "mensa": [
        {"destination_id": "mensa:m1", "destination_type": "mensa", "lon": 9.052, "lat": 48.521}
    ],
    "grocery": [
        {"destination_id": "grocery:n1", "destination_type": "grocery", "lon": 9.053, "lat": 48.522}
    ],
    "nightlife": [
        {
            "destination_id": "nightlife:n9",
            "destination_type": "nightlife",
            "lon": 9.054,
            "lat": 48.523,
        }
    ],
}

SITES = [
    {"site_id": "morgenstelle", "name": "M", "lon": 9.0, "lat": 48.5},
    {"site_id": "tal", "name": "T", "lon": 9.1, "lat": 48.5},
]


class PlaceDatabase(FakeDatabase):
    def __init__(self) -> None:
        super().__init__()
        self.params: list[Any] = []
        self.cell = [{"cell_id": "A", "district_id": "d1", "populated": True}]

    async def fetch(self, query: str, params: Any = None) -> list[dict[str, Any]]:
        self.params.append(params)
        if query == q.Q_CELL_AT:
            return self.cell
        if query == q.Q_SITES:
            return SITES
        if query == q.Q_WINDOWS:
            return WINDOWS
        if query == q.Q_NEAREST_TYPE:
            return TYPE_ROWS.get(params[2], [])
        if query == q.Q_NEAREST_LABEL:
            return [
                {
                    "destination_id": "sport:tennis:w1",
                    "destination_type": "sport",
                    "lon": 9.055,
                    "lat": 48.524,
                }
            ]
        if query == q.Q_DESTINATION_POINT:
            return [{"lon": 9.06, "lat": 48.53}]
        return []


class FakeValhalla:
    def __init__(self, seconds: float = 600.0) -> None:
        self.seconds = seconds
        self.calls: list[tuple[str, int]] = []

    async def matrix(self, sources, targets, costing, options) -> np.ndarray:
        self.calls.append((costing, len(targets)))
        return np.full((len(sources), len(targets)), self.seconds)

    async def route(self, origin, target, costing, options):
        return {
            "type": "Feature",
            "properties": {"time_s": 300, "length_m": 1200},
            "geometry": {"type": "LineString", "coordinates": [list(origin), list(target)]},
        }


class FakeOtp:
    def __init__(self) -> None:
        self.calls = 0

    async def plan(self, origin, destination, when, arrive_by, access) -> OtpTrip:
        self.calls += 1
        return OtpTrip(
            time_s=480,
            access_s=60,
            wait_s=120,
            in_vehicle_s=240,
            egress_s=60,
            transfers=0,
            first_stop="Stop",
            first_route="1",
            departure="08:05",
        )


def _client() -> tuple[TestClient, PlaceDatabase, FakeValhalla, FakeOtp]:
    db = PlaceDatabase()
    deps = make_deps(db)
    deps.models._model = _model()
    deps.models._checked = time.monotonic() + 3600
    valhalla, otp = FakeValhalla(), FakeOtp()
    deps.valhalla = valhalla  # type: ignore[assignment]
    deps.otp = otp  # type: ignore[assignment]
    client = TestClient(create_app(deps))
    client.__enter__()
    return client, db, valhalla, otp


def test_place_derives_fit_and_trips_from_the_point() -> None:
    client, db, valhalla, otp = _client()
    r = client.post("/api/place", json={"point": [9.05, 48.52], "profile": PROFILE})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["cell_id"] == "A" and d["district"] == "West" and d["populated"] is True
    assert d["fit"] is not None and d["fit_parts"]
    assert {t["mode"] for t in d["trips"]} == {"walk"}
    assert any(t["destination_type"] == "campus_site" for t in d["trips"])
    assert otp.calls == 0
    assert valhalla.calls and valhalla.calls[0][0] == "pedestrian"
    # campus sites, mensa, grocery, sport:tennis and nightlife from the fake database
    assert len(db.params) >= 6


def test_place_transit_keeps_legs() -> None:
    client, _, _, otp = _client()
    body = {"point": [9.05, 48.52], "profile": dict(PROFILE, modes=["walk", "transit"])}
    r = client.post("/api/place", json=body)
    assert r.status_code == 200, r.text
    transit = [t for t in r.json()["trips"] if t["mode"] == "transit"]
    assert transit and otp.calls > 0
    assert transit[0]["legs"]["first_stop"] == "Stop" and transit[0]["legs"]["wait_min"] == 2


def test_place_requires_weight_and_a_cell() -> None:
    client, db, _, _ = _client()
    empty = dict(PROFILE, destinations={"mensa": {"importance": 0}})
    assert (
        client.post("/api/place", json={"point": [9.05, 48.52], "profile": empty}).status_code
        == 422
    )
    db.cell = []
    assert (
        client.post("/api/place", json={"point": [9.05, 48.52], "profile": PROFILE}).status_code
        == 404
    )


def test_terms_keep_the_minimum_per_term_and_mode() -> None:
    model = _model()
    targets = [
        Target("mensa:m1", "mensa", "mensa", "midday", (9.05, 48.52)),
        Target("mensa:m2", "mensa", "mensa", "midday", (9.06, 48.52)),
    ]
    out = {("mensa:m1", "mensa", "walk"): 600.0, ("mensa:m2", "mensa", "walk"): 300.0}
    terms, modes = _terms(model, targets, out)
    assert terms["mensa"].minutes[0, 0] == 5 and modes == ["walk"]


def test_route_returns_the_geometry_and_mode() -> None:
    client, _, valhalla, _ = _client()
    r = client.post(
        "/api/route",
        json={"origin": [9.05, 48.52], "destination_id": "mensa:m1", "mode": "bike"},
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["properties"]["mode"] == "bike" and d["properties"]["time_s"] == 300
    assert d["geometry"]["coordinates"][-1] == [9.06, 48.53]
    bad = client.post(
        "/api/route",
        json={"origin": [9.05, 48.52], "destination_id": "mensa:m1", "mode": "transit"},
    )
    assert bad.status_code == 422
