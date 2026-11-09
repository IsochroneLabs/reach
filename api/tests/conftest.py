"""Fixtures of the API tests: a fake database and Valhalla mocked with recorded responses.

`fixtures/valhalla/marktplatz_walking_339.json` holds real Valhalla 3.9.1 answers recorded once
on the Tübingen tiles (P5): origin of the Marktplatz cell, four grocery routing points (two
beyond the 15-minute budget), three nearby cells; the expansion answer is cut to 25 edges.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from reach_api.db import Location, Profile
from reach_api.deps import Deps
from reach_api.main import create_app
from reach_api.settings import load_config
from reach_api.valhalla import ValhallaClient

REPO = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).parent / "fixtures"
VALHALLA = "http://valhalla.test"
RUN_ID = "20261105T184022Z"
CELL = "CRS3035RES100mN2823400E4251200"


def recorded() -> dict[str, Any]:
    return json.loads((FIXTURES / "valhalla" / "marktplatz_walking_339.json").read_text())


def osm_url(facility_id: str) -> str:
    kind = {"n": "node", "w": "way", "r": "relation"}[facility_id[0]]
    return f"https://www.openstreetmap.org/{kind}/{facility_id[1:]}"


# informative tags of two recorded facilities (the others have none)
TAGS = {
    "n2978948434": {"opening_hours": "Mo-Sa 07:00-20:00", "wheelchair": "yes"},
    "n5183783736": {"addr:street": "Neckargasse", "addr:housenumber": "5"},
}


class FakeDatabase:
    """`Database` answering from the recorded fixture; `calls` lists the methods used."""

    def __init__(self, rec: dict[str, Any]) -> None:
        self.rec = rec
        self.cell = CELL
        self.calls: list[str] = []
        self.run: str | None = RUN_ID
        # cell centre / clicked point inside the city boundary (status and rule 12)
        self.in_city = True
        self.click_in_city = True
        self.recommendations: list[dict[str, Any]] | None = None
        self.scored = True
        # published reachable facilities (the two recorded ones within 900 s), cut to the first n
        self.reachable_n = 2
        # categories of the recorded facilities for `nearest_facility_points`
        self.facility_categories = {"n13105232458": "pharmacy", "w396807347": "pharmacy"}
        self.scores = [
            {
                "category": "grocery",
                "count": 2,
                "nearest_min": 2.43,
                "class": "sufficient",
                "deficit": 0.0,
            },
            {
                "category": "pharmacy",
                "count": 0,
                "nearest_min": None,
                "class": "lack",
                "deficit": 163.0,
            },
        ]

    async def run_id(self) -> str | None:
        self.calls.append("run_id")
        return self.run

    async def meta(self, run_id: str) -> dict[str, Any]:
        return {
            "run": {"run_id": run_id, "status": "published", "reference_weekday": "2026-11-10"},
            "data_sources": [{"source": "osm", "licence": "ODbL 1.0"}],
            "checks": [
                {"check": "crs", "stage": "validate", "status": "ok", "value": None, "message": ""},
                {
                    "check": "monotonic",
                    "stage": "validate_results",
                    "status": "warn",
                    "value": 0.003,
                    "message": "6 of 1699 cells",
                },
            ],
            "thresholds": [
                {"category": "grocery", "k": 2, "class": None, "lower": None, "upper": None},
                {"category": "transit", "k": None, "class": "lack", "lower": 0, "upper": 0},
            ],
        }

    async def profiles(self) -> dict[str, Profile]:
        return {
            "walking_339": Profile(
                "walking_339", "pedestrian", {"walking_speed": 3.39}, 3.39, 15.0
            ),
            "cycling_15": Profile(
                "cycling_15",
                "bicycle",
                {"bicycle_type": "Hybrid", "cycling_speed": 15.0},
                15.0,
                15.0,
            ),
        }

    async def categories(self) -> dict[str, int]:
        return {"grocery": 2, "pharmacy": 1}

    async def transit_profiles(self) -> list[str]:
        return ["walking_339"]

    async def cells_geojson(self, run_id: str, category: str, profile_id: str) -> str:
        self.calls.append("cells_geojson")
        feature = {
            "type": "Feature",
            "id": CELL,
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[9.05, 48.52], [9.051, 48.52], [9.051, 48.521], [9.05, 48.52]]],
            },
            "properties": {"cell_id": CELL, "count": 2, "class": "sufficient", "deficit": 0.0},
        }
        return json.dumps({"type": "FeatureCollection", "run_id": run_id, "features": [feature]})

    async def districts_geojson(self, run_id: str) -> str:
        return json.dumps({"type": "FeatureCollection", "run_id": run_id, "features": []})

    async def district_scores(self, district_id: str, profile_id: str | None):
        if district_id != "r1":
            return None
        return {"district_id": "r1", "name": "Altstadt", "admin_level": 11, "scores": []}

    async def locate(self, lon: float, lat: float) -> Location:
        self.calls.append("locate")
        lon0, lat0 = self.rec["origin"]
        return Location(
            cell_id=CELL
            if self.scored
            else "CRS3035RES100mN2823900E4251200"
            if self.in_city
            else "CRS3035RES100mN2822900E4249800",
            scored=self.scored,
            population=163 if self.scored else None,
            district_id="r1" if self.scored else None,
            lon=lon0,
            lat=lat0,
            x=503_000.0,
            y=5_374_000.0,
            in_city=self.in_city,
            click_in_city=self.click_in_city,
        )

    async def cell_values(self, cell_id: str, profile_id: str):
        return self.scores, {
            "departures": 4454,
            "stops_count": 12,
            "nearest_stop_min": 4.18,
            "class": "high",
        }

    async def reachable(self, cell_id: str, profile_id: str, x: float, y: float):
        """Published reachable facilities: the two grocery points within 900 s of the
        recording (145 s and 225 s by the recorded matrix)."""
        self.calls.append("reachable")
        near = self.rec["points"][2:]
        return [
            {
                "facility_id": p["facility_id"],
                "category": p["category"],
                "name": p["name"],
                "time_s": t,
                "lon": p["lon"],
                "lat": p["lat"],
                "tags": TAGS.get(p["facility_id"], {}),
                "osm_url": osm_url(p["facility_id"]),
            }
            for p, t in list(zip(near, (145, 225), strict=True))[: self.reachable_n]
        ]

    async def facility_points_near(self, x: float, y: float, reach_m: float):
        self.calls.append("facility_points_near")
        return [
            {k: p[k] for k in ("facility_id", "point_id", "category", "name", "lon", "lat")}
            | {"tags": TAGS.get(p["facility_id"], {}), "osm_url": osm_url(p["facility_id"])}
            for p in self.rec["points"]
        ]

    async def nearest_facility_points(
        self, x: float, y: float, category: str, exclude_ids: list[str], limit: int
    ):
        """Recorded facilities (two of them as pharmacies, to have a category in "lack") that
        are not excluded, in recorded order."""
        self.calls.append("nearest_facility_points")
        return [
            {k: p[k] for k in ("facility_id", "point_id", "category", "name", "lon", "lat")}
            | {
                "category": self.facility_categories.get(p["facility_id"], p["category"]),
                "tags": TAGS.get(p["facility_id"], {}),
                "osm_url": osm_url(p["facility_id"]),
            }
            for p in self.rec["points"]
            if p["facility_id"] not in exclude_ids
            and self.facility_categories.get(p["facility_id"], p["category"]) == category
        ][:limit]

    async def facility(self, facility_id: str):
        p = self.rec["points"][-1]
        if facility_id != p["facility_id"]:
            return None
        return {
            "facility_id": p["facility_id"],
            "name": p["name"],
            "lon": p["lon"],
            "lat": p["lat"],
            "categories": [p["category"]],
            "tags": TAGS.get(p["facility_id"], {}),
            "osm_url": osm_url(p["facility_id"]),
            "points": [{"x": p["x"], "y": p["y"], "lon": p["lon"], "lat": p["lat"]}],
        }

    async def facilities_geojson(self, run_id: str, category: str, with_area: bool) -> str:
        self.calls.append("facilities_geojson")
        feats = [
            {
                "type": "Feature",
                "id": p["facility_id"],
                "geometry": {"type": "Point", "coordinates": [p["lon"], p["lat"]]},
                "properties": {
                    "kind": "facility",
                    "facility_id": p["facility_id"],
                    "name": p["name"],
                    "category": p["category"],
                    "tags": TAGS.get(p["facility_id"], {}),
                    "osm_url": osm_url(p["facility_id"]),
                },
            }
            for p in self.rec["points"]
            if p["category"] == category
        ]
        if with_area:
            ring = [[9.0, 48.5], [9.001, 48.5], [9.001, 48.501], [9.0, 48.5]]
            feats.append(
                {
                    "type": "Feature",
                    "id": "w1/area",
                    "geometry": {"type": "MultiPolygon", "coordinates": [[ring]]},
                    "properties": {"kind": "area", "facility_id": "w1", "category": category},
                }
            )
        body = {"type": "FeatureCollection", "run_id": run_id, "category": category}
        return json.dumps({**body, "features": feats})

    async def cells_near(self, points_xy, reach_m: float):
        return [
            {
                "cell_id": c["cell_id"],
                "population": c["population"],
                "lon": c["lon"],
                "lat": c["lat"],
            }
            for c in self.rec["cells"]
        ]

    async def residents_by_class(self, cell_ids, category: str, profile_id: str):
        return {"sufficient": 400}

    async def recommendations_geojson(self, run_id: str, category, profile_id):
        self.calls.append("recommendations_geojson")
        if self.recommendations is None:  # run published before the recommender
            return None
        features = [
            f
            for f in self.recommendations
            if category in (None, f["properties"]["category"])
            and profile_id in (None, f["properties"]["profile_id"])
        ]
        body = {"type": "FeatureCollection", "run_id": run_id, "available": True}
        return json.dumps({**body, "features": features})

    async def recommendation(self, candidate_id: str, category: str, profile_id: str):
        for f in self.recommendations or []:
            props = f["properties"]
            if (props["candidate_id"], props["category"], props["profile_id"]) == (
                candidate_id,
                category,
                profile_id,
            ):
                cells = [c["cell_id"] for c in self.rec["cells"]]
                lon, lat = props["point"]
                return {**props, "lon": lon, "lat": lat, "cell_ids": cells, "residents": 812}
        return None


def _make_deps(db: FakeDatabase, **api: Any) -> Deps:
    config = load_config(REPO / "config" / "config.yaml")
    if api:
        config = config.model_copy(update={"api": config.api.model_copy(update=api)})
    pairs = config.valhalla.max_matrix_pairs
    valhalla = ValhallaClient(VALHALLA, config.api.valhalla, pairs)
    live_matrix = ValhallaClient(VALHALLA, config.api.live_matrix, pairs)
    return Deps(config=config, db=db, valhalla=valhalla, live_matrix=live_matrix)


@pytest.fixture(autouse=True)
def _no_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unit tests never resolve names: "localhost" is 127.0.0.1, every other host is unknown."""

    def fake(host: str, port: object) -> list:
        if host == "localhost":
            return [(None, None, None, None, ("127.0.0.1", 0))]
        raise OSError(f"{host} does not resolve in tests")

    monkeypatch.setattr("reach_api.ratelimit.getaddrinfo", fake)


@pytest.fixture
def make_deps() -> Callable[..., Deps]:
    """Factory: deps on a fake database; keyword arguments replace fields of `api`."""
    return _make_deps


@pytest.fixture
def rec() -> dict[str, Any]:
    return recorded()


@pytest.fixture
def db(rec: dict[str, Any]) -> FakeDatabase:
    return FakeDatabase(rec)


@pytest.fixture
def valhalla(rec: dict[str, Any]) -> Iterator[respx.MockRouter]:
    """Valhalla answering with the recorded responses (reverse isochrone for `reverse: true`,
    the catchment matrix for several sources)."""

    def isochrone(request: httpx.Request) -> httpx.Response:
        reverse = json.loads(request.content).get("reverse")
        return httpx.Response(200, json=rec["isochrone_reverse" if reverse else "isochrone"])

    recorded_s = dict(
        zip(
            [(round(p["lon"], 7), round(p["lat"], 7)) for p in rec["points"]],
            rec["matrix"]["sources_to_targets"]["durations"][0],
            strict=True,
        )
    )

    def matrix(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if len(body["sources"]) > 1:
            return httpx.Response(200, json=rec["matrix_catchment"])
        # one source: the recorded time of every requested facility point (any subset, any order)
        durations = [[recorded_s[(t["lon"], t["lat"])] for t in body["targets"]]]
        return httpx.Response(
            200, json={**rec["matrix"], "sources_to_targets": {"durations": durations}}
        )

    with respx.mock(base_url=VALHALLA, assert_all_called=False) as mock:
        mock.post("/isochrone", name="isochrone").mock(side_effect=isochrone)
        mock.post("/sources_to_targets", name="matrix").mock(side_effect=matrix)
        mock.post("/route", name="route").mock(return_value=httpx.Response(200, json=rec["route"]))
        mock.post("/expansion", name="expansion").mock(
            return_value=httpx.Response(200, json=rec["expansion"])
        )
        yield mock


@pytest.fixture
def client(db: FakeDatabase, valhalla: respx.MockRouter) -> Iterator[TestClient]:
    with TestClient(create_app(_make_deps(db))) as c:
        yield c
