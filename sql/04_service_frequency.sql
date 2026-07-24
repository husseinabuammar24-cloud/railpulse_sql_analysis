-- Service Frequency
-- Classify each service_id into a frequency category based on its total
-- number of scheduled trips:
--   > 50 trips      -> "High Frequency"
--   10-50 trips     -> "Medium Frequency"
--   < 10 trips      -> "Low Frequency/Special"
-- Show the percentage of services in each category.
-- TO RUN: sqlite3 -header -column railpulse.db < sql/04_service_frequency.sql

WITH service_trip_counts AS (
    SELECT
        calendar.service_id,
        COUNT(trips.trip_id) AS total_trips
    FROM calendar
    LEFT JOIN trips ON calendar.service_id = trips.service_id
    GROUP BY calendar.service_id
),
service_classification AS (
    SELECT
        service_id,
        total_trips,
        CASE
            WHEN total_trips > 5 THEN 'High Frequency'
            WHEN total_trips BETWEEN 2 AND 4 THEN 'Medium Frequency'
            ELSE 'Low Frequency/Special'
        END AS frequency_category
    FROM service_trip_counts
)
SELECT
    frequency_category,
    COUNT(*) AS service_count,
    ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM service_classification), 2) AS percentage_share
FROM service_classification
GROUP BY frequency_category
ORDER BY service_count DESC;
