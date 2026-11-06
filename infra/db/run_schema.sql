-- Template of one run schema run_<id> (docs/data_contract.md "Schema run_<id>"). publish runs it
-- as pipeline_write with search_path = run_<id>, public, then COPYs the data and refreshes
-- district_scores, all in one transaction. Raw counts and times only; classes, deficits and
-- district shares are views (AGENTS.md rule 5, methodology §3–4). Geometries EPSG:25832.

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

CREATE TABLE urban_boundary (
    part_id integer PRIMARY KEY,
    name    text,
    geom    geometry(MultiPolygon, 25832) NOT NULL
);

CREATE TABLE facilities (
    facility_id text NOT NULL,
    category    text NOT NULL,
    name        text,
    geom        geometry(Point, 25832) NOT NULL,
    PRIMARY KEY (facility_id, category)
);

CREATE TABLE facility_points (
    facility_id text NOT NULL,
    point_id    integer NOT NULL,
    kind        text NOT NULL CHECK (kind IN ('node', 'representative', 'access')),
    geom        geometry(Point, 25832) NOT NULL,
    PRIMARY KEY (facility_id, point_id)
);

CREATE TABLE stops (
    stop_id            text PRIMARY KEY,
    name               text NOT NULL,
    weekday_departures integer NOT NULL CHECK (weekday_departures >= 0),
    geom               geometry(Point, 25832) NOT NULL
);

CREATE TABLE profiles (
    profile_id      text PRIMARY KEY,
    costing         text NOT NULL,
    costing_options jsonb NOT NULL,
    speed_kmh       double precision NOT NULL CHECK (speed_kmh > 0),
    time_budget_min double precision NOT NULL CHECK (time_budget_min > 0)
);

CREATE TABLE access_counts (
    cell_id     text NOT NULL REFERENCES cells,
    category    text NOT NULL,
    profile_id  text NOT NULL REFERENCES profiles,
    count       integer NOT NULL CHECK (count >= 0),
    nearest_min double precision,
    PRIMARY KEY (cell_id, category, profile_id)
);

-- Facilities reachable within the facility budget per cell and profile (count stage): one row
-- per facility with its minimum time over its routing points; joined with facilities by
-- facility_id it gives access_counts.count. Read by the pin-drop inspector (arch. §6.5 rule 8).
-- (cell_id, profile_id, facility_id) is unique by construction and checked by validate_results;
-- no primary key: its index would take ~55 MB per run, the deduplicated lookup index ~4 MB.
CREATE TABLE reachable (
    cell_id     text NOT NULL REFERENCES cells,
    profile_id  text NOT NULL REFERENCES profiles,
    facility_id text NOT NULL,
    time_s      smallint NOT NULL CHECK (time_s >= 0)
);

CREATE TABLE transit_supply (
    cell_id          text NOT NULL REFERENCES cells,
    profile_id       text NOT NULL REFERENCES profiles,
    departures       integer NOT NULL CHECK (departures >= 0),
    stops_count      integer NOT NULL CHECK (stops_count >= 0),
    nearest_stop_min double precision,
    PRIMARY KEY (cell_id, profile_id)
);

-- Recommender (methodology §5, recommend stage): ranked zones per category x profile. geom = the
-- 100 m grid cell of the candidate (a zone, not an exact site), point_geom = its centre (the
-- routing target of its catchment). Raw gains only; classes stay derived at read time.
CREATE TABLE recommendations (
    category                 text NOT NULL,
    profile_id               text NOT NULL REFERENCES profiles,
    rank                     integer NOT NULL CHECK (rank >= 1),
    candidate_id             text NOT NULL,
    population_gain          double precision NOT NULL CHECK (population_gain >= 0),
    residents_gaining_access integer NOT NULL CHECK (residents_gaining_access >= 0),
    residents_to_sufficient  integer NOT NULL CHECK (residents_to_sufficient >= 0),
    catchment_residents      integer NOT NULL CHECK (catchment_residents >= 0),
    catchment_cells          integer NOT NULL CHECK (catchment_cells >= 0),
    geom                     geometry(Polygon, 25832) NOT NULL,
    point_geom               geometry(Point, 25832) NOT NULL,
    PRIMARY KEY (category, profile_id, rank),
    UNIQUE (category, profile_id, candidate_id)
);

-- Catchments of the recommended candidates: scored cells reaching the candidate's centre within
-- the facility budget (matrix time); the same for every category of a candidate and profile.
CREATE TABLE recommendation_catchments (
    candidate_id text NOT NULL,
    profile_id   text NOT NULL REFERENCES profiles,
    cell_id      text NOT NULL REFERENCES cells,
    time_s       smallint NOT NULL CHECK (time_s >= 0),
    PRIMARY KEY (candidate_id, profile_id, cell_id)
);

-- Category rows: k set, class/lower/upper null. Transit rows: category 'transit', class and
-- bounds set, k null (upper null = open-ended).
CREATE TABLE thresholds (
    category text NOT NULL,
    k        integer CHECK (k >= 1),
    class    text,
    lower    integer,
    upper    integer,
    UNIQUE NULLS NOT DISTINCT (category, class),
    CHECK ((class IS NULL) = (k IS NOT NULL))
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
CREATE INDEX ON urban_boundary USING gist (geom);
CREATE INDEX ON facilities USING gist (geom);
CREATE INDEX ON facilities (category);
CREATE INDEX ON facility_points USING gist (geom);
CREATE INDEX ON stops USING gist (geom);
CREATE INDEX ON access_counts (category, profile_id);
CREATE INDEX ON reachable (cell_id, profile_id);
CREATE INDEX ON recommendations USING gist (geom);

-- methodology §4: lack A = 0, insufficient 0 < A < k, sufficient A >= k;
-- deficit U = P * max(0, 1 - A / k).
CREATE VIEW scores AS
SELECT a.cell_id,
       a.category,
       a.profile_id,
       a.count,
       a.nearest_min,
       CASE
           WHEN a.count = 0 THEN 'lack'
           WHEN a.count < t.k THEN 'insufficient'
           ELSE 'sufficient'
       END AS class,
       c.population * greatest(0, 1 - a.count::double precision / t.k) AS deficit
FROM access_counts a
JOIN thresholds t ON t.category = a.category AND t.class IS NULL
JOIN cells c ON c.cell_id = a.cell_id;

-- methodology §3: class of the summed departures S_i (bounds inclusive, upper null = open).
CREATE VIEW transit_scores AS
SELECT s.cell_id,
       s.profile_id,
       t.class
FROM transit_supply s
JOIN thresholds t
  ON t.category = 'transit'
 AND t.class IS NOT NULL
 AND s.departures >= t.lower
 AND (t.upper IS NULL OR s.departures <= t.upper);

-- methodology §4 "District results": shares of residents per class, deficit sum, residents
-- lacking access; cells without a district are left out.
CREATE MATERIALIZED VIEW district_scores AS
SELECT c.district_id,
       s.category,
       s.profile_id,
       coalesce(sum(c.population) FILTER (WHERE s.class = 'lack'), 0)::double precision
           / nullif(sum(c.population), 0) AS share_lack,
       coalesce(sum(c.population) FILTER (WHERE s.class = 'insufficient'), 0)::double precision
           / nullif(sum(c.population), 0) AS share_insufficient,
       coalesce(sum(c.population) FILTER (WHERE s.class = 'sufficient'), 0)::double precision
           / nullif(sum(c.population), 0) AS share_sufficient,
       sum(s.deficit) AS deficit_sum,
       coalesce(sum(c.population) FILTER (WHERE s.class = 'lack'), 0)::integer AS residents_lack
FROM scores s
JOIN cells c ON c.cell_id = s.cell_id
WHERE c.district_id IS NOT NULL
GROUP BY c.district_id, s.category, s.profile_id
WITH NO DATA;

CREATE UNIQUE INDEX ON district_scores (district_id, category, profile_id);
