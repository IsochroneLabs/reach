-- Template of one run schema run_<id> (docs/data_contract.md "Schema run_<id>", v1.1.0). publish
-- runs it as pipeline_write with search_path = run_<id>, public, then COPYs the data, all in one
-- transaction. Raw values only; the fit is derived by the API (AGENTS.md rule 5).
-- Geometries EPSG:25832.

CREATE TABLE cells (
    cell_id     text PRIMARY KEY,
    population  integer NOT NULL CHECK (population >= 0),
    populated   boolean NOT NULL,
    district_id text,
    geom        geometry(Polygon, 25832) NOT NULL,
    origin_geom geometry(Point, 25832) NOT NULL,
    CHECK (populated = (population > 0))
);

CREATE TABLE districts (
    district_id text PRIMARY KEY,
    name        text NOT NULL,
    admin_level smallint NOT NULL,
    geom        geometry(MultiPolygon, 25832) NOT NULL
);

CREATE TABLE destination_types (
    destination_type text PRIMARY KEY,
    label_en         text NOT NULL,
    label_de         text NOT NULL,
    source           text NOT NULL CHECK (source IN ('osm', 'campus', 'labels')),
    trip_window      text NOT NULL,
    fine_time_min    real NOT NULL CHECK (fine_time_min > 0),
    nearest_k        smallint
);

CREATE TABLE destinations (
    destination_id   text PRIMARY KEY,
    destination_type text NOT NULL REFERENCES destination_types,
    name             text NOT NULL,
    osm_id           text NOT NULL,
    geom             geometry(Point, 25832) NOT NULL
);

-- OSM details of destinations and labelled destinations, shown by the app (notes N29).
CREATE TABLE destination_details (
    destination_id text PRIMARY KEY,
    opening_hours  text,
    website        text,
    wheelchair     text,
    open_in_window boolean  -- open at the time of the type's trip window; NULL = unknown
);

CREATE TABLE destination_labels (
    destination_id   text PRIMARY KEY,
    destination_type text NOT NULL REFERENCES destination_types,
    label_kind       text NOT NULL CHECK (label_kind IN ('brand', 'group', 'category', 'religion')),
    label            text NOT NULL,
    name             text NOT NULL,
    n_features       integer NOT NULL CHECK (n_features >= 1),
    osm_ids          text NOT NULL,
    offered          boolean NOT NULL,
    geom             geometry(Point, 25832) NOT NULL
);

CREATE TABLE campus_sites (
    site_id       text PRIMARY KEY,
    name          text NOT NULL,
    default_share real NOT NULL CHECK (default_share BETWEEN 0 AND 1),
    geom          geometry(Point, 25832) NOT NULL
);

CREATE TABLE programmes (
    programme text PRIMARY KEY,
    label_en  text NOT NULL,
    label_de  text NOT NULL,
    sites     text[] NOT NULL,
    shares    double precision[]  -- per site (Alma, notes N24); NULL = equal weights
);

CREATE TABLE addresses (
    address_id  integer PRIMARY KEY,
    label       text NOT NULL,
    street      text NOT NULL,
    housenumber text NOT NULL,
    postcode    text NOT NULL,
    city        text NOT NULL,
    residential boolean NOT NULL,
    cell_id     text REFERENCES cells,
    geom        geometry(Point, 25832) NOT NULL
);

CREATE TABLE stops (
    stop_id text PRIMARY KEY,
    name    text NOT NULL,
    geom    geometry(Point, 25832) NOT NULL
);

CREATE TABLE trip_windows (
    trip_window    text PRIMARY KEY,
    weekday        text NOT NULL,
    "time"         text NOT NULL,
    kind           text NOT NULL CHECK (kind IN ('depart_at', 'arrive_by')),
    direction      text NOT NULL CHECK (direction IN ('to', 'back')),
    reference_date date NOT NULL
);

CREATE TABLE stop_departures (
    stop_id     text NOT NULL,
    trip_window text NOT NULL REFERENCES trip_windows,
    departures  integer NOT NULL CHECK (departures >= 0),
    PRIMARY KEY (stop_id, trip_window)
);

CREATE TABLE travel_times (
    cell_id        text NOT NULL REFERENCES cells,
    destination_id text NOT NULL,
    mode           text NOT NULL CHECK (mode IN ('walk', 'bike', 'transit', 'bike_transit')),
    trip_window    text NOT NULL REFERENCES trip_windows,
    time_s         integer CHECK (time_s >= 0),
    access_s       integer,
    wait_s         integer,
    in_vehicle_s   integer,
    egress_s       integer,
    transfers      smallint,
    first_stop     text,
    first_route    text,
    departure      text,
    walk_only      boolean NOT NULL DEFAULT false,
    PRIMARY KEY (cell_id, destination_id, mode, trip_window)
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
CREATE INDEX ON destinations (destination_type);
CREATE INDEX ON destination_labels (destination_type, label);
CREATE INDEX ON addresses (lower(label) text_pattern_ops);
CREATE INDEX ON addresses USING gist (geom);
CREATE INDEX ON stops USING gist (geom);
CREATE INDEX ON travel_times (destination_id);
