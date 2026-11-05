-- Roles and database privileges (arch. §8, docs/data_contract.md). Applied by
-- `python -m reach_pipeline migrate` as the superuser before the migrations; idempotent.
-- Passwords are set by `migrate` from APP_READ_PASSWORD, PIPELINE_WRITE_PASSWORD and
-- SUPERVISOR_READ_PASSWORD (.env), never here.
--
--   pipeline_write   publish/cleanup: creates the run_<id> schemas, switches the current views,
--                    writes meta.runs and meta.data_sources
--   app_read         API: reads the current views and meta (USAGE on current, no run schemas)
--   supervisor_read  supervisors (SSH tunnel): reads current, meta and every run schema

DO $$
DECLARE
    r text;
BEGIN
    FOREACH r IN ARRAY ARRAY['pipeline_write', 'app_read', 'supervisor_read'] LOOP
        IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = r) THEN
            EXECUTE format('CREATE ROLE %I LOGIN', r);
        END IF;
    END LOOP;
END
$$;

-- Database level: only the three roles connect; only pipeline_write creates schemas.
DO $$
BEGIN
    EXECUTE format('REVOKE ALL ON DATABASE %I FROM PUBLIC', current_database());
    EXECUTE format(
        'GRANT CONNECT, TEMPORARY ON DATABASE %I TO pipeline_write, app_read, supervisor_read',
        current_database()
    );
    EXECUTE format('GRANT CREATE ON DATABASE %I TO pipeline_write', current_database());
END
$$;

-- PostGIS types and functions live in public; nobody creates objects there.
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO pipeline_write, app_read, supervisor_read;

-- Default privileges: every schema, table and view pipeline_write creates (run_<id>.*) is
-- readable by the supervisors. The API gets SELECT on the current views only (0001_meta.sql).
ALTER DEFAULT PRIVILEGES FOR ROLE pipeline_write GRANT USAGE ON SCHEMAS TO supervisor_read;
ALTER DEFAULT PRIVILEGES FOR ROLE pipeline_write GRANT SELECT ON TABLES TO supervisor_read;
