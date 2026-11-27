-- Schema listings: views on the latest listing snapshot lst_<id> (arch. O24, data contract
-- Listings, F4.4). publish_listings (as pipeline_write) creates lst_<id> and replaces the views;
-- app_read reads the views only, like current.
CREATE SCHEMA IF NOT EXISTS listings AUTHORIZATION pipeline_write;
GRANT USAGE ON SCHEMA listings TO app_read, supervisor_read;
ALTER DEFAULT PRIVILEGES FOR ROLE pipeline_write IN SCHEMA listings
    GRANT SELECT ON TABLES TO app_read, supervisor_read;
