-- Clip the naldo GTFS feed to a bbox: keep stops inside, their stop_times, trips with >= 2 kept
-- stops, and the routes, services and transfers they use. Parameters via getvariable():
--   src (unpacked feed dir), dst (output dir), min_lon, min_lat, max_lon, max_lat.
CREATE TABLE stops AS SELECT * FROM read_csv(getvariable('src') || '/stops.txt', all_varchar = true)
  WHERE CAST(stop_lon AS DOUBLE) BETWEEN getvariable('min_lon') AND getvariable('max_lon')
    AND CAST(stop_lat AS DOUBLE) BETWEEN getvariable('min_lat') AND getvariable('max_lat');
-- Parent stations of kept stops must exist too.
INSERT INTO stops SELECT * FROM read_csv(getvariable('src') || '/stops.txt', all_varchar = true)
  WHERE stop_id IN (SELECT parent_station FROM stops WHERE parent_station <> '')
    AND stop_id NOT IN (SELECT stop_id FROM stops);
CREATE TABLE st0 AS SELECT * FROM read_csv(getvariable('src') || '/stop_times.txt', all_varchar = true)
  WHERE stop_id IN (SELECT stop_id FROM stops);
CREATE TABLE keep_trips AS SELECT trip_id FROM st0 GROUP BY trip_id HAVING count(*) >= 2;
CREATE TABLE stop_times AS SELECT * FROM st0 WHERE trip_id IN (SELECT trip_id FROM keep_trips);
CREATE TABLE trips AS SELECT * FROM read_csv(getvariable('src') || '/trips.txt', all_varchar = true)
  WHERE trip_id IN (SELECT trip_id FROM keep_trips);
CREATE TABLE routes AS SELECT * FROM read_csv(getvariable('src') || '/routes.txt', all_varchar = true)
  WHERE route_id IN (SELECT route_id FROM trips);
CREATE TABLE agency AS SELECT * FROM read_csv(getvariable('src') || '/agency.txt', all_varchar = true)
  WHERE agency_id IN (SELECT agency_id FROM routes);
CREATE TABLE calendar AS SELECT * FROM read_csv(getvariable('src') || '/calendar.txt', all_varchar = true)
  WHERE service_id IN (SELECT service_id FROM trips);
CREATE TABLE calendar_dates AS SELECT * FROM read_csv(getvariable('src') || '/calendar_dates.txt', all_varchar = true)
  WHERE service_id IN (SELECT service_id FROM trips);
CREATE TABLE transfers AS SELECT * FROM read_csv(getvariable('src') || '/transfers.txt', all_varchar = true)
  WHERE from_stop_id IN (SELECT stop_id FROM stops) AND to_stop_id IN (SELECT stop_id FROM stops);
CREATE TABLE feed_info AS SELECT * FROM read_csv(getvariable('src') || '/feed_info.txt', all_varchar = true);
COPY stops TO (getvariable('dst') || '/stops.txt') (HEADER, QUOTE '"');
COPY stop_times TO (getvariable('dst') || '/stop_times.txt') (HEADER);
COPY trips TO (getvariable('dst') || '/trips.txt') (HEADER);
COPY routes TO (getvariable('dst') || '/routes.txt') (HEADER);
COPY agency TO (getvariable('dst') || '/agency.txt') (HEADER);
COPY calendar TO (getvariable('dst') || '/calendar.txt') (HEADER);
COPY calendar_dates TO (getvariable('dst') || '/calendar_dates.txt') (HEADER);
COPY transfers TO (getvariable('dst') || '/transfers.txt') (HEADER);
COPY feed_info TO (getvariable('dst') || '/feed_info.txt') (HEADER);
SELECT (SELECT count(*) FROM stops) stops, (SELECT count(*) FROM trips) trips,
       (SELECT count(*) FROM stop_times) stop_times, (SELECT count(*) FROM routes) routes;
