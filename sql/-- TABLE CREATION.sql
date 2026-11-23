-- TABLE CREATION 


-- 1. CITIES
CREATE TABLE cities (
    city_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    city_name VARCHAR(100) NOT NULL,
    state_name VARCHAR(100) NOT NULL,
    country VARCHAR(100) NOT NULL DEFAULT 'India',
    latitude NUMERIC(9, 6),
    longitude NUMERIC(9, 6),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_cities_location
        UNIQUE (city_name, state_name, country)
);

-- 2. AIR QUALITY OBSERVATIONS
CREATE TABLE air_quality (
    measurement_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    city_id BIGINT NOT NULL REFERENCES cities(city_id),
    measured_at TIMESTAMPTZ NOT NULL,

    pm25 NUMERIC(10, 3),
    pm10 NUMERIC(10, 3),
    no2 NUMERIC(10, 3),
    so2 NUMERIC(10, 3),
    co NUMERIC(10, 3),
    o3 NUMERIC(10, 3),
    nh3 NUMERIC(10, 3),
    aqi INTEGER,

    data_source VARCHAR(100) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_air_quality_source
        UNIQUE (city_id, measured_at, data_source),

    CONSTRAINT chk_pm25_nonnegative
        CHECK (pm25 IS NULL OR pm25 >= 0),

    CONSTRAINT chk_pm10_nonnegative
        CHECK (pm10 IS NULL OR pm10 >= 0),

    CONSTRAINT chk_aqi_nonnegative
        CHECK (aqi IS NULL OR aqi >= 0)
);

-- 3. WEATHER OBSERVATIONS
CREATE TABLE weather_data (
    weather_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    city_id BIGINT NOT NULL REFERENCES cities(city_id),
    observed_at TIMESTAMPTZ NOT NULL,

    temperature_c NUMERIC(6, 2),
    humidity_pct NUMERIC(5, 2),
    pressure_hpa NUMERIC(8, 2),
    wind_speed_mps NUMERIC(7, 2),
    wind_direction_deg NUMERIC(6, 2),
    rainfall_mm NUMERIC(8, 2),

    data_source VARCHAR(100) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_weather_source
        UNIQUE (city_id, observed_at, data_source),

    CONSTRAINT chk_humidity_range
        CHECK (humidity_pct IS NULL OR humidity_pct BETWEEN 0 AND 100),

    CONSTRAINT chk_wind_speed_nonnegative
        CHECK (wind_speed_mps IS NULL OR wind_speed_mps >= 0)
);

-- 4. PM2.5 PREDICTIONS
CREATE TABLE IF NOT EXISTS predictions (
    prediction_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    city_id BIGINT NOT NULL REFERENCES cities(city_id),

    predicted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    forecast_for TIMESTAMPTZ NOT NULL,

    predicted_pm25 NUMERIC(10, 3) NOT NULL,
    model_name VARCHAR(100) NOT NULL,
    model_version VARCHAR(50),

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_predicted_pm25_nonnegative
        CHECK (predicted_pm25 >= 0)
);

-- 5. MACHINE LEARNING MODEL METRICS
CREATE TABLE IF NOT EXISTS model_metrics (
    metric_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    model_name VARCHAR(100) NOT NULL,
    model_version VARCHAR(50),
    target_variable VARCHAR(50) NOT NULL DEFAULT 'PM2.5',

    training_started_at TIMESTAMPTZ,
    training_completed_at TIMESTAMPTZ,
    training_rows INTEGER,

    mae NUMERIC(12, 5),
    rmse NUMERIC(12, 5),
    r2_score NUMERIC(10, 5),

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 6. INDEXES FOR FASTER QUERIES
CREATE INDEX IF NOT EXISTS idx_air_quality_city_time
    ON air_quality (city_id, measured_at DESC);

CREATE INDEX IF NOT EXISTS idx_weather_city_time
    ON weather_data (city_id, observed_at DESC);

CREATE INDEX IF NOT EXISTS idx_predictions_city_forecast
    ON predictions (city_id, forecast_for DESC);

CREATE INDEX IF NOT EXISTS idx_model_metrics_name
    ON model_metrics (model_name, created_at DESC);