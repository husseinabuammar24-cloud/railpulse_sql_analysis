-- Amenity Coverage by Route (Wheelchair & Bike Access)
-- For each non-bus route, calculate the percentage of trips offering
-- wheelchair accessibility, bike storage, and either amenity.
-- Routes with 5 or fewer trips are excluded; results ranked by trip volume.
-- TO RUN: sqlite3 -header -column railpulse.db < sql/05_accessibility_audit.sql

WITH trip_amenities AS (
    SELECT
        trips.trip_id,
        trips.route_id,
        CASE
            WHEN NULLIF(trips.wheelchair_accessible, '') IS NULL THEN 0
            ELSE CAST(trips.wheelchair_accessible AS INTEGER)
        END AS wheelchair_accessible_flag,
        CASE
            WHEN NULLIF(trips.bikes_allowed, '') IS NULL THEN 0
            ELSE CAST(trips.bikes_allowed AS INTEGER)
        END AS bikes_allowed_flag
    FROM trips
),
route_stats AS (
    SELECT
        r.route_id,
        COALESCE(NULLIF(r.route_short_name, ''), '(no_short_name)') AS route_short_name,
        COALESCE(NULLIF(r.route_long_name, ''), '(no_long_name)') AS route_long_name,
        COUNT(DISTINCT ta.trip_id) AS total_trips,
        ROUND(100.0 * SUM(ta.wheelchair_accessible_flag) / NULLIF(COUNT(DISTINCT ta.trip_id), 0), 2) AS wheelchair_accessible_pct,
        ROUND(100.0 * SUM(ta.bikes_allowed_flag) / NULLIF(COUNT(DISTINCT ta.trip_id), 0), 2) AS bikes_allowed_pct,
        ROUND(100.0 * SUM(CASE WHEN ta.wheelchair_accessible_flag = 1 OR ta.bikes_allowed_flag = 1 THEN 1 ELSE 0 END) / NULLIF(COUNT(DISTINCT ta.trip_id), 0), 2) AS either_amenity_pct
    FROM trip_amenities ta
    JOIN routes r ON r.route_id = ta.route_id
    WHERE COALESCE(r.route_short_name, '') NOT LIKE '%BUS%'
      AND COALESCE(r.route_long_name, '') NOT LIKE '%BUS%'
    GROUP BY r.route_id, route_short_name, route_long_name
    HAVING total_trips > 5
)
SELECT
    route_short_name,
    route_long_name,
    total_trips,
    wheelchair_accessible_pct,
    bikes_allowed_pct,
    either_amenity_pct
FROM route_stats
ORDER BY total_trips DESC
LIMIT 15;




'''

route_short_name  route_long_name                                 total_trips  wheelchair_accessible_pct  bikes_allowed_pct  either_amenity_pct
----------------  ----------------------------------------------  -----------  -------------------------  -----------------  ------------------
IC                Anvers-Central -- Charleroi-Central             3081         0.0                        100.0              100.0             
S2                Louvain -- Braine-le-Comte                      2674         0.0                        100.0              100.0             
IC                Eupen -- Ostende                                2210         0.0                        100.0              100.0             
S10               Termonde -- Alost                               1782         0.0                        100.0              100.0             
IC                Brussels Airport-Zaventem -- Gand-Saint-Pierre  1734         0.0                        100.0              100.0             
IC                Anvers-Central -- Hasselt                       1649         0.0                        100.0              100.0             
IC                Liège-Guillemins -- Knokke                      1577         0.0                        100.0              100.0             
IC                Brussels Airport-Zaventem -- Mons               1569         0.0                        100.0              100.0             
IC                Luxembourg (LU) -- Bruxelles-Midi               1435         0.0                        100.0              100.0             
IC                Bruxelles-Midi -- Anvers-Central                1398         0.0                        100.0              100.0             
S1                Nivelles -- Anvers-Central                      1350         0.0                        100.0              100.0             
EC                Rotterdam Centraal (NL) -- Bruxelles-Midi       1191         0.0                        100.0              100.0             
IC                Brussels Airport-Zaventem -- Tournai            1167         0.0                        100.0              100.0             
IC                Bruxelles-Midi -- Arlon                         1092         0.0                        100.0              100.0             
IC                Lille Flandres (FR) -- Anvers-Central           1080         0.0                        100.0              100.0             
'''