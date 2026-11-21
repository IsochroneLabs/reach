-- Night departures (service day Friday 2026-11-27, times >= 24:00) at Tübingen-area stops,
-- grouped by route. Run after gtfs_service.sql in the same session (see scripts/gtfs_checks.sh).
.print '== Friday service day: routes with departures >= 24:00 in the Tübingen area'
SELECT r.route_short_name AS route, r.route_type, count(DISTINCT t.trip_id) AS trips,
       min(st.departure_time) AS first_after_24, max(st.departure_time) AS last
FROM trips t JOIN routes r USING (route_id) JOIN st USING (trip_id)
WHERE t.service_id IN (SELECT * FROM active_services(DATE '2026-11-27')) AND st.dep_s >= 86400
GROUP BY ALL ORDER BY trips DESC LIMIT 25;

.print '== Departures 00:15-01:30 (as 24:15-25:30) at central stops, Friday service day'
SELECT s.stop_name, r.route_short_name AS route, st.departure_time, t.trip_headsign
FROM trips t JOIN routes r USING (route_id) JOIN st USING (trip_id) JOIN tue_stops s USING (stop_id)
WHERE t.service_id IN (SELECT * FROM active_services(DATE '2026-11-27'))
  AND st.dep_s BETWEEN 87300 AND 91800
  AND (s.stop_name ILIKE '%Neue Aula%' OR s.stop_name ILIKE 'Tübingen Hbf%'
       OR s.stop_name ILIKE '%Nonnenhaus%' OR s.stop_name ILIKE '%Wöhrdstraße%')
ORDER BY st.dep_s LIMIT 40;
