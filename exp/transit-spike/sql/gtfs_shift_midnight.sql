-- Workaround for R5 (no routing through midnight, conveyal/r5#286): copy the part of every trip
-- at or after 24:00 into a new trip on a new service that runs one day later, times - 24 h.
-- Parameters: src (unpacked clipped feed dir), dst (output dir). Transfers on the same vehicle
-- across midnight are lost (the copy starts at its first stop >= 24:00).
CREATE MACRO secs(t) AS CAST(split_part(t, ':', 1) AS INT) * 3600
  + CAST(split_part(t, ':', 2) AS INT) * 60 + CAST(split_part(t, ':', 3) AS INT);
CREATE MACRO hms(s) AS lpad((s // 3600)::VARCHAR, 2, '0') || ':' || lpad(((s % 3600) // 60)::VARCHAR, 2, '0')
  || ':' || lpad((s % 60)::VARCHAR, 2, '0');
CREATE TABLE st AS SELECT * FROM read_csv(getvariable('src') || '/stop_times.txt', all_varchar = true);
CREATE TABLE trips AS SELECT * FROM read_csv(getvariable('src') || '/trips.txt', all_varchar = true);
CREATE TABLE cal AS SELECT * FROM read_csv(getvariable('src') || '/calendar.txt', all_varchar = true);
CREATE TABLE cd AS SELECT * FROM read_csv(getvariable('src') || '/calendar_dates.txt', all_varchar = true);
CREATE TABLE late AS SELECT * FROM st WHERE secs(departure_time) >= 86400;
CREATE TABLE late_trips AS SELECT DISTINCT trip_id FROM late GROUP BY trip_id HAVING count(*) >= 2;
CREATE TABLE new_st AS
  SELECT trip_id || '_n' AS trip_id, hms(secs(arrival_time) - 86400) AS arrival_time,
         hms(secs(departure_time) - 86400) AS departure_time, stop_id, stop_sequence, stop_headsign,
         pickup_type, drop_off_type, shape_dist_traveled
  FROM late WHERE trip_id IN (SELECT trip_id FROM late_trips) AND secs(arrival_time) >= 86400;
CREATE TABLE new_trips AS
  SELECT * REPLACE (trip_id || '_n' AS trip_id, service_id || '_n' AS service_id)
  FROM trips WHERE trip_id IN (SELECT trip_id FROM late_trips);
CREATE TABLE used AS SELECT DISTINCT service_id FROM trips WHERE trip_id IN (SELECT trip_id FROM late_trips);
-- weekday flags move one day later (Mon -> Tue, ..., Sun -> Mon); dates + 1 day
CREATE TABLE new_cal AS
  SELECT service_id || '_n' AS service_id, sunday AS monday, monday AS tuesday, tuesday AS wednesday,
         wednesday AS thursday, thursday AS friday, friday AS saturday, saturday AS sunday,
         strftime(strptime(start_date, '%Y%m%d') + INTERVAL 1 DAY, '%Y%m%d') AS start_date,
         strftime(strptime(end_date, '%Y%m%d') + INTERVAL 1 DAY, '%Y%m%d') AS end_date
  FROM cal WHERE service_id IN (SELECT service_id FROM used);
CREATE TABLE new_cd AS
  SELECT service_id || '_n' AS service_id, strftime(strptime(date, '%Y%m%d') + INTERVAL 1 DAY, '%Y%m%d') AS date,
         exception_type FROM cd WHERE service_id IN (SELECT service_id FROM used);
COPY (SELECT * FROM st UNION ALL SELECT * FROM new_st) TO (getvariable('dst') || '/stop_times.txt') (HEADER);
COPY (SELECT * FROM trips UNION ALL BY NAME SELECT * FROM new_trips) TO (getvariable('dst') || '/trips.txt') (HEADER);
COPY (SELECT * FROM cal UNION ALL BY NAME SELECT * FROM new_cal) TO (getvariable('dst') || '/calendar.txt') (HEADER);
COPY (SELECT * FROM cd UNION ALL BY NAME SELECT * FROM new_cd) TO (getvariable('dst') || '/calendar_dates.txt') (HEADER);
SELECT (SELECT count(*) FROM late_trips) AS shifted_trips, (SELECT count(*) FROM new_st) AS shifted_stop_times;
