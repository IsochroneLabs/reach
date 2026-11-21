-- Plausibility pairs: add the Zensus cell id and centroid of each address-side point (the
-- pipeline routes from cell centroids). Input data/spike/work/pairs_raw.csv; output
-- exp/transit-spike/config/plausibility_pairs.csv (committed: addresses are public places).
INSTALL spatial; LOAD spatial;
CREATE MACRO cell_id(lon, lat) AS (
  WITH p AS (SELECT ST_Transform(ST_Point(lon, lat), 'EPSG:4326', 'EPSG:3035', always_xy := true) g)
  SELECT 'CRS3035RES100mN' || (floor(ST_Y(g) / 100) * 100)::BIGINT || 'E'
         || (floor(ST_X(g) / 100) * 100)::BIGINT FROM p);
CREATE MACRO centroid(lon, lat) AS (
  WITH p AS (SELECT ST_Transform(ST_Point(lon, lat), 'EPSG:4326', 'EPSG:3035', always_xy := true) g)
  SELECT ST_Transform(ST_Point(floor(ST_X(g) / 100) * 100 + 50, floor(ST_Y(g) / 100) * 100 + 50),
                      'EPSG:3035', 'EPSG:4326', always_xy := true) FROM p);
COPY (
  SELECT pair_id, trip_window, date, time, rule, from_label, from_lon, from_lat,
         CASE WHEN trip_window = 'night_return' THEN cell_id(to_lon, to_lat)
              ELSE cell_id(from_lon, from_lat) END AS home_cell_id,
         round(ST_X(CASE WHEN trip_window = 'night_return' THEN centroid(to_lon, to_lat)
                         ELSE centroid(from_lon, from_lat) END), 5) AS home_cell_lon,
         round(ST_Y(CASE WHEN trip_window = 'night_return' THEN centroid(to_lon, to_lat)
                         ELSE centroid(from_lon, from_lat) END), 5) AS home_cell_lat,
         to_label, to_lon, to_lat,
         '' AS ref_departure, '' AS ref_arrival, '' AS ref_duration_min, '' AS ref_lines,
         '' AS ref_transfers, '' AS ref_source, '' AS ref_looked_up_on
  FROM read_csv('data/spike/work/pairs_raw.csv')
) TO 'exp/transit-spike/config/plausibility_pairs.csv' (HEADER);
