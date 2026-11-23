
"""
AirVision: Hourly weather data collection for six Indian cities.

Features:
1. Fetches hourly weather forecasts from Open-Meteo.
2. Collects temperature, humidity, pressure, wind and rainfall.
3. Validates the returned data.
4. Stores weather observations in PostgreSQL.
5. Avoids duplicate records using the database uniqueness constraint.
6. Displays a summary of records collected for each city.

Run from the project root:
    python scripts/fetch_weather.py
"""

import sys
from pathlib import Path

import pandas as pd
import requests
from sqlalchemy import text

# --------------------------------------------------
# 1. PROJECT PATH AND DATABASE IMPORT
# --------------------------------------------------

# Determine the Air Vision project root.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Allow Python to import modules from the project root.
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.database import engine


# --------------------------------------------------
# 2. API CONFIGURATION
# --------------------------------------------------

API_URL = "https://api.open-meteo.com/v1/forecast"

DATA_SOURCE = "open_meteo_weather"

TIMEZONE = "Asia/Kolkata"

# Fetch recent history and upcoming forecasts.
PAST_DAYS = 2
FORECAST_DAYS = 3

REQUEST_TIMEOUT = 30


# --------------------------------------------------
# 3. CITY CONFIGURATION
# --------------------------------------------------

CITIES = {
    "Delhi": {
        "latitude": 28.6139,
        "longitude": 77.2090,
        "state": "Delhi",
    },
    "Mumbai": {
        "latitude": 19.0760,
        "longitude": 72.8777,
        "state": "Maharashtra",
    },
    "Bengaluru": {
        "latitude": 12.9716,
        "longitude": 77.5946,
        "state": "Karnataka",
    },
    "Chennai": {
        "latitude": 13.0827,
        "longitude": 80.2707,
        "state": "Tamil Nadu",
    },
    "Kolkata": {
        "latitude": 22.5726,
        "longitude": 88.3639,
        "state": "West Bengal",
    },
    "Hyderabad": {
        "latitude": 17.3850,
        "longitude": 78.4867,
        "state": "Telangana",
    },
}


# --------------------------------------------------
# 4. HOURLY WEATHER VARIABLES
# --------------------------------------------------

HOURLY_VARIABLES = [
    "temperature_2m",
    "relative_humidity_2m",
    "surface_pressure",
    "wind_speed_10m",
    "wind_direction_10m",
    "rain",
]

# Map API variable names to PostgreSQL column names.
COLUMN_MAPPING = {
    "temperature_2m": "temperature_c",
    "relative_humidity_2m": "humidity_pct",
    "surface_pressure": "pressure_hpa",
    "wind_speed_10m": "wind_speed_mps",
    "wind_direction_10m": "wind_direction_deg",
    "rain": "rainfall_mm",
}


# --------------------------------------------------
# 5. FETCH WEATHER DATA
# --------------------------------------------------

def fetch_city_weather(city_name, city_info):
    """Fetch hourly weather data for one city."""

    parameters = {
        "latitude": city_info["latitude"],
        "longitude": city_info["longitude"],
        "hourly": ",".join(HOURLY_VARIABLES),
        "past_days": PAST_DAYS,
        "forecast_days": FORECAST_DAYS,
        "timezone": TIMEZONE,
    }

    response = requests.get(
        API_URL,
        params=parameters,
        timeout=REQUEST_TIMEOUT,
    )

    response.raise_for_status()

    payload = response.json()

    hourly = payload.get("hourly")

    if not hourly or "time" not in hourly:
        raise ValueError(
            f"Open-Meteo did not return hourly data for {city_name}."
        )

    timestamps = hourly["time"]

    records = []

    for index, timestamp in enumerate(timestamps):
        record = {
            "city_name": city_name,
            "state_name": city_info["state"],
            "latitude": city_info["latitude"],
            "longitude": city_info["longitude"],
            "observed_at": timestamp,
            "data_source": DATA_SOURCE,
        }

        for api_variable, database_column in COLUMN_MAPPING.items():
            values = hourly.get(api_variable, [])

            if index < len(values):
                record[database_column] = values[index]
            else:
                record[database_column] = None

        records.append(record)

    dataframe = pd.DataFrame(records)

    # Convert timestamps and reject invalid records.
    dataframe["observed_at"] = pd.to_datetime(
        dataframe["observed_at"],
        errors="coerce",
    )

    dataframe = dataframe.dropna(
        subset=["city_name", "observed_at"]
    )

    dataframe = dataframe.drop_duplicates(
        subset=["city_name", "observed_at"]
    )

    # Ensure that at least one weather measurement is present.
    measurement_columns = list(COLUMN_MAPPING.values())

    dataframe = dataframe.dropna(
        subset=measurement_columns,
        how="all",
    )

    # Reject physically invalid values.
    dataframe = dataframe[
        dataframe["humidity_pct"].isna()
        | dataframe["humidity_pct"].between(0, 100)
    ]

    dataframe = dataframe[
        dataframe["wind_speed_mps"].isna()
        | (dataframe["wind_speed_mps"] >= 0)
    ]

    dataframe = dataframe[
        dataframe["rainfall_mm"].isna()
        | (dataframe["rainfall_mm"] >= 0)
    ]

    return dataframe


# --------------------------------------------------
# 6. INSERT WEATHER DATA INTO POSTGRESQL
# --------------------------------------------------

def save_weather_to_database(dataframe):
    """
    Insert weather records into PostgreSQL.

    The cities table must already exist.
    The weather_data table must already exist.
    The weather table's unique constraint prevents duplicate
    city/timestamp/source combinations.
    """

    if dataframe.empty:
        return 0

    insert_city_sql = text(
        """
        INSERT INTO cities (
            city_name,
            state_name,
            country,
            latitude,
            longitude
        )
        VALUES (
            :city_name,
            :state_name,
            'India',
            :latitude,
            :longitude
        )
        ON CONFLICT (city_name, state_name, country)
        DO NOTHING
        """
    )

    get_city_id_sql = text(
        """
        SELECT city_id
        FROM cities
        WHERE city_name = :city_name
          AND state_name = :state_name
          AND country = 'India'
        """
    )

    insert_weather_sql = text(
        """
        INSERT INTO weather_data (
            city_id,
            observed_at,
            temperature_c,
            humidity_pct,
            pressure_hpa,
            wind_speed_mps,
            wind_direction_deg,
            rainfall_mm,
            data_source
        )
        VALUES (
            :city_id,
            :observed_at,
            :temperature_c,
            :humidity_pct,
            :pressure_hpa,
            :wind_speed_mps,
            :wind_direction_deg,
            :rainfall_mm,
            :data_source
        )
        ON CONFLICT (city_id, observed_at, data_source)
        DO NOTHING
        """
    )

    inserted_count = 0

    # A transaction ensures related inserts succeed together.
    with engine.begin() as connection:

        for city_name, city_group in dataframe.groupby("city_name"):

            first_row = city_group.iloc[0]

            city_parameters = {
                "city_name": city_name,
                "state_name": first_row["state_name"],
                "latitude": float(first_row["latitude"]),
                "longitude": float(first_row["longitude"]),
            }

            # Add the city if it is not already registered.
            connection.execute(
                insert_city_sql,
                city_parameters,
            )

            # Obtain its database ID.
            city_result = connection.execute(
                get_city_id_sql,
                {
                    "city_name": city_name,
                    "state_name": first_row["state_name"],
                },
            )

            city_id = city_result.scalar_one_or_none()

            if city_id is None:
                raise RuntimeError(
                    f"Could not find database ID for {city_name}."
                )

            # Insert each hourly weather observation.
            for _, row in city_group.iterrows():

                weather_parameters = {
                    "city_id": city_id,
                    "observed_at": row["observed_at"].to_pydatetime(),
                    "temperature_c": row["temperature_c"],
                    "humidity_pct": row["humidity_pct"],
                    "pressure_hpa": row["pressure_hpa"],
                    "wind_speed_mps": row["wind_speed_mps"],
                    "wind_direction_deg": row["wind_direction_deg"],
                    "rainfall_mm": row["rainfall_mm"],
                    "data_source": row["data_source"],
                }

                result = connection.execute(
                    insert_weather_sql,
                    weather_parameters,
                )

                inserted_count += result.rowcount

    return inserted_count


# --------------------------------------------------
# 7. MAIN EXECUTION
# --------------------------------------------------

def main():

    print("=" * 65)
    print("AIRVISION - HOURLY WEATHER DATA COLLECTION")
    print("=" * 65)

    all_dataframes = []

    # Fetch data from every configured city.
    for city_name, city_info in CITIES.items():

        try:
            city_dataframe = fetch_city_weather(
                city_name,
                city_info,
            )

            all_dataframes.append(city_dataframe)

            print(
                f"{city_name}: "
                f"{len(city_dataframe)} valid hourly records fetched."
            )

        except (
            requests.RequestException,
            ValueError,
            KeyError,
        ) as error:

            print(
                f"{city_name}: Failed to fetch weather data. "
                f"Reason: {error}"
            )

    if not all_dataframes:
        raise RuntimeError(
            "No weather data was collected. "
            "Check your internet connection and Open-Meteo availability."
        )

    combined_dataframe = pd.concat(
        all_dataframes,
        ignore_index=True,
    )

    combined_dataframe = combined_dataframe.sort_values(
        ["city_name", "observed_at"]
    )

    print("\nTotal valid records fetched:", len(combined_dataframe))

    print("\nSaving weather records to PostgreSQL...")

    try:
        inserted_count = save_weather_to_database(
            combined_dataframe
        )

    except Exception as error:
        raise RuntimeError(
            "Failed to save weather data to PostgreSQL. "
            "Verify that the cities and weather_data tables exist "
            "and that their column names and constraints match "
            "the SQL schema."
        ) from error

    print("\n" + "=" * 65)
    print("WEATHER DATA COLLECTION COMPLETED")
    print("=" * 65)

    print(f"Cities processed: {combined_dataframe['city_name'].nunique()}")
    print(f"Records fetched: {len(combined_dataframe)}")
    print(f"New records inserted: {inserted_count}")
    print(
        "Existing records skipped: "
        f"{len(combined_dataframe) - inserted_count}"
    )

    print("\nRecords fetched per city:")

    print(
        combined_dataframe.groupby("city_name")
        .size()
        .to_string()
    )

    print("\nSample weather records:")

    print(
        combined_dataframe[
            [
                "city_name",
                "observed_at",
                "temperature_c",
                "humidity_pct",
                "pressure_hpa",
                "wind_speed_mps",
                "rainfall_mm",
            ]
        ]
        .head(10)
        .to_string(index=False)
    )

    print("\nPostgreSQL storage: successful.")


# --------------------------------------------------
# 8. ENTRY POINT
# --------------------------------------------------

if __name__ == "__main__":

    try:
        main()

    except Exception as error:
        print(f"\nERROR: {error}")
        raise

    finally:
        engine.dispose()
