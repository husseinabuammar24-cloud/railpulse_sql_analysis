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


'''
Output:
-----

10|139071
9|135851
11|135156
12|131354
13|129093
8|126474
14|125563
15|117889
16|113909
17|113471
7|112928
18|112798
19|110299
20|110284
21|109585
22|105451
6|83442
23|74074
5|34173
0|29885
1|7973
4|5941
2|805
3|50

'''
