-- Origins per A1 (approximation for sizing): populated Zensus 100 m cells whose centroid lies in
-- the city boundary, plus cells with an OSM address but no residents. Needs the duckdb spatial
-- extension. Output: data/spike/work/origins.csv (cell_id, kind, population, lon, lat).
INSTALL spatial; LOAD spatial;
CREATE TABLE city AS
  SELECT geom FROM ST_Read('data/spike/work/boundary.geojson') WHERE admin_level = '8';
CREATE TABLE cells AS
  SELECT GITTER_ID_100m AS cell_id, TRY_CAST(Einwohner AS INT) AS population,
         ST_Transform(ST_Point(CAST(x_mp_100m AS DOUBLE), CAST(y_mp_100m AS DOUBLE)), 'EPSG:3035', 'EPSG:4326', always_xy := true) AS pt,
         x_mp_100m AS x, y_mp_100m AS y
  FROM read_csv('data/spike/zensus/Zensus2022_Bevoelkerungszahl_100m-Gitter.csv', delim = ';',
                all_varchar = true)
  WHERE CAST(x_mp_100m AS INT) BETWEEN 4230000 AND 4275000
    AND CAST(y_mp_100m AS INT) BETWEEN 2800000 AND 2835000;
CREATE TABLE populated AS
  SELECT c.* FROM cells c, city WHERE c.population > 0 AND ST_Within(c.pt, city.geom);
CREATE TABLE addr AS
  SELECT ST_Point(lon, lat) AS pt FROM read_csv('data/spike/work/addr.csv');
CREATE TABLE addr3035 AS
  SELECT ST_Transform(pt, 'EPSG:4326', 'EPSG:3035', always_xy := true) AS p FROM addr a, city
  WHERE ST_Within(a.pt, city.geom);
-- Zensus id from 3035 coordinates: N<y floor 100>E<x floor 100>.
CREATE TABLE addr_cells AS
  SELECT DISTINCT 'CRS3035RES100mN' || (floor(ST_Y(p) / 100) * 100)::BIGINT
         || 'E' || (floor(ST_X(p) / 100) * 100)::BIGINT AS cell_id,
         (floor(ST_X(p) / 100) * 100 + 50)::BIGINT AS x, (floor(ST_Y(p) / 100) * 100 + 50)::BIGINT AS y
  FROM addr3035;
CREATE TABLE origins AS
  SELECT cell_id, 'populated' AS kind, population, ST_X(pt) lon, ST_Y(pt) lat FROM populated
  UNION ALL
  SELECT a.cell_id, 'address', 0,
         ST_X(ST_Transform(ST_Point(a.x::DOUBLE, a.y::DOUBLE), 'EPSG:3035', 'EPSG:4326', always_xy := true)),
         ST_Y(ST_Transform(ST_Point(a.x::DOUBLE, a.y::DOUBLE), 'EPSG:3035', 'EPSG:4326', always_xy := true))
  FROM addr_cells a WHERE a.cell_id NOT IN (SELECT cell_id FROM populated);
COPY origins TO 'data/spike/work/origins.csv' (HEADER);
SELECT kind, count(*) AS cells, sum(population) AS residents FROM origins GROUP BY kind;
