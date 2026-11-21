-- Cross-check of the OTP night result: N93 departures >= 24:00 per service day (run after
-- gtfs_service.sql in the same session).
.print '== N93 departures >= 24:00 at Tübingen Neckarbrücke per service day'
SELECT d::DATE AS service_day, dayname(d) AS weekday, list(DISTINCT st.departure_time ORDER BY st.departure_time) AS deps
FROM (SELECT unnest([DATE '2026-11-24', DATE '2026-11-27', DATE '2026-11-28']) AS d) days,
     LATERAL (SELECT trip_id, route_id FROM trips WHERE service_id IN (SELECT * FROM active_services(days.d))) t
JOIN routes r USING (route_id) JOIN st USING (trip_id) JOIN tue_stops s USING (stop_id)
WHERE r.route_short_name = 'N93' AND st.dep_s >= 86400 AND s.stop_name ILIKE '%Neckarbrücke%'
GROUP BY d ORDER BY d;
