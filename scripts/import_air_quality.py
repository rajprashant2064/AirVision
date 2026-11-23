

from pathlib import Path
import sys

import pandas as pd
from sqlalchemy import text

# Make the project root importable when this script is run directly.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.database import engine  # noqa: E402


CSV_PATH = PROJECT_ROOT / "data" / "raw" / "current_air_quality.csv"

# The existing CSV does not contain state names.
# These values are used only when creating new city records.
CITY_STATES = {
    "Bengaluru": "Karnataka",
    "Chennai": "Tamil Nadu",
    "Delhi": "Delhi",
    "Hyderabad": "Telangana",
    "Kolkata": "West Bengal",
    "Mumbai": "Maharashtra",
}

DATA_SOURCE = "Open-Meteo"


def load_and_validate_csv() -> pd.DataFrame:
    """Load the CSV and validate its required columns."""

    if not CSV_PATH.exists():
        raise FileNotFoundError(f"CSV file not found: {CSV_PATH}")

    df = pd.read_csv(CSV_PATH)

    required_columns = [
        "city",
        "measured_at",
        "latitude",
        "longitude",
        "pm2_5",
        "pm10",
        "nitrogen_dioxide",
        "sulphur_dioxide",
        "ozone",
        "carbon_monoxide",
    ]

    missing_columns = [
        column for column in required_columns if column not in df.columns
    ]

    if missing_columns:
        raise ValueError(
            f"CSV is missing required columns: {missing_columns}"
        )

    if df.empty:
        raise ValueError("The CSV contains no observations.")

    if df["city"].isna().any():
        raise ValueError("The CSV contains rows without a city name.")

    df["city"] = df["city"].astype(str).str.strip()
    df["measured_at"] = pd.to_datetime(
        df["measured_at"], errors="coerce"
    )

    if df["measured_at"].isna().any():
        raise ValueError("Some measured_at values are invalid.")

    numeric_columns = [
        "latitude",
        "longitude",
        "pm2_5",
        "pm10",
        "nitrogen_dioxide",
        "sulphur_dioxide",
        "ozone",
        "carbon_monoxide",
    ]

    for column in numeric_columns:
        df[column] = pd.to_numeric(df[column], errors="coerce")

    if df.duplicated(["city", "measured_at"]).any():
        raise ValueError(
            "Duplicate city/timestamp observations exist in the CSV."
        )

    pollutant_columns = [
        "pm2_5",
        "pm10",
        "nitrogen_dioxide",
        "sulphur_dioxide",
        "ozone",
        "carbon_monoxide",
    ]

    for column in pollutant_columns:
        invalid = df[column].dropna() < 0
        if invalid.any():
            raise ValueError(
                f"Negative pollutant measurements found in {column}."
            )

    return df


def import_data(df: pd.DataFrame) -> tuple[int, int]:
    """Insert city records and air-quality observations."""

    cities_added = 0
    observations_added = 0

    with engine.begin() as connection:
        # Insert city records only if the city/state/country combination
        # does not already exist.
        for city_name in sorted(df["city"].unique()):
            if city_name not in CITY_STATES:
                raise ValueError(
                    f"No state mapping configured for city: {city_name}"
                )

            city_row = df.loc[df["city"] == city_name].iloc[0]

            result = connection.execute(
                text(
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
                    RETURNING city_id
                    """
                ),
                {
                    "city_name": city_name,
                    "state_name": CITY_STATES[city_name],
                    "latitude": (
                        None if pd.isna(city_row["latitude"])
                        else float(city_row["latitude"])
                    ),
                    "longitude": (
                        None if pd.isna(city_row["longitude"])
                        else float(city_row["longitude"])
                    ),
                },
            )

            if result.fetchone() is not None:
                cities_added += 1

        # Retrieve the canonical city IDs from the database.
        city_rows = connection.execute(
            text(
                """
                SELECT city_id, city_name
                FROM cities
                WHERE country = 'India'
                """
            )
        ).mappings().all()

        city_ids = {
            row["city_name"]: row["city_id"] for row in city_rows
        }

        for row in df.to_dict(orient="records"):
            city_id = city_ids.get(row["city"])

            if city_id is None:
                raise ValueError(
                    f"City not found in database: {row['city']}"
                )

            result = connection.execute(
                text(
                    """
                    INSERT INTO air_quality (
                        city_id,
                        measured_at,
                        pm25,
                        pm10,
                        no2,
                        so2,
                        co,
                        o3,
                        data_source
                    )
                    VALUES (
                        :city_id,
                        :measured_at,
                        :pm25,
                        :pm10,
                        :no2,
                        :so2,
                        :co,
                        :o3,
                        :data_source
                    )
                    ON CONFLICT (city_id, measured_at, data_source)
                    DO NOTHING
                    RETURNING measurement_id
                    """
                ),
                {
                    "city_id": city_id,
                    "measured_at": row["measured_at"].to_pydatetime(),
                    "pm25": (
                        None if pd.isna(row["pm2_5"])
                        else float(row["pm2_5"])
                    ),
                    "pm10": (
                        None if pd.isna(row["pm10"])
                        else float(row["pm10"])
                    ),
                    "no2": (
                        None if pd.isna(row["nitrogen_dioxide"])
                        else float(row["nitrogen_dioxide"])
                    ),
                    "so2": (
                        None if pd.isna(row["sulphur_dioxide"])
                        else float(row["sulphur_dioxide"])
                    ),
                    "co": (
                        None if pd.isna(row["carbon_monoxide"])
                        else float(row["carbon_monoxide"])
                    ),
                    "o3": (
                        None if pd.isna(row["ozone"])
                        else float(row["ozone"])
                    ),
                    "data_source": DATA_SOURCE,
                },
            )

            if result.fetchone() is not None:
                observations_added += 1

    return cities_added, observations_added


def main() -> None:
    """Run the import and print a summary."""

    try:
        print("AirVision: Starting CSV-to-PostgreSQL import...")
        print(f"CSV file: {CSV_PATH}")

        df = load_and_validate_csv()

        print(f"Validated observations: {len(df)}")
        print(f"Cities in CSV: {df['city'].nunique()}")

        cities_added, observations_added = import_data(df)

        print("\nImport completed successfully.")
        print(f"New cities inserted: {cities_added}")
        print(f"New observations inserted: {observations_added}")
        print(
            "Existing observations were skipped if their city, "
            "timestamp, and data source already existed."
        )

    except Exception as error:
        print("\nImport failed. The database transaction was rolled back.")
        print(f"Error: {error}")
        raise

    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
