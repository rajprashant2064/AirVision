

from pathlib import Path

import pandas as pd
import requests


# Project paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"
OUTPUT_FILE = RAW_DATA_DIR / "current_air_quality.csv"

# Open-Meteo Air Quality API
API_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"

# Coordinates for our initial six-city selection
CITIES = {
    "Delhi": {"latitude": 28.6139, "longitude": 77.2090},
    "Mumbai": {"latitude": 19.0760, "longitude": 72.8777},
    "Bengaluru": {"latitude": 12.9716, "longitude": 77.5946},
    "Chennai": {"latitude": 13.0827, "longitude": 80.2707},
    "Kolkata": {"latitude": 22.5726, "longitude": 88.3639},
    "Hyderabad": {"latitude": 17.3850, "longitude": 78.4867},
}

# Hourly variables requested from the API
HOURLY_VARIABLES = [
    "pm2_5",
    "pm10",
    "nitrogen_dioxide",
    "sulphur_dioxide",
    "ozone",
    "carbon_monoxide",
]


def fetch_city_data(city_name, coordinates):
    """Fetch the latest available hourly air-quality measurements."""
    params = {
        "latitude": coordinates["latitude"],
        "longitude": coordinates["longitude"],
        "hourly": ",".join(HOURLY_VARIABLES),
        "past_days": 1,
        "forecast_days": 1,
        "timezone": "Asia/Kolkata",
    }

    response = requests.get(API_URL, params=params, timeout=30)
    response.raise_for_status()
    payload = response.json()

    hourly = payload.get("hourly")
    if not hourly or "time" not in hourly:
        raise ValueError(f"No hourly data returned for {city_name}.")

    timestamps = hourly["time"]
    records = []

    for index, timestamp in enumerate(timestamps):
        record = {
            "city": city_name,
            "measured_at": timestamp,
            "latitude": coordinates["latitude"],
            "longitude": coordinates["longitude"],
        }

        for variable in HOURLY_VARIABLES:
            values = hourly.get(variable, [])
            record[variable] = (
                values[index]
                if index < len(values)
                else None
            )

        records.append(record)

    return records


def main():
    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
    all_records = []

    for city_name, coordinates in CITIES.items():
        try:
            records = fetch_city_data(city_name, coordinates)
            all_records.extend(records)
            print(f"{city_name}: fetched {len(records)} hourly records.")

        except (requests.RequestException, ValueError, KeyError) as error:
            print(f"{city_name}: data retrieval failed: {error}")

    if not all_records:
        raise RuntimeError(
            "No city data was retrieved. Check your internet connection "
            "and the API response before continuing."
        )

    dataframe = pd.DataFrame(all_records)

    # Convert timestamps and validate key fields.
    dataframe["measured_at"] = pd.to_datetime(
        dataframe["measured_at"],
        errors="coerce",
    )

    dataframe = dataframe.dropna(
        subset=["city", "measured_at", "pm2_5"]
    )

    dataframe = dataframe.drop_duplicates(
        subset=["city", "measured_at"]
    )

    dataframe = dataframe.sort_values(
        ["city", "measured_at"]
    )

    dataframe.to_csv(OUTPUT_FILE, index=False)

    print("\nData collection completed.")
    print(f"Valid records: {len(dataframe)}")
    print(f"Saved to: {OUTPUT_FILE}")
    print("\nSample records:")
    print(dataframe.head(10).to_string(index=False))


if __name__ == "__main__":
    main()
