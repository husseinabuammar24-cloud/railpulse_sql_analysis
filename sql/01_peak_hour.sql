-- The Peak Hour Problem
-- What hour of the day experiences the highest volume of scheduled 
-- train departures across the entire network?
-- GTFS allows departure_time past "23:59:59" (e.g. "25:10:00") for trips
-- that start before midnight and continue into the next service day, so
-- SUBSTR() is used instead of strftime() and the result is normalized
-- back into a standard 0-23 hour with % 24. (Note: you have to save the file before running it!)
-- TO RUN: sqlite3 railpulse.db < sql/01_peak_hour.sql

SELECT
    CAST(SUBSTR(departure_time, 1, 2) AS INTEGER) % 24 AS hour_of_day,
    COUNT(*) AS departure_count
FROM stop_times
WHERE departure_time IS NOT NULL
GROUP BY hour_of_day
ORDER BY departure_count DESC;


