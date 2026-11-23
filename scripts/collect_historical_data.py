

import os
import sys
import logging
from datetime import datetime, timezone

import requests
from sqlalchemy import create_engine, text
from dotenv import load_dotenv


# ---------------------------------------------------------
# 1. PROJECT PATHS AND CONFIGURATION
# ---------------------------------------------------------

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

DATA_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"

TIMEOUT = 30

CITIES = {
    "Delhi": {"latitude": 28.6139, "longitude": 77.2090},
    "Mumbai": {"latitude": 19.0760, "longitude": 72.8777},
    "Bengaluru": {"latitude": 12.9716, "longitude": 77.5946},
    "Chennai": {"latitude": 13.0827, "longitude": 80.2707},
    "Kolkata": {"latitude": 22.5726, "longitude": 88.3639},
    "Hyderabad": {"latitude": 17.3850, "longitude": 78.4867},
}


# ---------------------------------------------------------
# 2. LOGGING
# ---------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger("airvision_collector")


# ---------------------------------------------------------
# 3. DATABASE CONNECTION
# ---------------------------------------------------------

def create_database_engine():
    """
    Reuse the PostgreSQL connection settings in the root .env file.
    Supports either DATABASE_URL or individual DB settings.
    """

    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        host = os.getenv("DB_HOST", "localhost")
        port = os.getenv("DB_PORT", "5432")
        database = os.getenv("DB_NAME", "airvision")
        username = os.getenv("DB_USER")
        password = os.getenv("DB_PASSWORD")

        if not username or not password:
            raise RuntimeError(
                "Database credentials were not found in .env. "
                "Check the DB_HOST, DB_PORT, DB_NAME, DB_USER, "
                "and DB_PASSWORD settings used by your application."
            )

        from urllib.parse import quote_plus

        database_url = (
            f"postgresql+psycopg://{quote_plus(username)}:"
            f"{quote_plus(password)}@{host}:{port}/{database}"
        )

    elif database_url.startswith("postgresql://"):
        database_url = database_url.replace(
            "postgresql://", "postgresql+psycopg://", 1
        )

    return create_engine(
        database_url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 10},
    )


# ---------------------------------------------------------
# 4. CREATE HISTORICAL OBSERVATIONS TABLE
# ---------------------------------------------------------

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS air_quality_observations (
    id BIGSERIAL PRIMARY KEY,
    city VARCHAR(100) NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,

    pm2_5 DOUBLE PRECISION,
    pm10 DOUBLE PRECISION,
    nitrogen_dioxide DOUBLE PRECISION,
    ozone DOUBLE PRECISION,
    carbon_monoxide DOUBLE PRECISION,
    sulphur_dioxide DOUBLE PRECISION,

    temperature_c DOUBLE PRECISION,
    relative_humidity DOUBLE PRECISION,
    wind_speed_kmh DOUBLE PRECISION,
    rainfall_mm DOUBLE PRECISION,

    source VARCHAR(50) NOT NULL DEFAULT 'Open-Meteo',
    collected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_air_quality_city_time
        UNIQUE (city, observed_at)
);
"""


# ---------------------------------------------------------
# 5. API HELPERS
# ---------------------------------------------------------

def get_json(url, params):
    """Fetch JSON from an API and raise a useful error on failure."""

    response = requests.get(
        url,
        params=params,
        timeout=TIMEOUT,
    )

    response.raise_for_status()

    return response.json()


def get_value(series, index):
    """Return a numeric value or None when data is unavailable."""

    if not series or index >= len(series):
        return None

    value = series[index]

    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------
# 6. COLLECT OBSERVATIONS FOR ONE CITY
# ---------------------------------------------------------

def collect_city(engine, city, coordinates):
    latitude = coordinates["latitude"]
    longitude = coordinates["longitude"]

    logger.info("Collecting data for %s", city)

    # Open-Meteo returns hourly air-quality data.
    air = get_json(
        DATA_URL,
        {
            "latitude": latitude,
            "longitude": longitude,
            "hourly": (
                "pm2_5,pm10,nitrogen_dioxide,ozone,"
                "carbon_monoxide,sulphur_dioxide"
            ),
            "past_days": 1,
            "forecast_days": 1,
            "timezone": "UTC",
        },
    )

    # Open-Meteo returns hourly weather data.
    weather = get_json(
        WEATHER_URL,
        {
            "latitude": latitude,
            "longitude": longitude,
            "hourly": (
                "temperature_2m,relative_humidity_2m,"
                "wind_speed_10m,rain"
            ),
            "past_days": 1,
            "forecast_days": 1,
            "timezone": "UTC",
        },
    )

    air_hourly = air.get("hourly", {})
    weather_hourly = weather.get("hourly", {})

    air_times = air_hourly.get("time", [])
    weather_times = weather_hourly.get("time", [])

    weather_index = {
        timestamp: index
        for index, timestamp in enumerate(weather_times)
    }

    records = []

    for index, timestamp in enumerate(air_times):
        # Match weather and pollution by timestamp.
        if timestamp not in weather_index:
            continue

        weather_i = weather_index[timestamp]

        try:
            observed_at = datetime.fromisoformat(timestamp).replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            logger.warning(
                "Skipping invalid timestamp for %s: %s",
                city,
                timestamp,
            )
            continue

        record = {
            "city": city,
            "observed_at": observed_at,

            "pm2_5": get_value(air_hourly.get("pm2_5"), index),
            "pm10": get_value(air_hourly.get("pm10"), index),
            "nitrogen_dioxide": get_value(
                air_hourly.get("nitrogen_dioxide"), index
            ),
            "ozone": get_value(air_hourly.get("ozone"), index),
            "carbon_monoxide": get_value(
                air_hourly.get("carbon_monoxide"), index
            ),
            "sulphur_dioxide": get_value(
                air_hourly.get("sulphur_dioxide"), index
            ),

            "temperature_c": get_value(
                weather_hourly.get("temperature_2m"), weather_i
            ),
            "relative_humidity": get_value(
                weather_hourly.get("relative_humidity_2m"), weather_i
            ),
            "wind_speed_kmh": get_value(
                weather_hourly.get("wind_speed_10m"), weather_i
            ),
            "rainfall_mm": get_value(
                weather_hourly.get("rain"), weather_i
            ),

            "source": "Open-Meteo",
        }

        # Avoid storing completely empty pollution records.
        pollution_fields = (
            "pm2_5",
            "pm10",
            "nitrogen_dioxide",
            "ozone",
            "carbon_monoxide",
            "sulphur_dioxide",
        )

        if all(record[field] is None for field in pollution_fields):
            continue

        records.append(record)

    if not records:
        logger.warning("No usable observations returned for %s", city)
        return 0

    insert_sql = text("""
        INSERT INTO air_quality_observations (
            city,
            observed_at,
            pm2_5,
            pm10,
            nitrogen_dioxide,
            ozone,
            carbon_monoxide,
            sulphur_dioxide,
            temperature_c,
            relative_humidity,
            wind_speed_kmh,
            rainfall_mm,
            source
        )
        VALUES (
            :city,
            :observed_at,
            :pm2_5,
            :pm10,
            :nitrogen_dioxide,
            :ozone,
            :carbon_monoxide,
            :sulphur_dioxide,
            :temperature_c,
            :relative_humidity,
            :wind_speed_kmh,
            :rainfall_mm,
            :source
        )
        ON CONFLICT (city, observed_at)
        DO UPDATE SET
            pm2_5 = EXCLUDED.pm2_5,
            pm10 = EXCLUDED.pm10,
            nitrogen_dioxide = EXCLUDED.nitrogen_dioxide,
            ozone = EXCLUDED.ozone,
            carbon_monoxide = EXCLUDED.carbon_monoxide,
            sulphur_dioxide = EXCLUDED.sulphur_dioxide,
            temperature_c = EXCLUDED.temperature_c,
            relative_humidity = EXCLUDED.relative_humidity,
            wind_speed_kmh = EXCLUDED.wind_speed_kmh,
            rainfall_mm = EXCLUDED.rainfall_mm,
            source = EXCLUDED.source
    """)

    with engine.begin() as connection:
        connection.execute(insert_sql, records)

    logger.info(
        "%s: processed %s hourly records",
        city,
        len(records),
    )

    return len(records)


# ---------------------------------------------------------
# 7. MAIN COLLECTION PROCESS
# ---------------------------------------------------------

def main():
    engine = None

    try:
        engine = create_database_engine()

        # Check the connection and create the table if needed.
        with engine.begin() as connection:
            connection.execute(text("SELECT 1"))
            connection.execute(text(CREATE_TABLE_SQL))

        logger.info("Connected to PostgreSQL successfully.")

        total_processed = 0
        failed_cities = []

        for city, coordinates in CITIES.items():
            try:
                total_processed += collect_city(
                    engine,
                    city,
                    coordinates,
                )
            except Exception as exc:
                failed_cities.append(city)
                logger.exception(
                    "Collection failed for %s: %s",
                    city,
                    exc,
                )

        logger.info(
            "Collection finished. Processed %s records.",
            total_processed,
        )

        if failed_cities:
            logger.error(
                "Failed cities: %s",
                ", ".join(failed_cities),
            )
            sys.exit(1)

    except Exception:
        logger.exception("AirVision collection pipeline failed.")
        sys.exit(1)

    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    main()
