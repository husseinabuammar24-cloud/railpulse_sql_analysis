-- Busiest Morning Destinations
-- Find the top 3 most frequent terminal destinations (trip_headsign) for
-- all morning trips that depart before 12:00:00
--
-- "Departs" is taken as each trip's first stop_times row(the lowest 
-- stop_sequence), i.e. the trip's actual origin departure time.
-- TO RUN: sqlite3 -header -column railpulse.db < sql/03_morning_destinations.sql


-- Create a temporary table named first_departure that identifies the very first stop
WITH first_departure AS (
    SELECT
        trip_id,
        MIN(stop_sequence) AS first_sequence
    FROM stop_times
    GROUP BY trip_id
) 
SELECT 
    trips.trip_headsign, 
    COUNT(*) AS trip_count
FROM first_departure
JOIN stop_times
    ON stop_times.trip_id = first_departure.trip_id
    AND stop_times.stop_sequence = first_departure.first_sequence
JOIN trips
    ON trips.trip_id = first_departure.trip_id
WHERE stop_times.departure_time < '12:00:00'
    AND trips.trip_headsign IS NOT NULL
GROUP BY trips.trip_headsign 
ORDER BY trip_count DESC
LIMIT 3;
