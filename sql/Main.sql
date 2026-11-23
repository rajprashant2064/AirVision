SELECT current_database();

SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_type = 'BASE TABLE'
ORDER BY table_name;

INSERT INTO cities (
    city_name,
    state_name,
    latitude,
    longitude
)
VALUES
    ('Delhi', 'Delhi', 28.613900, 77.209000),
    ('Mumbai', 'Maharashtra', 19.076000, 72.877700),
    ('Bengaluru', 'Karnataka', 12.971600, 77.594600),
    ('Chennai', 'Tamil Nadu', 13.082700, 80.270700),
    ('Kolkata', 'West Bengal', 22.572600, 88.363900),
    ('Hyderabad', 'Telangana', 17.385000, 78.486700)
ON CONFLICT (city_name, state_name, country) DO NOTHING;

SELECT
    city_id,
    city_name,
    state_name,
    latitude,
    longitude
FROM cities
ORDER BY city_id;

SELECT
    (SELECT COUNT(*) FROM cities) AS total_cities,
    (SELECT COUNT(*) FROM air_quality) AS air_quality_records,
    (SELECT COUNT(*) FROM weather_data) AS weather_records,
    (SELECT COUNT(*) FROM predictions) AS prediction_records,
    (SELECT COUNT(*) FROM model_metrics) AS model_evaluations;


	--Confirming database table structures
	SELECT
    table_name,
    column_name,
    data_type,
    is_nullable
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name IN (
      'cities',
      'air_quality',
      'weather_data',
      'predictions',
      'model_metrics'
  )
ORDER BY
    table_name,
    ordinal_position;


	--Database Verification
	-- AirVision database verification

SELECT
    table_name,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'public'
ORDER BY table_name, ordinal_position;



SELECT
    current_database() AS database_name,
    current_user AS connected_user,
    NOW() AS server_time;




	SELECT 'cities' AS table_name, COUNT(*) AS total_records
FROM cities

UNION ALL

SELECT 'air_quality', COUNT(*)
FROM air_quality

UNION ALL

SELECT 'weather_data', COUNT(*)
FROM weather_data

UNION ALL

SELECT 'predictions', COUNT(*)
FROM predictions

UNION ALL

SELECT 'model_metrics', COUNT(*)
FROM model_metrics;


SELECT *
FROM cities
ORDER BY city_id;


SELECT
    table_name,
    COUNT(*) AS column_count
FROM information_schema.columns
WHERE table_schema = 'public'
GROUP BY table_name
ORDER BY table_name;


SELECT
    table_name
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_type = 'BASE TABLE'
ORDER BY table_name;


SELECT 'cities' AS table_name, COUNT(*) AS total_records FROM cities
UNION ALL
SELECT 'air_quality', COUNT(*) FROM air_quality
UNION ALL
SELECT 'weather_data', COUNT(*) FROM weather_data
UNION ALL
SELECT 'predictions', COUNT(*) FROM predictions
UNION ALL
SELECT 'model_metrics', COUNT(*) FROM model_metrics;


SELECT
    table_name,
    column_name,
    data_type,
    is_nullable
FROM information_schema.columns
WHERE table_schema = 'public'
ORDER BY table_name, ordinal_position;




SELECT
    table_name,
    COUNT(*) AS total_columns
FROM information_schema.columns
WHERE table_schema = 'public'
GROUP BY table_name
ORDER BY table_name;


SELECT
    c.city_name,
    COUNT(a.measurement_id) AS observation_count,
    MIN(a.measured_at) AS first_measurement,
    MAX(a.measured_at) AS last_measurement
FROM cities AS c
LEFT JOIN air_quality AS a
    ON c.city_id = a.city_id
GROUP BY c.city_name
ORDER BY c.city_name;

SELECT
    c.city_name,
    COUNT(a.measurement_id) AS total_records,
    ROUND(AVG(a.pm25), 2) AS average_pm25,
    ROUND(MIN(a.pm25), 2) AS minimum_pm25,
    ROUND(MAX(a.pm25), 2) AS maximum_pm25,
    MIN(a.measured_at) AS first_measurement,
    MAX(a.measured_at) AS last_measurement
FROM cities AS c
LEFT JOIN air_quality AS a
    ON c.city_id = a.city_id
GROUP BY c.city_name
ORDER BY c.city_name;


SELECT
    c.city_name,
    COUNT(a.measurement_id) AS total_records,
    ROUND(AVG(a.pm25), 2) AS average_pm25,
    ROUND(MIN(a.pm25), 2) AS minimum_pm25,
    ROUND(MAX(a.pm25), 2) AS maximum_pm25,
    MAX(a.measured_at) AS latest_measurement
FROM cities AS c
LEFT JOIN air_quality AS a
    ON c.city_id = a.city_id
GROUP BY c.city_name
ORDER BY c.city_name;



SELECT
    c.city_name,
    COUNT(w.weather_id) AS total_weather_records,
    ROUND(AVG(w.temperature_c), 2) AS avg_temperature_c,
    ROUND(AVG(w.humidity_pct), 2) AS avg_humidity_pct,
    ROUND(AVG(w.wind_speed_mps), 2) AS avg_wind_speed_mps,
    MIN(w.observed_at) AS first_observation,
    MAX(w.observed_at) AS last_observation
FROM cities AS c
LEFT JOIN weather_data AS w
    ON c.city_id = w.city_id
GROUP BY c.city_name
ORDER BY c.city_name;



SELECT
    c.city_name,
    a.measured_at,
    a.pm25,
    a.pm10,
    a.no2,
    a.so2,
    a.o3,
    a.co,
    w.temperature_c,
    w.humidity_pct,
    w.pressure_hpa,
    w.wind_speed_mps,
    w.rainfall_mm
FROM cities AS c
JOIN air_quality AS a
    ON c.city_id = a.city_id
LEFT JOIN weather_data AS w
    ON w.city_id = a.city_id
   AND w.observed_at = a.measured_at
ORDER BY
    c.city_name,
    a.measured_at DESC
LIMIT 20;



SELECT
    c.city_name,
    COUNT(a.measurement_id) AS air_quality_records,
    COUNT(w.weather_id) AS matching_weather_records,
    COUNT(a.measurement_id) - COUNT(w.weather_id)
        AS unmatched_air_quality_records
FROM cities AS c
LEFT JOIN air_quality AS a
    ON a.city_id = c.city_id
LEFT JOIN weather_data AS w
    ON w.city_id = a.city_id
   AND w.observed_at = a.measured_at
GROUP BY c.city_name
ORDER BY c.city_name;

-- List all public tables in the AirVision database.
SELECT
    table_name
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_type = 'BASE TABLE'
ORDER BY table_name;

-- Check how many records are available in each table.
SELECT
    'air_quality' AS table_name,
    COUNT(*) AS total_records
FROM air_quality

UNION ALL

SELECT
    'weather_data' AS table_name,
    COUNT(*) AS total_records
FROM weather_data

UNION ALL

SELECT
    'cities' AS table_name,
    COUNT(*) AS total_records
FROM cities;






SELECT
    city,
    COUNT(*) AS observation_count,
    MIN(observed_at) AS first_observation,
    MAX(observed_at) AS last_observation
FROM air_quality_observations
GROUP BY city
ORDER BY city;



SELECT
    city,
    observed_at,
    pm2_5,
    pm10,
    temperature_c,
    relative_humidity,
    source
FROM air_quality_observations
ORDER BY observed_at DESC
LIMIT 20;



SELECT
    COUNT(*) AS total_records,
    COUNT(DISTINCT city) AS total_cities,
    COUNT(DISTINCT observed_at) AS distinct_timestamps,
    COUNT(pm2_5) AS records_with_pm25,
    MIN(observed_at) AS earliest_record,
    MAX(observed_at) AS latest_record
FROM air_quality_observations;


SELECT
    c.city_name,
    w.observed_at,
    w.data_source
FROM weather_data AS w
JOIN cities AS c
    ON c.city_id = w.city_id
WHERE w.observed_at > NOW()
ORDER BY w.observed_at DESC;


SELECT
    NOW() AS database_current_time,
    MAX(observed_at) AS latest_weather_time,
    MIN(observed_at) AS earliest_weather_time,
    COUNT(*) AS total_records,
    COUNT(*) FILTER (
        WHERE observed_at > NOW()
    ) AS future_records
FROM weather_data;


SELECT DISTINCT ON (c.city_name)
    c.city_name,
    w.observed_at,
    w.temperature_c,
    w.humidity_pct,
    w.wind_speed_mps,
    w.data_source
FROM weather_data AS w
JOIN cities AS c
    ON c.city_id = w.city_id
WHERE w.observed_at <= NOW()
ORDER BY c.city_name, w.observed_at DESC;