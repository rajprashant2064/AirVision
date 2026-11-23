CREATE DATABASE Airvision;

SELECT datname
FROM pg_database
WHERE datname = 'Airvision';


-- AirVision database verification

SELECT
    table_name,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'public'
ORDER BY table_name, ordinal_position;
