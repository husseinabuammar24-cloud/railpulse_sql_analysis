-- Platform Bottlenecks
-- Identify the top 3 busiest platforms in Brussels-Central.
--
-- Brussels-Central appears as a parent station (location_type = 1) with
-- individual platform-level stops (location_type = 0) linked via
-- parent_station. The station name is matched in both French and Dutch
-- since GTFS-BE stop names aren't always in the same language.
-- TO RUN: sqlite3 -header -column railpulse.db < sql/02_platform_bottlenecks.sql

SELECT
    platform_stop.platform_code,
    COUNT(*) AS departure_count
FROM stop_times
JOIN stops AS platform_stop
    ON stop_times.stop_id = platform_stop.stop_id
JOIN stops AS parent_stop
    ON platform_stop.parent_station = parent_stop.stop_id
WHERE (parent_stop.stop_name LIKE '%Brussels-Central%'
       OR parent_stop.stop_name LIKE '%Bruxelles-Central%'
       OR parent_stop.stop_name LIKE '%Brussel-Centraal%')
  AND platform_stop.platform_code IS NOT NULL
GROUP BY platform_stop.platform_code
ORDER BY departure_count DESC
LIMIT 3;

