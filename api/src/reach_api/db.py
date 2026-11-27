"""Read-only access to `current` and `meta` as role `app_read` (arch. §8, AGENTS.md rule 6).

Geometries are stored in EPSG:25832 and transformed to EPSG:4326 in SQL (`ST_Transform`) at this
boundary only. `Database` is the interface the routes use; tests replace it with a fake.
"""

from __future__ import annotations

from typing import Any, Protocol

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from reach_api.settings import DbPool

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


Q_CELLS = """
SELECT cell_id, district_id, populated,
       ST_X(ST_Transform(origin_geom, 4326)) AS lon, ST_Y(ST_Transform(origin_geom, 4326)) AS lat
FROM current.cells ORDER BY cell_id
"""
Q_DISTRICTS = "SELECT district_id, name FROM current.districts"
Q_TYPES = "SELECT * FROM current.destination_types"
Q_LABELS = """
SELECT destination_type, label_kind, label, count(*)::int AS destinations
FROM current.destination_labels WHERE offered
GROUP BY destination_type, label_kind, label ORDER BY destination_type, label_kind, label
"""
Q_LABEL_DESTINATIONS = """
SELECT destination_id, destination_type, label, name,
       ST_X(ST_Transform(geom, 4326)) AS lon, ST_Y(ST_Transform(geom, 4326)) AS lat
FROM current.destination_labels WHERE offered ORDER BY destination_id
"""
Q_SITES = """
SELECT site_id, name, default_share,
       ST_X(ST_Transform(geom, 4326)) AS lon, ST_Y(ST_Transform(geom, 4326)) AS lat
FROM current.campus_sites ORDER BY site_id
"""
Q_PROGRAMMES = "SELECT programme, label_en, label_de, sites, shares FROM current.programmes"
Q_DESTINATIONS = """
SELECT destination_id, destination_type, name FROM current.destinations
UNION ALL
SELECT destination_id, destination_type, name FROM current.destination_labels
"""
Q_TIMES = """
SELECT cell_id, destination_id, mode, time_s, departure FROM current.travel_times
WHERE time_s IS NOT NULL
"""
Q_WINDOWS = "SELECT * FROM current.trip_windows ORDER BY trip_window"
Q_SOURCES = """
SELECT s.source, s.retrieved_at::date AS date, r.gtfs_valid_to
FROM meta.data_sources s JOIN meta.runs r USING (run_id) WHERE s.run_id = %s ORDER BY s.source
"""
Q_BOUNDS = """
SELECT ST_XMin(e) AS w, ST_YMin(e) AS s, ST_XMax(e) AS e, ST_YMax(e) AS n
FROM (SELECT ST_Extent(ST_Transform(geom, 4326)) AS e FROM current.cells) x
"""
Q_CELL_TRIPS = """
SELECT t.destination_id, t.mode, t.trip_window, t.time_s, t.access_s, t.wait_s, t.in_vehicle_s,
       t.egress_s, t.transfers, t.first_stop, t.first_route, t.departure, t.walk_only
FROM current.travel_times t
WHERE t.cell_id = %s AND t.destination_id = ANY(%s)
ORDER BY t.destination_id, t.mode
"""
# F4.5 point routing: nearest k in EPSG:25832 (GiST <->), never distances in degrees.
Q_NEAREST_TYPE = """
WITH p AS (SELECT ST_Transform(ST_SetSRID(ST_MakePoint(%s, %s), 4326), 25832) AS g)
SELECT d.destination_id, d.destination_type,
       ST_X(ST_Transform(d.geom, 4326)) AS lon, ST_Y(ST_Transform(d.geom, 4326)) AS lat,
       ST_Distance(d.geom, p.g) AS distance_m
FROM current.destinations d, p
WHERE d.destination_type = %s
ORDER BY d.geom <-> p.g
LIMIT %s
"""
Q_NEAREST_LABEL = """
WITH p AS (SELECT ST_Transform(ST_SetSRID(ST_MakePoint(%s, %s), 4326), 25832) AS g)
SELECT d.destination_id, d.destination_type, d.label,
       ST_X(ST_Transform(d.geom, 4326)) AS lon, ST_Y(ST_Transform(d.geom, 4326)) AS lat,
       ST_Distance(d.geom, p.g) AS distance_m
FROM current.destination_labels d, p
WHERE d.offered AND d.destination_type = %s AND d.label = %s
ORDER BY d.geom <-> p.g
LIMIT %s
"""
Q_DESTINATION_POINT = """
SELECT ST_X(ST_Transform(geom, 4326)) AS lon, ST_Y(ST_Transform(geom, 4326)) AS lat
FROM current.destinations WHERE destination_id = %s
UNION ALL
SELECT ST_X(ST_Transform(geom, 4326)), ST_Y(ST_Transform(geom, 4326))
FROM current.destination_labels WHERE destination_id = %s
UNION ALL
SELECT ST_X(ST_Transform(geom, 4326)), ST_Y(ST_Transform(geom, 4326))
FROM current.campus_sites WHERE 'campus_site:' || site_id = %s
LIMIT 1
"""
Q_CELL_AT = """
SELECT cell_id, district_id, populated
FROM current.cells
WHERE ST_Contains(geom, ST_Transform(ST_SetSRID(ST_MakePoint(%s, %s), 4326), 25832))
LIMIT 1
"""
# Words of the query must all occur in the label; `straße`, `strasse`, `str.` count as `str`.
_NORM = (
    "regexp_replace(replace(replace(replace(lower(label), 'straße', 'str'), 'strasse', 'str'),"
    " 'str.', 'str'), '[^a-z0-9äöüß]+', ' ', 'g')"
)
Q_SEARCH = f"""
SELECT a.label, a.cell_id,
       ST_X(ST_Transform(a.geom, 4326)) AS lon, ST_Y(ST_Transform(a.geom, 4326)) AS lat
FROM current.addresses a
WHERE a.cell_id IS NOT NULL AND {_NORM} LIKE ALL(%s)
ORDER BY length(a.label), a.label
LIMIT %s
"""


class Database(Protocol):
    async def run_id(self) -> str | None: ...

    async def fetch(self, query: str, params: Any = None) -> list[dict[str, Any]]: ...


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

    async def fetch(self, query: str, params: Any = None) -> list[dict[str, Any]]:
        async with self.pool.connection() as conn:
            cur = await conn.execute(query, params)
            return await cur.fetchall()

    async def run_id(self) -> str | None:
        """Run id `current` points at, or None before the first publish."""
        async with self.pool.connection() as conn:
            cur = await conn.execute(_RUN_ID)
            row = await cur.fetchone()
        return row["run_id"] if row else None
