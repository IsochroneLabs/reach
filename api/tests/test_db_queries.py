"""SQL of `reach_api.db` against a disposable PostGIS as role `app_read` (marker `db`).

Publishes the tiny hand-made run of the pipeline's data-contract test
(`pipeline/tests/test_db_contract.py`, loaded by path) and runs every query of
`PostgresDatabase`. Needs `REACH_TEST_DATABASE_URL` (superuser URL), like the pipeline test.
"""

from __future__ import annotations

import importlib.util
import json
import os
import uuid
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import psycopg
import pytest
from psycopg import sql

from reach_api.db import PostgresDatabase
from reach_api.settings import DbPool

pytestmark = pytest.mark.db

REPO = Path(__file__).resolve().parents[2]
RUN_ID = "20260101T000000Z"
# Marktplatz Tübingen, ~50 km from the test run's urban boundary.
MARKT = (9.0568, 48.5204)
# Scored cell with a real Zensus grid id (lower-left corner in EPSG:3035) and its centre as
# origin, as `validate` writes them; added to the published run as superuser.
_REAL_CELL = """
INSERT INTO {schema}.cells (cell_id, population, district_id, geom, origin_geom)
SELECT 'CRS3035RES100mN' || n || 'E' || e, 7, NULL,
       ST_Transform(ST_MakeEnvelope(e, n, e + 100, n + 100, 3035), 25832),
       ST_Transform(ST_SetSRID(ST_MakePoint(e + 50, n + 50), 3035), 25832)
FROM (SELECT floor(ST_X(p) / 100)::bigint * 100 AS e, floor(ST_Y(p) / 100)::bigint * 100 AS n
      FROM (SELECT ST_Transform(ST_SetSRID(ST_MakePoint(9.0568, 48.5204), 4326), 3035) AS p) q
     ) g
"""


def _contract():
    path = REPO / "pipeline" / "tests" / "test_db_contract.py"
    spec = importlib.util.spec_from_file_location("pipeline_db_contract", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def db_url() -> Iterator[str]:
    from reach_pipeline import db

    admin = os.environ.get("REACH_TEST_DATABASE_URL")
    if not admin:
        pytest.fail("set REACH_TEST_DATABASE_URL to a superuser URL of a disposable PostGIS")
    contract = _contract()
    name = f"reach_test_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    url = psycopg.conninfo.make_conninfo(admin, dbname=name)
    try:
        with psycopg.connect(url, autocommit=True) as conn:
            db.migrate(conn, contract.SQL_DIR, {})
        contract._publish(url, RUN_ID)
        with psycopg.connect(url, autocommit=True) as conn:
            conn.execute(_REAL_CELL.format(schema=f"run_{RUN_ID.lower()}"))
        yield url
    finally:
        with psycopg.connect(admin, autocommit=True) as conn:
            conn.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name))
            )


@pytest.fixture
async def pg(db_url: str) -> AsyncIterator[PostgresDatabase]:
    # Superuser connection acting as app_read, so only app_read's privileges apply.
    dsn = psycopg.conninfo.make_conninfo(db_url, options="-c role=app_read")
    database = PostgresDatabase(dsn, DbPool(min_size=1, max_size=2))
    await database.open()
    try:
        yield database
    finally:
        await database.close()


async def test_run_meta_profiles(pg: PostgresDatabase) -> None:
    assert await pg.run_id() == RUN_ID
    meta = await pg.meta(RUN_ID)
    assert meta["run"]["status"] == "published"
    assert {c["status"] for c in meta["checks"]} == {"ok", "warn"}
    profiles = await pg.profiles()
    assert profiles["walk"].costing_options == {"walking_speed": 3.39}
    assert await pg.categories() == {"grocery": 2, "pharmacy": 1}
    assert await pg.transit_profiles() == ["walk"]


async def test_cells_geojson(pg: PostgresDatabase) -> None:
    body = json.loads(await pg.cells_geojson(RUN_ID, "grocery", "walk"))
    assert body["type"] == "FeatureCollection" and len(body["features"]) == 4
    a = body["features"][0]
    assert a["id"] == "a" and a["geometry"]["type"] == "Polygon"
    # Class and deficit from the scores view: a has 0 groceries (k=2), 10 residents.
    assert a["properties"]["class"] == "lack" and a["properties"]["deficit"] == 10
    lon, lat = a["geometry"]["coordinates"][0][0]
    assert 8 < lon < 10 and 48 < lat < 49.5  # EPSG:4326 near 9° E, 48.75° N
    assert len(str(lon).split(".")[1]) <= 6
    transit = json.loads(await pg.cells_geojson(RUN_ID, "transit", "walk"))
    assert [f["properties"]["class"] for f in transit["features"]] == [
        "lack",
        "insufficient",
        "medium",
        "high",
    ]


async def test_districts(pg: PostgresDatabase) -> None:
    body = json.loads(await pg.districts_geojson(RUN_ID))
    assert {f["id"]: f["properties"]["residents"] for f in body["features"]} == {"d1": 30, "d2": 30}
    scores = await pg.district_scores("d1", "walk")
    grocery = next(s for s in scores["scores"] if s["category"] == "grocery")
    assert grocery["districts_ranked"] == 2 and grocery["rank_deficit"] in (1, 2)
    assert await pg.district_scores("zz", None) is None


async def test_locate_and_points(pg: PostgresDatabase) -> None:
    # Facility n1 at EPSG:25832 (500050, 5400050), inside the urban boundary (cells a, b).
    import pyproj

    to4326 = pyproj.Transformer.from_crs(25832, 4326, always_xy=True)
    lon, lat = to4326.transform(500_050, 5_400_050)
    loc = await pg.locate(lon, lat)
    assert loc.allowed and loc.cell_id.startswith("CRS3035RES100mN")
    assert not loc.scored  # test cells use ids a–d, not grid ids
    # The districts (200 m square from 500000/5400000) are the city: grid centre at 500004.
    assert loc.status == "unpopulated" and loc.in_city
    far = await pg.locate(lon + 0.05, lat)
    assert not far.allowed and far.status == "outside_city"
    # Click inside the city near its east edge, grid centre outside (x = 500203.9): accepted,
    # but never scored (O11).
    edge = await pg.locate(*to4326.transform(500_195, 5_400_100))
    assert edge.click_in_city and not edge.in_city
    assert edge.allowed and edge.status == "outside_city"


async def test_locate_scored_cell_outside_boundary(pg: PostgresDatabase) -> None:
    # K1 (architecture v0.14 rule 12): a scored cell far outside the urban boundary is allowed,
    # the grid id computed from the click matches cells.cell_id, origin = cells.origin_geom.
    loc = await pg.locate(*MARKT)
    assert loc.scored and loc.allowed and loc.population == 7 and loc.status == "scored"
    assert loc.cell_id == "CRS3035RES100mN2823400E4251200"  # id of the real Marktplatz cell
    assert loc.lon == pytest.approx(9.056138, abs=1e-6)
    assert loc.lat == pytest.approx(48.520463, abs=1e-6)
    # Clicks ~30 m from the centre (inside the cell) snap to the same cell and origin; ~80 m
    # east is the next cell.
    again = await pg.locate(loc.lon + 0.0003, loc.lat - 0.0002)
    assert (again.cell_id, again.x, again.y) == (loc.cell_id, loc.x, loc.y)
    east = await pg.locate(loc.lon + 0.0011, loc.lat)
    assert east.cell_id == "CRS3035RES100mN2823400E4251300" and not east.scored
    near = await pg.facility_points_near(500_050, 5_400_050, 50)
    assert [(p["facility_id"], p["category"]) for p in near] == [("n1", "grocery")]
    facility = await pg.facility("n1")
    assert facility["categories"] == ["grocery"] and len(facility["points"]) == 1
    cells = await pg.cells_near([(500_050, 5_400_050)], 60)
    assert [c["cell_id"] for c in cells] == ["a"]
    assert await pg.residents_by_class(["a", "b"], "grocery", "walk") == {
        "lack": 10,
        "insufficient": 20,
    }
    scores, transit = await pg.cell_values("c", "walk")
    assert {s["category"]: s["class"] for s in scores} == {
        "grocery": "sufficient",
        "pharmacy": "sufficient",
    }
    assert transit["class"] == "medium"


async def test_nearest_facility_points(pg: PostgresDatabase) -> None:
    # one facility in the run: found at any distance, one row with its nearest routing point
    rows = await pg.nearest_facility_points(510_000, 5_410_000, "grocery", [], 8)
    assert [(r["facility_id"], r["point_id"], r["category"]) for r in rows] == [
        ("n1", 0, "grocery")
    ]
    assert 8 < rows[0]["lon"] < 10 and 48 < rows[0]["lat"] < 49.5
    # already counted facilities are left out; other categories have no facility
    assert await pg.nearest_facility_points(510_000, 5_410_000, "grocery", ["n1"], 8) == []
    assert await pg.nearest_facility_points(510_000, 5_410_000, "pharmacy", [], 8) == []
    assert await pg.nearest_facility_points(510_000, 5_410_000, "grocery", [], 1) == rows


async def test_facilities_with_tags_and_links(pg: PostgresDatabase) -> None:
    body = json.loads(await pg.facilities_geojson(RUN_ID, "grocery", False))
    assert body["category"] == "grocery"
    (feature,) = body["features"]
    assert feature["geometry"]["type"] == "Point"
    assert feature["properties"] == {
        "kind": "facility",
        "facility_id": "n1",
        "name": "Shop",
        "category": "grocery",
        "tags": {"opening_hours": "Mo-Fr 08:00-18:00"},
        "osm_url": "https://www.openstreetmap.org/node/1",
    }
    # a point facility has neither outline nor access points
    with_area = json.loads(await pg.facilities_geojson(RUN_ID, "grocery", True))
    assert [f["properties"]["kind"] for f in with_area["features"]] == ["facility"]
    assert json.loads(await pg.facilities_geojson(RUN_ID, "pharmacy", True))["features"] == []
    # the lists of the live endpoints carry the same tags and link
    rows = await pg.nearest_facility_points(510_000, 5_410_000, "grocery", [], 8)
    assert rows[0]["tags"] == {"opening_hours": "Mo-Fr 08:00-18:00"}
    assert rows[0]["osm_url"].endswith("/node/1")
    assert (await pg.facility("n1"))["tags"]["opening_hours"] == "Mo-Fr 08:00-18:00"


async def test_reachable_lists_published_facilities(pg: PostgresDatabase) -> None:
    rows = await pg.reachable("b", "walk", 500_150, 5_400_050)
    assert [(r["facility_id"], r["category"], r["time_s"]) for r in rows] == [
        ("n1", "grocery", 270)
    ]
    assert 8 < rows[0]["lon"] < 10 and 48 < rows[0]["lat"] < 49.5
    assert await pg.reachable("a", "walk", 500_050, 5_400_050) == []  # nothing within budget


async def test_recommendations(pg: PostgresDatabase) -> None:
    body = json.loads(await pg.recommendations_geojson(RUN_ID, None, None))
    assert body["available"] is True and len(body["features"]) == 1
    f = body["features"][0]
    assert f["id"] == "walk/pharmacy/1" and f["geometry"]["type"] == "Polygon"
    assert f["properties"]["population_gain"] == 20 and 8 < f["properties"]["point"][0] < 10
    assert f["properties"]["district_name"] == "One"  # zone of cell a lies in district d1
    empty = json.loads(await pg.recommendations_geojson(RUN_ID, "grocery", "walk"))
    assert empty["features"] == []
    r = await pg.recommendation("CRS3035RES100mN1E1", "pharmacy", "walk")
    assert r["cell_ids"] == ["a", "b"] and r["residents"] == 30 and r["rank"] == 1
    assert await pg.recommendation("CRS3035RES100mN1E1", "grocery", "walk") is None
