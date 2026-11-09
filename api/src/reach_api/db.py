"""Read-only access to the `current` views and `meta` as role `app_read` (arch. §8, rule 6).

Geometries are stored in EPSG:25832 and transformed to EPSG:4326 in SQL (`ST_Transform`) at this
boundary only; GeoJSON bodies are built entirely in PostGIS with 6 decimals (~0.1 m). Classes,
deficits and district shares come from the views (`scores`, `transit_scores`,
`district_scores`); nothing here derives them. `Database` is the interface the routes use; tests
replace it with a fake.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from reach_api.settings import DbPool

# 6 decimals in GeoJSON coordinates (~0.1 m).
GEOJSON_DECIMALS = 6
TRANSIT = "transit"  # `thresholds.category` of the transit classes (data contract)


@dataclass(frozen=True)
class Profile:
    profile_id: str
    costing: str
    costing_options: dict[str, Any]
    speed_kmh: float
    time_budget_min: float


@dataclass(frozen=True)
class Location:
    """The 100 m Zensus grid cell under a point (EPSG:3035 id), scored or not."""

    cell_id: str
    scored: bool
    population: int | None
    district_id: str | None
    lon: float  # origin = cell centre, EPSG:4326
    lat: float
    x: float  # origin, EPSG:25832
    y: float
    in_city: bool  # cell centre inside the city boundary (union of the districts)
    click_in_city: bool  # clicked point inside the city boundary

    @property
    def status(self) -> str:
        """`scored` (row in `cells`), `unpopulated` (centre in the city, no residents in the
        Zensus grid) or `outside_city` (centre outside the city boundary: never scored, O11)."""
        if self.scored:
            return "scored"
        return "unpopulated" if self.in_city else "outside_city"

    @property
    def allowed(self) -> bool:
        """Rule 12: a scored cell, or a cell whose centre or clicked point lies in the city."""
        return self.scored or self.in_city or self.click_in_city


class Database(Protocol):
    async def run_id(self) -> str | None: ...
    async def meta(self, run_id: str) -> dict[str, Any]: ...
    async def profiles(self) -> dict[str, Profile]: ...
    async def categories(self) -> dict[str, int]: ...
    async def transit_profiles(self) -> list[str]: ...
    async def cells_geojson(self, run_id: str, category: str, profile_id: str) -> str: ...
    async def districts_geojson(self, run_id: str) -> str: ...
    async def district_scores(
        self, district_id: str, profile_id: str | None
    ) -> dict[str, Any] | None: ...
    async def locate(self, lon: float, lat: float) -> Location: ...
    async def cell_values(
        self, cell_id: str, profile_id: str
    ) -> tuple[list[dict[str, Any]], dict[str, Any] | None]: ...
    async def reachable(
        self, cell_id: str, profile_id: str, x: float, y: float
    ) -> list[dict[str, Any]]: ...
    async def facility_points_near(
        self, x: float, y: float, reach_m: float
    ) -> list[dict[str, Any]]: ...
    async def facility(self, facility_id: str) -> dict[str, Any] | None: ...
    async def nearest_facility_points(
        self, x: float, y: float, category: str, exclude_ids: list[str], limit: int
    ) -> list[dict[str, Any]]: ...
    async def cells_near(
        self, points_xy: list[tuple[float, float]], reach_m: float
    ) -> list[dict[str, Any]]: ...
    async def residents_by_class(
        self, cell_ids: list[str], category: str, profile_id: str
    ) -> dict[str, int]: ...
    async def recommendations_geojson(
        self, run_id: str, category: str | None, profile_id: str | None
    ) -> str | None: ...
    async def recommendation(
        self, candidate_id: str, category: str, profile_id: str
    ) -> dict[str, Any] | None: ...


# Run schema that `current.cells` reads from (same lookup as reach_pipeline.db.current_schema),
# mapped back to its run id.
_RUN_ID = """
SELECT r.run_id FROM meta.runs r
WHERE 'run_' || lower(r.run_id) = (
    SELECT DISTINCT tn.nspname FROM pg_rewrite rw
    JOIN pg_class v ON v.oid = rw.ev_class
    JOIN pg_namespace vn ON vn.oid = v.relnamespace
    JOIN pg_depend d ON d.objid = rw.oid AND d.classid = 'pg_rewrite'::regclass
    JOIN pg_class t ON t.oid = d.refobjid AND t.oid <> v.oid
    JOIN pg_namespace tn ON tn.oid = t.relnamespace
    WHERE vn.nspname = 'current' AND v.relname = 'cells')
"""

_GEOM = f"ST_AsGeoJSON(ST_Transform({{}}, 4326), {GEOJSON_DECIMALS})::json"

_CELLS = f"""
SELECT json_build_object(
  'type', 'FeatureCollection',
  'run_id', %(run_id)s::text, 'category', %(category)s::text, 'profile_id', %(profile_id)s::text,
  'features', coalesce(json_agg(json_build_object(
    'type', 'Feature', 'id', c.cell_id,
    'geometry', {_GEOM.format("c.geom")},
    'properties', json_build_object(
      'cell_id', c.cell_id, 'population', c.population, 'district_id', c.district_id,
      'count', s.count, 'nearest_min', s.nearest_min, 'class', s.class, 'deficit', s.deficit)
  ) ORDER BY c.cell_id), '[]'::json))::text AS body
FROM current.cells c
JOIN current.scores s USING (cell_id)
WHERE s.category = %(category)s AND s.profile_id = %(profile_id)s
"""

_TRANSIT_CELLS = f"""
SELECT json_build_object(
  'type', 'FeatureCollection',
  'run_id', %(run_id)s::text, 'category', %(category)s::text, 'profile_id', %(profile_id)s::text,
  'features', coalesce(json_agg(json_build_object(
    'type', 'Feature', 'id', c.cell_id,
    'geometry', {_GEOM.format("c.geom")},
    'properties', json_build_object(
      'cell_id', c.cell_id, 'population', c.population, 'district_id', c.district_id,
      'departures', ts.departures, 'stops_count', ts.stops_count,
      'nearest_stop_min', ts.nearest_stop_min, 'class', sc.class)
  ) ORDER BY c.cell_id), '[]'::json))::text AS body
FROM current.cells c
JOIN current.transit_supply ts USING (cell_id)
JOIN current.transit_scores sc ON sc.cell_id = ts.cell_id AND sc.profile_id = ts.profile_id
WHERE ts.profile_id = %(profile_id)s
"""

_DISTRICTS = f"""
SELECT json_build_object(
  'type', 'FeatureCollection', 'run_id', %(run_id)s::text,
  'features', coalesce(json_agg(json_build_object(
    'type', 'Feature', 'id', d.district_id,
    'geometry', {_GEOM.format("d.geom")},
    'properties', json_build_object(
      'district_id', d.district_id, 'name', d.name, 'admin_level', d.admin_level,
      'residents', coalesce(p.residents, 0), 'cells', coalesce(p.cells, 0))
  ) ORDER BY d.name), '[]'::json))::text AS body
FROM current.districts d
LEFT JOIN (SELECT district_id, sum(population)::bigint AS residents, count(*) AS cells
           FROM current.cells GROUP BY district_id) p USING (district_id)
"""

# Ranks over all districts per category × profile (methodology §4: by total deficit and by share
# of residents lacking access); ordering only, the values come from district_scores. Shares are
# null for districts without residents; they rank last.
_DISTRICT_SCORES = """
SELECT category, profile_id, share_lack, share_insufficient, share_sufficient, deficit_sum,
       residents_lack, rank_deficit, rank_share_lack, districts_ranked
FROM (SELECT d.*,
             rank() OVER w_deficit AS rank_deficit,
             rank() OVER w_lack AS rank_share_lack,
             count(*) OVER (PARTITION BY category, profile_id) AS districts_ranked
      FROM current.district_scores d
      WINDOW w_deficit AS (PARTITION BY category, profile_id ORDER BY deficit_sum DESC NULLS LAST),
             w_lack AS (PARTITION BY category, profile_id ORDER BY share_lack DESC NULLS LAST)) r
WHERE district_id = %(district_id)s
  AND (%(profile_id)s::text IS NULL OR profile_id = %(profile_id)s::text)
ORDER BY profile_id, category
"""

# The 100 m grid cell under the point: EPSG:3035 lower-left corner gives the Zensus id
# (CRS3035RES100mN<north>E<east>), its centre is the origin (cells.origin_geom for scored cells).
# The districts cover the city (up to `districts.coverage_tolerance_pct`), so "inside a district"
# is "inside the city"; `in_city` is the cell centre, `click_in_city` the clicked point.
_LOCATE = """
WITH click AS (
  SELECT ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326) AS g4
), grid AS (
  SELECT g4, ST_Transform(g4, 25832) AS g,
         floor(ST_X(ST_Transform(g4, 3035)) / 100)::bigint * 100 AS e,
         floor(ST_Y(ST_Transform(g4, 3035)) / 100)::bigint * 100 AS n
  FROM click
), cell AS (
  SELECT 'CRS3035RES100mN' || n || 'E' || e AS cell_id, g,
         ST_Transform(ST_SetSRID(ST_MakePoint(e + 50, n + 50), 3035), 25832) AS centre
  FROM grid
)
SELECT cell.cell_id, c.cell_id IS NOT NULL AS scored, c.population, c.district_id,
       ST_X(ST_Transform(o.origin, 4326)) AS lon, ST_Y(ST_Transform(o.origin, 4326)) AS lat,
       ST_X(o.origin) AS x, ST_Y(o.origin) AS y,
       EXISTS (SELECT 1 FROM current.districts d WHERE ST_Covers(d.geom, cell.centre))
         AS in_city,
       EXISTS (SELECT 1 FROM current.districts d WHERE ST_Covers(d.geom, cell.g))
         AS click_in_city
FROM cell
LEFT JOIN current.cells c ON c.cell_id = cell.cell_id
CROSS JOIN LATERAL (SELECT coalesce(c.origin_geom, cell.centre) AS origin) o
"""

# Facilities `count` found within the budget of a cell and profile, one row per category of the
# facility; the routing target is the facility's point nearest to the origin by straight line
# (only used to draw the route; the time is the matrix time of the run).
_REACHABLE = """
SELECT r.facility_id, f.category, f.name, r.time_s,
       ST_X(ST_Transform(p.geom, 4326)) AS lon, ST_Y(ST_Transform(p.geom, 4326)) AS lat
FROM current.reachable r
JOIN current.facilities f USING (facility_id)
CROSS JOIN LATERAL (
  SELECT fp.geom FROM current.facility_points fp
  WHERE fp.facility_id = r.facility_id
  ORDER BY fp.geom <-> ST_SetSRID(ST_MakePoint(%(x)s, %(y)s), 25832), fp.point_id
  LIMIT 1) p
WHERE r.cell_id = %(cell_id)s AND r.profile_id = %(profile_id)s
ORDER BY f.category, r.time_s, r.facility_id
"""

# Facility routing points within the straight-line prefilter reach of an origin: the same
# targets the count stage sends (facility_points joined to facilities by facility_id, one row
# per point and category, O20).
_POINTS_NEAR = """
SELECT fp.facility_id, fp.point_id, f.category, f.name,
       ST_X(ST_Transform(fp.geom, 4326)) AS lon, ST_Y(ST_Transform(fp.geom, 4326)) AS lat
FROM current.facility_points fp
JOIN current.facilities f USING (facility_id)
WHERE ST_DWithin(fp.geom, ST_SetSRID(ST_MakePoint(%(x)s, %(y)s), 25832), %(reach)s)
ORDER BY fp.facility_id, fp.point_id, f.category
"""

# The `limit` nearest facilities of a category by straight line (distance to their nearest routing
# point), without the excluded ones; one row per facility with that point. Used to find the next
# facility beyond the budget (W4), so no reach limit applies. Every facility has at least one
# row in `facility_points` (`count` only sees facilities through them), so the join loses none.
_NEAREST_POINTS = """
SELECT f.facility_id, p.point_id, f.category, f.name,
       ST_X(ST_Transform(p.geom, 4326)) AS lon, ST_Y(ST_Transform(p.geom, 4326)) AS lat
FROM current.facilities f
CROSS JOIN LATERAL (
  SELECT fp.point_id, fp.geom FROM current.facility_points fp
  WHERE fp.facility_id = f.facility_id
  ORDER BY fp.geom <-> ST_SetSRID(ST_MakePoint(%(x)s, %(y)s), 25832), fp.point_id
  LIMIT 1) p
WHERE f.category = %(category)s AND NOT (f.facility_id = ANY(%(exclude)s::text[]))
ORDER BY p.geom <-> ST_SetSRID(ST_MakePoint(%(x)s, %(y)s), 25832), f.facility_id
LIMIT %(limit)s
"""

_FACILITY = """
SELECT f.facility_id, f.name,
       ST_X(ST_Transform(f.geom, 4326)) AS lon, ST_Y(ST_Transform(f.geom, 4326)) AS lat,
       (SELECT array_agg(c.category ORDER BY c.category) FROM current.facilities c
        WHERE c.facility_id = f.facility_id) AS categories,
       (SELECT json_agg(json_build_object(
                 'x', ST_X(fp.geom), 'y', ST_Y(fp.geom),
                 'lon', ST_X(ST_Transform(fp.geom, 4326)),
                 'lat', ST_Y(ST_Transform(fp.geom, 4326))) ORDER BY fp.point_id)
        FROM current.facility_points fp WHERE fp.facility_id = f.facility_id) AS points
FROM current.facilities f
WHERE f.facility_id = %(facility_id)s
ORDER BY f.category
LIMIT 1
"""

# Scored cells whose origin lies within the prefilter reach of any of the points.
_CELLS_NEAR = """
SELECT c.cell_id, c.population,
       ST_X(ST_Transform(c.origin_geom, 4326)) AS lon,
       ST_Y(ST_Transform(c.origin_geom, 4326)) AS lat
FROM current.cells c
WHERE EXISTS (
  SELECT 1 FROM unnest(%(xs)s::float8[], %(ys)s::float8[]) AS p(x, y)
  WHERE ST_DWithin(c.origin_geom, ST_SetSRID(ST_MakePoint(p.x, p.y), 25832), %(reach)s))
ORDER BY c.cell_id
"""


# Recommended zones (recommend stage, methodology §5) as GeoJSON polygons, best rank first;
# `point` is the zone centre, the target of its catchment; the district is the one containing
# it (null outside every district). Filters are optional.
_RECOMMENDATIONS = f"""
SELECT json_build_object(
  'type', 'FeatureCollection', 'run_id', %(run_id)s::text, 'available', true,
  'features', coalesce(json_agg(json_build_object(
    'type', 'Feature', 'id', r.profile_id || '/' || r.category || '/' || r.rank,
    'geometry', {_GEOM.format("r.geom")},
    'properties', json_build_object(
      'category', r.category, 'profile_id', r.profile_id, 'rank', r.rank,
      'candidate_id', r.candidate_id, 'population_gain', r.population_gain,
      'residents_gaining_access', r.residents_gaining_access,
      'residents_to_sufficient', r.residents_to_sufficient,
      'catchment_residents', r.catchment_residents, 'catchment_cells', r.catchment_cells,
      'district_id', d.district_id, 'district_name', d.name,
      'point', json_build_array(round(ST_X(ST_Transform(r.point_geom, 4326))::numeric, 6),
                                round(ST_Y(ST_Transform(r.point_geom, 4326))::numeric, 6)))
  ) ORDER BY r.profile_id, r.category, r.rank), '[]'::json))::text AS body
FROM current.recommendations r
LEFT JOIN LATERAL (SELECT district_id, name FROM current.districts
                   WHERE ST_Contains(geom, r.point_geom) ORDER BY district_id LIMIT 1) d ON true
WHERE (%(category)s::text IS NULL OR r.category = %(category)s::text)
  AND (%(profile_id)s::text IS NULL OR r.profile_id = %(profile_id)s::text)
"""

# One recommendation with the cells of its stored catchment (recommendation_catchments).
_RECOMMENDATION = """
SELECT r.category, r.profile_id, r.rank, r.candidate_id, r.population_gain,
       r.residents_gaining_access, r.residents_to_sufficient,
       ST_X(ST_Transform(r.point_geom, 4326)) AS lon,
       ST_Y(ST_Transform(r.point_geom, 4326)) AS lat,
       coalesce((SELECT array_agg(rc.cell_id ORDER BY rc.cell_id)
                 FROM current.recommendation_catchments rc
                 WHERE rc.candidate_id = r.candidate_id AND rc.profile_id = r.profile_id),
                '{}') AS cell_ids,
       coalesce((SELECT sum(c.population)::bigint FROM current.recommendation_catchments rc
                 JOIN current.cells c USING (cell_id)
                 WHERE rc.candidate_id = r.candidate_id AND rc.profile_id = r.profile_id),
                0) AS residents
FROM current.recommendations r
WHERE r.candidate_id = %(candidate_id)s AND r.category = %(category)s
  AND r.profile_id = %(profile_id)s
"""


class PostgresDatabase:
    """`Database` on an async psycopg pool."""

    def __init__(self, dsn: str, pool: DbPool) -> None:
        self.pool = AsyncConnectionPool(
            dsn,
            min_size=pool.min_size,
            max_size=pool.max_size,
            open=False,
            kwargs={"autocommit": True, "row_factory": dict_row},
        )

    async def open(self) -> None:
        await self.pool.open()

    async def close(self) -> None:
        await self.pool.close()

    async def _all(self, query: str, params: dict[str, Any] | None = None) -> list[dict]:
        async with self.pool.connection() as conn:
            cur = await conn.execute(query, params)
            return await cur.fetchall()

    async def _one(self, query: str, params: dict[str, Any] | None = None) -> dict | None:
        rows = await self._all(query, params)
        return rows[0] if rows else None

    async def run_id(self) -> str | None:
        row = await self._one(_RUN_ID)
        return row["run_id"] if row else None

    async def meta(self, run_id: str) -> dict[str, Any]:
        run = await self._one(
            "SELECT run_id, started_at, finished_at, status, osm_snapshot, gtfs_valid_from, "
            "gtfs_valid_to, reference_weekday, config_hash FROM meta.runs WHERE run_id = %(r)s",
            {"r": run_id},
        )
        sources = await self._all(
            "SELECT source, url, retrieved_at, checksum, licence FROM meta.data_sources "
            "WHERE run_id = %(r)s ORDER BY source",
            {"r": run_id},
        )
        checks = await self._all(
            'SELECT "check", stage, status, value, message FROM current.validation_report '
            'ORDER BY stage, "check"'
        )
        thresholds = await self._all(
            "SELECT category, k, class, lower, upper FROM current.thresholds "
            "ORDER BY category, lower NULLS FIRST"
        )
        return {"run": run, "data_sources": sources, "checks": checks, "thresholds": thresholds}

    async def profiles(self) -> dict[str, Profile]:
        rows = await self._all(
            "SELECT profile_id, costing, costing_options, speed_kmh, time_budget_min "
            "FROM current.profiles ORDER BY profile_id"
        )
        return {r["profile_id"]: Profile(**r) for r in rows}

    async def categories(self) -> dict[str, int]:
        rows = await self._all(
            "SELECT category, k FROM current.thresholds WHERE class IS NULL ORDER BY category"
        )
        return {r["category"]: r["k"] for r in rows}

    async def transit_profiles(self) -> list[str]:
        rows = await self._all("SELECT DISTINCT profile_id FROM current.transit_supply")
        return [r["profile_id"] for r in rows]

    async def cells_geojson(self, run_id: str, category: str, profile_id: str) -> str:
        query = _TRANSIT_CELLS if category == TRANSIT else _CELLS
        params = {"run_id": run_id, "category": category, "profile_id": profile_id}
        row = await self._one(query, params)
        return row["body"]

    async def districts_geojson(self, run_id: str) -> str:
        row = await self._one(_DISTRICTS, {"run_id": run_id})
        return row["body"]

    async def district_scores(
        self, district_id: str, profile_id: str | None
    ) -> dict[str, Any] | None:
        district = await self._one(
            "SELECT district_id, name, admin_level FROM current.districts "
            "WHERE district_id = %(d)s",
            {"d": district_id},
        )
        if district is None:
            return None
        rows = await self._all(
            _DISTRICT_SCORES, {"district_id": district_id, "profile_id": profile_id}
        )
        return {**district, "scores": rows}

    async def locate(self, lon: float, lat: float) -> Location:
        row = await self._one(_LOCATE, {"lon": lon, "lat": lat})
        return Location(**row)

    async def cell_values(
        self, cell_id: str, profile_id: str
    ) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        params = {"c": cell_id, "p": profile_id}
        scores = await self._all(
            "SELECT category, count, nearest_min, class, deficit FROM current.scores "
            "WHERE cell_id = %(c)s AND profile_id = %(p)s ORDER BY category",
            params,
        )
        transit = await self._one(
            "SELECT ts.departures, ts.stops_count, ts.nearest_stop_min, sc.class "
            "FROM current.transit_supply ts JOIN current.transit_scores sc "
            "ON sc.cell_id = ts.cell_id AND sc.profile_id = ts.profile_id "
            "WHERE ts.cell_id = %(c)s AND ts.profile_id = %(p)s",
            params,
        )
        return scores, transit

    async def reachable(
        self, cell_id: str, profile_id: str, x: float, y: float
    ) -> list[dict[str, Any]]:
        params = {"cell_id": cell_id, "profile_id": profile_id, "x": x, "y": y}
        return await self._all(_REACHABLE, params)

    async def facility_points_near(
        self, x: float, y: float, reach_m: float
    ) -> list[dict[str, Any]]:
        return await self._all(_POINTS_NEAR, {"x": x, "y": y, "reach": reach_m})

    async def facility(self, facility_id: str) -> dict[str, Any] | None:
        return await self._one(_FACILITY, {"facility_id": facility_id})

    async def nearest_facility_points(
        self, x: float, y: float, category: str, exclude_ids: list[str], limit: int
    ) -> list[dict[str, Any]]:
        params = {"x": x, "y": y, "category": category, "exclude": exclude_ids, "limit": limit}
        return await self._all(_NEAREST_POINTS, params)

    async def cells_near(
        self, points_xy: list[tuple[float, float]], reach_m: float
    ) -> list[dict[str, Any]]:
        xs, ys = [p[0] for p in points_xy], [p[1] for p in points_xy]
        return await self._all(_CELLS_NEAR, {"xs": xs, "ys": ys, "reach": reach_m})

    async def residents_by_class(
        self, cell_ids: list[str], category: str, profile_id: str
    ) -> dict[str, int]:
        rows = await self._all(
            "SELECT s.class, sum(c.population)::bigint AS residents FROM current.scores s "
            "JOIN current.cells c USING (cell_id) WHERE s.cell_id = ANY(%(ids)s) "
            "AND s.category = %(cat)s AND s.profile_id = %(p)s GROUP BY s.class",
            {"ids": cell_ids, "cat": category, "p": profile_id},
        )
        return {r["class"]: r["residents"] for r in rows}

    async def _has_recommendations(self) -> bool:
        # Runs published before the recommender (P7) have no such view.
        row = await self._one("SELECT to_regclass('current.recommendations') IS NOT NULL AS ok")
        return bool(row and row["ok"])

    async def recommendations_geojson(
        self, run_id: str, category: str | None, profile_id: str | None
    ) -> str | None:
        """None if the current run has no recommendations table."""
        if not await self._has_recommendations():
            return None
        params = {"run_id": run_id, "category": category, "profile_id": profile_id}
        row = await self._one(_RECOMMENDATIONS, params)
        return row["body"]

    async def recommendation(
        self, candidate_id: str, category: str, profile_id: str
    ) -> dict[str, Any] | None:
        if not await self._has_recommendations():
            return None
        params = {"candidate_id": candidate_id, "category": category, "profile_id": profile_id}
        return await self._one(_RECOMMENDATION, params)
