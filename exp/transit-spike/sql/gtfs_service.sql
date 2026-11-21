-- GTFS checks for the T1 spike (run with the duckdb CLI from the repository root).
-- Input: data/spike/gtfs (naldo feed unpacked without shapes.txt).
-- Tübingen box: routing area approximation (city + ~4 km), EPSG:4326.
CREATE OR REPLACE MACRO secs(t) AS
  CAST(split_part(t, ':', 1) AS INT) * 3600 + CAST(split_part(t, ':', 2) AS INT) * 60
  + CAST(split_part(t, ':', 3) AS INT);

CREATE OR REPLACE TABLE stops AS
  SELECT * FROM read_csv('data/spike/gtfs/stops.txt', all_varchar = true);
CREATE OR REPLACE TABLE tue_stops AS
  SELECT stop_id, stop_name, CAST(stop_lat AS DOUBLE) lat, CAST(stop_lon AS DOUBLE) lon
  FROM stops
  WHERE CAST(stop_lon AS DOUBLE) BETWEEN 8.98 AND 9.14
    AND CAST(stop_lat AS DOUBLE) BETWEEN 48.46 AND 48.58;
CREATE OR REPLACE TABLE cal AS
  SELECT * FROM read_csv('data/spike/gtfs/calendar.txt', all_varchar = true);
CREATE OR REPLACE TABLE cal_dates AS
  SELECT * FROM read_csv('data/spike/gtfs/calendar_dates.txt', all_varchar = true);
CREATE OR REPLACE TABLE trips AS
  SELECT * FROM read_csv('data/spike/gtfs/trips.txt', all_varchar = true);
CREATE OR REPLACE TABLE routes AS
  SELECT * FROM read_csv('data/spike/gtfs/routes.txt', all_varchar = true);
CREATE OR REPLACE TABLE st AS
  SELECT trip_id, stop_id, CAST(stop_sequence AS INT) seq, secs(departure_time) dep_s,
         departure_time
  FROM read_csv('data/spike/gtfs/stop_times.txt', all_varchar = true)
  WHERE stop_id IN (SELECT stop_id FROM tue_stops);

-- Services active on a date: calendar weekday flag within range, plus/minus calendar_dates.
CREATE OR REPLACE MACRO active_services(d) AS TABLE
  WITH base AS (
    SELECT service_id FROM cal
    WHERE strptime(start_date, '%Y%m%d') <= d AND strptime(end_date, '%Y%m%d') >= d
      AND CASE dayofweek(d)
            WHEN 0 THEN sunday WHEN 1 THEN monday WHEN 2 THEN tuesday WHEN 3 THEN wednesday
            WHEN 4 THEN thursday WHEN 5 THEN friday ELSE saturday END = '1'
  ), added AS (
    SELECT service_id FROM cal_dates
    WHERE strptime(date, '%Y%m%d') = d AND exception_type = '1'
  ), removed AS (
    SELECT service_id FROM cal_dates
    WHERE strptime(date, '%Y%m%d') = d AND exception_type = '2'
  )
  SELECT service_id FROM (SELECT * FROM base UNION SELECT * FROM added)
  WHERE service_id NOT IN (SELECT service_id FROM removed);

.print '== Tübingen-area stops'
SELECT count(*) AS stops FROM tue_stops;

.print '== Trips touching the Tübingen area per service day (night = times >= 24:00)'
SELECT d::DATE AS service_day, dayname(d) AS weekday,
       count(DISTINCT t.trip_id) AS trips,
       count(DISTINCT CASE WHEN st.dep_s >= 86400 THEN t.trip_id END) AS trips_after_midnight
FROM (SELECT unnest([DATE '2026-11-24', DATE '2026-11-27', DATE '2026-11-28',
                     DATE '2026-11-29', DATE '2026-12-08', DATE '2026-12-15']) AS d) days,
     LATERAL (SELECT trip_id FROM trips WHERE service_id IN (SELECT * FROM active_services(days.d))) t
JOIN st USING (trip_id)
GROUP BY d ORDER BY d;
