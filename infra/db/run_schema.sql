-- Template of one run schema run_<id> (docs/data_contract.md "Schema run_<id>"). publish runs it
-- as pipeline_write with search_path = run_<id>, public, then COPYs the data, all in one
-- transaction. Ported subset (S0.4): the input layers of validate and the validation report.
-- Destinations, trip windows and raw travel times are added when their columns are fixed (S1.4,
-- S1.9). Raw values only; the fit is derived by the API (AGENTS.md rule 5). Geometries EPSG:25832.

CREATE TABLE cells (
    cell_id     text PRIMARY KEY,
    population  integer NOT NULL CHECK (population >= 0),
    district_id text,
    geom        geometry(Polygon, 25832) NOT NULL,
    origin_geom geometry(Point, 25832) NOT NULL
);

CREATE TABLE districts (
    district_id text PRIMARY KEY,
    name        text NOT NULL,
    admin_level smallint NOT NULL,
    geom        geometry(MultiPolygon, 25832) NOT NULL
);

CREATE TABLE stops (
    stop_id text PRIMARY KEY,
    name    text NOT NULL,
    geom    geometry(Point, 25832) NOT NULL
);

CREATE TABLE validation_report (
    "check" text NOT NULL,
    stage   text NOT NULL,
    status  text NOT NULL CHECK (status IN ('ok', 'warn', 'fail')),
    value   double precision,
    message text NOT NULL,
    PRIMARY KEY (stage, "check")
);

CREATE INDEX ON cells USING gist (geom);
CREATE INDEX ON cells USING gist (origin_geom);
CREATE INDEX ON cells (district_id);
CREATE INDEX ON districts USING gist (geom);
CREATE INDEX ON stops USING gist (geom);
