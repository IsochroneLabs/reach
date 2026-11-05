-- Schema meta (run history, provenance) and schema current (views on the latest published
-- run). docs/data_contract.md "Schema meta". Applied once by `migrate`, as the superuser.

CREATE EXTENSION IF NOT EXISTS postgis;

-- meta may already exist: migrate creates it for meta.schema_migrations before any migration.
CREATE SCHEMA IF NOT EXISTS meta;

CREATE TABLE meta.runs (
    run_id            text PRIMARY KEY CHECK (run_id ~ '^\d{8}T\d{6}Z$'),
    started_at        timestamptz NOT NULL,
    finished_at       timestamptz,
    status            text NOT NULL CHECK (status IN ('running', 'published', 'failed')),
    osm_snapshot      timestamptz,
    gtfs_valid_from   date,
    gtfs_valid_to     date,
    reference_weekday date,
    config_hash       text NOT NULL
);

CREATE TABLE meta.data_sources (
    run_id       text NOT NULL REFERENCES meta.runs ON DELETE CASCADE,
    source       text NOT NULL,
    url          text NOT NULL,
    retrieved_at timestamptz NOT NULL,
    checksum     text NOT NULL,
    licence      text NOT NULL,
    PRIMARY KEY (run_id, source)
);

GRANT USAGE ON SCHEMA meta TO pipeline_write, app_read, supervisor_read;
GRANT SELECT, INSERT, UPDATE, DELETE ON meta.runs, meta.data_sources TO pipeline_write;
GRANT SELECT ON meta.runs, meta.data_sources TO app_read, supervisor_read;

-- The views are created and replaced by publish (as pipeline_write, the owner); readers get
-- SELECT through the default privileges below. Access to the run tables behind a view is
-- checked against the view owner, so app_read needs no rights on the run schemas.
CREATE SCHEMA current AUTHORIZATION pipeline_write;
GRANT USAGE ON SCHEMA current TO app_read, supervisor_read;
ALTER DEFAULT PRIVILEGES FOR ROLE pipeline_write IN SCHEMA current
    GRANT SELECT ON TABLES TO app_read, supervisor_read;
