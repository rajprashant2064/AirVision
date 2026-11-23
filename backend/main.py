"""
AirVision - Intelligent Air Pollution Prediction and Analytics Platform
FastAPI backend, PostgreSQL queries, prediction endpoint, and frontend serving.
"""

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
import math
import traceback

import joblib
import pandas as pd

import requests
from fastapi import Body

from backend.provider_config import (
    get_public_config,
    load_config,
    save_config,
    test_provider,
)

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from backend.database import engine


# =========================================================
# PROJECT PATHS
# =========================================================

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"


if not FRONTEND_DIR.is_dir():
    raise RuntimeError(f"Frontend directory not found: {FRONTEND_DIR}")

if not (FRONTEND_DIR / "index.html").is_file():
    raise RuntimeError("frontend/index.html was not found.")


# =========================================================
# FASTAPI APPLICATION
# =========================================================

app = FastAPI(
    title="AirVision API",
    description="Air quality, weather, analytics, and prediction for Indian cities.",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve frontend assets at /static/style.css and /static/script.js.
app.mount(
    "/static",
    StaticFiles(directory=str(FRONTEND_DIR)),
    name="static",
)


# =========================================================
# DATABASE HELPERS
# =========================================================

def execute_query(
    query: str,
    parameters: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Execute a SELECT query and return mapping rows."""

    try:
        with engine.connect() as connection:
            result = connection.execute(text(query), parameters or {})
            return [dict(row) for row in result.mappings().all()]

    except SQLAlchemyError as error:
        print("\n[AIRVISION DATABASE QUERY ERROR]")
        traceback.print_exc()

        # Keep detailed database errors in the server terminal.
        raise HTTPException(
            status_code=500,
            detail="Database query failed. Check the AirVision API terminal.",
        ) from error


def serialize_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert database values into JSON-compatible values."""

    output = []

    for record in records:
        converted = {}

        for key, value in record.items():
            if isinstance(value, (datetime, date)):
                converted[key] = value.isoformat()

            elif isinstance(value, Decimal):
                converted[key] = float(value)

            else:
                converted[key] = value

        output.append(converted)

    return output


def success_response(
    records: list[dict[str, Any]],
    data_key: str = "data",
) -> dict[str, Any]:
    return {
        "count": len(records),
        data_key: serialize_records(records),
    }


# =========================================================
# FRONTEND
# =========================================================

@app.get("/", include_in_schema=False)
def dashboard():
    """Open the AirVision dashboard in the browser."""
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/style.css", include_in_schema=False)
def frontend_stylesheet():
    """Serve the stylesheet using the path already referenced by index.html."""
    return FileResponse(FRONTEND_DIR / "style.css", media_type="text/css")


@app.get("/script.js", include_in_schema=False)
def frontend_javascript():
    """Serve the dashboard JavaScript using the path referenced by index.html."""
    return FileResponse(FRONTEND_DIR / "script.js", media_type="application/javascript")


# =========================================================
# API STATUS
# =========================================================

@app.get("/api/health")
def health_check():
    try:
        with engine.connect() as connection:
            database_name = connection.execute(
                text("SELECT current_database()")
            ).scalar_one()

        return {
            "api_status": "healthy",
            "database_status": "connected",
            "database": database_name,
            "version": "2.0.0",
        }

    except SQLAlchemyError as error:
        print("\n[AIRVISION HEALTH CHECK ERROR]")
        traceback.print_exc()

        raise HTTPException(
            status_code=503,
            detail="Database connection is unavailable.",
        ) from error


# =========================================================
# CITIES
# =========================================================

@app.get("/api/cities")
def get_cities():
    query = """
        SELECT city_id, city_name, state_name, country, latitude, longitude
        FROM cities
        ORDER BY city_name;
    """

    records = execute_query(query)
    return success_response(records, "cities")


# =========================================================
# LATEST AIR QUALITY
# =========================================================

@app.get("/api/air-quality/latest")
def get_latest_air_quality(
    city: str | None = Query(default=None, description="Optional city name"),
):
    query = """
        SELECT DISTINCT ON (c.city_id)
            c.city_id,
            c.city_name,
            a.measured_at,
            a.pm25,
            a.pm10,
            a.no2,
            a.so2,
            a.co,
            a.o3,
            a.nh3,
            a.aqi,
            a.data_source
        FROM cities AS c
        JOIN air_quality AS a ON a.city_id = c.city_id
        WHERE (
            CAST(:city AS TEXT) IS NULL
            OR LOWER(c.city_name) = LOWER(CAST(:city AS TEXT))
        )
        ORDER BY c.city_id, a.measured_at DESC;
    """

    records = execute_query(query, {"city": city})

    if city and not records:
        raise HTTPException(
            status_code=404,
            detail=f"No air-quality data found for {city}.",
        )

    return success_response(records)


# =========================================================
# AIR QUALITY HISTORY
# =========================================================

@app.get("/api/air-quality/history")
def get_air_quality_history(
    city: str = Query(..., description="City name, for example Delhi"),
    limit: int = Query(default=48, ge=1, le=500),
):
    query = """
        SELECT
            c.city_id,
            c.city_name,
            a.measured_at,
            a.pm25,
            a.pm10,
            a.no2,
            a.so2,
            a.co,
            a.o3,
            a.aqi
        FROM cities AS c
        JOIN air_quality AS a ON a.city_id = c.city_id
        WHERE LOWER(c.city_name) = LOWER(:city)
        ORDER BY a.measured_at DESC
        LIMIT :limit;
    """

    records = execute_query(query, {"city": city, "limit": limit})

    if not records:
        raise HTTPException(
            status_code=404,
            detail=f"No air-quality history found for {city}.",
        )

    # Return the records in chronological order for charts.
    records.reverse()

    return {
        "city": city,
        "count": len(records),
        "data": serialize_records(records),
    }


# =========================================================
# EXPERIMENTAL CPCB-STYLE AQI ESTIMATE
# =========================================================

# Breakpoints: (concentration_low, concentration_high, subindex_low, subindex_high)
# PM2.5, PM10, NO2, SO2 and O3 are in µg/m³; CO is in mg/m³.
AQI_BREAKPOINTS = {
    "PM2.5": [
        (0, 30, 0, 50), (31, 60, 51, 100), (61, 90, 101, 200),
        (91, 120, 201, 300), (121, 250, 301, 400), (251, 500, 401, 500),
    ],
    "PM10": [
        (0, 50, 0, 50), (51, 100, 51, 100), (101, 250, 101, 200),
        (251, 350, 201, 300), (351, 430, 301, 400), (431, 600, 401, 500),
    ],
    "NO2": [
        (0, 40, 0, 50), (41, 80, 51, 100), (81, 180, 101, 200),
        (181, 280, 201, 300), (281, 400, 301, 400), (401, 1000, 401, 500),
    ],
    "SO2": [
        (0, 40, 0, 50), (41, 80, 51, 100), (81, 380, 101, 200),
        (381, 800, 201, 300), (801, 1600, 301, 400), (1601, 2000, 401, 500),
    ],
    "CO": [
        (0, 1.0, 0, 50), (1.1, 2.0, 51, 100), (2.1, 10.0, 101, 200),
        (10.1, 17.0, 201, 300), (17.1, 34.0, 301, 400), (34.1, 50.0, 401, 500),
    ],
    "O3": [
        (0, 50, 0, 50), (51, 100, 51, 100), (101, 168, 101, 200),
        (169, 208, 201, 300), (209, 748, 301, 400), (749, 1000, 401, 500),
    ],
}


def calculate_pollutant_subindex(pollutant: str, concentration: float) -> int | None:
    """Calculate an AQI sub-index by linear interpolation."""
    if not math.isfinite(concentration) or concentration < 0:
        return None

    breakpoints = AQI_BREAKPOINTS.get(pollutant, [])
    for low_c, high_c, low_i, high_i in breakpoints:
        if low_c <= concentration <= high_c:
            value = ((high_i - low_i) / (high_c - low_c)) * (
                concentration - low_c
            ) + low_i
            return max(0, min(500, round(value)))

    # Out-of-range concentrations map to the top of the scale.
    if breakpoints and concentration > breakpoints[-1][1]:
        return 500
    return None


def get_aqi_category(aqi: int) -> str:
    """Return the Indian National AQI category label."""
    if aqi <= 50:
        return "Good"
    if aqi <= 100:
        return "Satisfactory"
    if aqi <= 200:
        return "Moderate"
    if aqi <= 300:
        return "Poor"
    if aqi <= 400:
        return "Very Poor"
    return "Severe"


@app.get("/api/air-quality/aqi")
def estimate_city_aqi(
    city: str = Query(..., description="City name, for example Delhi"),
):
    """
    Return an experimental CPCB-style AQI estimate based on recent stored data.

    This is not an official CPCB AQI. The provider data may be modelled,
    and the available hourly data may not satisfy official averaging rules.
    """
    query = """
        SELECT
            c.city_id,
            c.city_name,
            a.measured_at,
            a.pm25,
            a.pm10,
            a.no2,
            a.so2,
            a.co,
            a.o3
        FROM cities AS c
        JOIN air_quality AS a ON a.city_id = c.city_id
        WHERE LOWER(c.city_name) = LOWER(:city)
          AND a.measured_at >= NOW() - INTERVAL '24 hours'
        ORDER BY a.measured_at ASC;
    """
    records = execute_query(query, {"city": city})

    if not records:
        raise HTTPException(
            status_code=404,
            detail=f"No air-quality data found for {city} in the last 24 hours.",
        )

    if len(records) < 16:
        raise HTTPException(
            status_code=422,
            detail=(
                f"At least 16 observations in the last 24 hours are needed "
                f"for this experimental AQI estimate. Found {len(records)}."
            ),
        )

    def valid_values(rows: list[dict[str, Any]], key: str) -> list[float]:
        values = []
        for row in rows:
            value = row.get(key)
            if value is None:
                continue
            try:
                number = float(value)
            except (TypeError, ValueError):
                continue
            if math.isfinite(number) and number >= 0:
                values.append(number)
        return values

    # Approximate the available averaging windows using the stored hourly rows.
    pollutant_averages: dict[str, float] = {}
    for pollutant, column in (
        ("PM2.5", "pm25"),
        ("PM10", "pm10"),
        ("NO2", "no2"),
        ("SO2", "so2"),
    ):
        values = valid_values(records, column)
        if values:
            pollutant_averages[pollutant] = sum(values) / len(values)

    # CO and O3 use the most recent eight observations as an approximation
    # of an 8-hour average when the data is hourly.
    recent_eight = records[-8:]
    co_values = valid_values(recent_eight, "co")
    if co_values:
        # Open-Meteo reports CO in µg/m³; convert to mg/m³ for the breakpoint table.
        pollutant_averages["CO"] = (sum(co_values) / len(co_values)) / 1000.0

    o3_values = valid_values(recent_eight, "o3")
    if o3_values:
        pollutant_averages["O3"] = sum(o3_values) / len(o3_values)

    sub_indices: dict[str, int] = {}
    for pollutant, concentration in pollutant_averages.items():
        subindex = calculate_pollutant_subindex(pollutant, concentration)
        if subindex is not None:
            sub_indices[pollutant] = subindex

    if len(sub_indices) < 3 or not ({"PM2.5", "PM10"} & set(sub_indices)):
        raise HTTPException(
            status_code=422,
            detail=(
                "AQI could not be estimated: at least three valid pollutant "
                "sub-indices, including PM2.5 or PM10, are required."
            ),
        )

    overall_aqi = max(sub_indices.values())
    dominant_pollutant = max(sub_indices, key=sub_indices.get)

    return {
        "city": records[-1]["city_name"],
        "aqi": overall_aqi,
        "category": get_aqi_category(overall_aqi),
        "dominant_pollutant": dominant_pollutant,
        "pollutant_sub_indices": sub_indices,
        "pollutant_averages": {
            key: round(value, 2) for key, value in pollutant_averages.items()
        },
        "observations_used": len(records),
        "averaging_note": (
            "Uses stored observations from the last 24 hours; CO and O3 use "
            "up to the latest 8 observations. This is an approximation."
        ),
        "status": "experimental_estimate",
        "note": (
            "Not an official CPCB AQI or a health advisory. Data sources and "
            "averaging windows may differ from CPCB monitoring requirements."
        ),
    }




# =========================================================
# LATEST WEATHER
# =========================================================

@app.get("/api/weather/latest")
def get_latest_weather(
    city: str | None = Query(default=None, description="Optional city name"),
):
    query = """
        SELECT DISTINCT ON (c.city_id)
            c.city_id,
            c.city_name,
            w.observed_at,
            w.temperature_c,
            w.humidity_pct,
            w.pressure_hpa,
            w.wind_speed_mps,
            w.wind_direction_deg,
            w.rainfall_mm AS rain_mm,
            w.data_source
        FROM cities AS c
        JOIN weather_data AS w ON w.city_id = c.city_id
        WHERE (
            CAST(:city AS TEXT) IS NULL
            OR LOWER(c.city_name) = LOWER(CAST(:city AS TEXT))
        )
          AND w.observed_at <= NOW()
        ORDER BY c.city_id, w.observed_at DESC;
    """

    records = execute_query(query, {"city": city})

    if city and not records:
        raise HTTPException(
            status_code=404,
            detail=f"No weather data found for {city}.",
        )

    return success_response(records)


# =========================================================
# ANALYTICS SUMMARY
# =========================================================

@app.get("/api/analytics/summary")
def get_analytics_summary():
    query = """
        SELECT
            c.city_name,
            COUNT(a.measurement_id) AS total_records,
            ROUND(AVG(a.pm25)::numeric, 2) AS average_pm25,
            ROUND(MIN(a.pm25)::numeric, 2) AS minimum_pm25,
            ROUND(MAX(a.pm25)::numeric, 2) AS maximum_pm25,
            MAX(a.measured_at) AS latest_measurement
        FROM cities AS c
        LEFT JOIN air_quality AS a ON a.city_id = c.city_id
        GROUP BY c.city_id, c.city_name
        ORDER BY c.city_name;
    """

    records = execute_query(query)
    return success_response(records, "summary")


# =========================================================
# TRAINED RANDOM FOREST: ONE-HOUR-AHEAD PM2.5 PREDICTION
# =========================================================

@app.get("/api/predictions")
def predict_pm25(
    city: str = Query(..., description="City name, for example Delhi"),
):
    """
    Predict PM2.5 one hour ahead using the trained Random Forest model.

    This endpoint reads air_quality_observations, which is the table used
    to train the model. The existing air_quality table and other API routes
    remain unchanged.
    """
    model_path = BASE_DIR / "model" / "pm25_prediction_model.joblib"

    if not model_path.is_file():
        raise HTTPException(
            status_code=503,
            detail=(
                "The trained PM2.5 model was not found. "
                "Run scripts/training_prediction_model.py first."
            ),
        )

    # Fetch the latest four hourly rows: current row plus three PM2.5 lags.
    query = """
        SELECT
            city,
            observed_at,
            pm2_5,
            pm10,
            temperature_c,
            relative_humidity
        FROM air_quality_observations
        WHERE LOWER(city) = LOWER(:city)
        ORDER BY observed_at DESC
        LIMIT 4;
    """
    records = execute_query(query, {"city": city})
    records.reverse()

    if len(records) < 4:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Four hourly observations are required to forecast PM2.5 "
                f"for {city}. Collect more data and try again."
            ),
        )

    # Ensure the four rows are consecutive hourly records.
    timestamps = [record.get("observed_at") for record in records]
    if any(timestamp is None for timestamp in timestamps):
        raise HTTPException(
            status_code=422,
            detail=f"Some observation timestamps are missing for {city}.",
        )

    for previous, current in zip(timestamps, timestamps[1:]):
        if current - previous != pd.Timedelta(hours=1):
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Four consecutive hourly observations are required "
                    f"for {city}; the stored data has a time gap."
                ),
            )

    current = records[-1]
    lag_rows = records[-2::-1]  # Previous hour, two hours ago, three hours ago.

    try:
        lag_values = [float(row["pm2_5"]) for row in lag_rows]
        latest_pm25 = float(current["pm2_5"])
    except (TypeError, ValueError, KeyError):
        raise HTTPException(
            status_code=422,
            detail=f"PM2.5 values are missing or invalid for {city}.",
        )

    issue_time = current["observed_at"]
    features = {
        "city": str(current["city"]),
        "hour": issue_time.hour,
"day_of_week": issue_time.weekday(),
        "month": issue_time.month,
        "pm2_5_lag_1": lag_values[0],
        "pm2_5_lag_2": lag_values[1],
        "pm2_5_lag_3": lag_values[2],
        "pm10": current.get("pm10"),
        "temperature_c": current.get("temperature_c"),
        "relative_humidity": current.get("relative_humidity"),
    }

    try:
        artifact = joblib.load(model_path)
        trained_model = artifact["model"]
        feature_names = artifact.get("input_features", list(features.keys()))
        model_input = pd.DataFrame([features], columns=feature_names)
        prediction = float(trained_model.predict(model_input)[0])
    except (OSError, ValueError, KeyError, TypeError) as error:
        print("\n[AIRVISION MODEL LOAD/PREDICTION ERROR]")
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail="The trained prediction model could not be loaded or used.",
        ) from error
    except Exception as error:
        print("\n[AIRVISION MODEL PREDICTION ERROR]")
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail="Prediction failed. Check the AirVision API terminal.",
        ) from error

    if not math.isfinite(prediction):
        raise HTTPException(
            status_code=500,
            detail="The model returned an invalid PM2.5 prediction.",
        )

    # Concentration cannot be negative.
    prediction = max(0.0, prediction)

    return {
        "city": current["city"],
        "pollutant": "PM2.5",
        "model": "Random Forest (one-hour-ahead)",
        "forecast_horizon_hours": 1,
        "latest_pm25": round(latest_pm25, 2),
        "estimated_next_pm25": round(prediction, 2),
        "forecast_for": (issue_time + pd.Timedelta(hours=1)).isoformat(),
        "trend_per_observation": round(prediction - latest_pm25, 2),
        "observations_used": 4,
        "metrics": artifact.get("metrics", {}),
        "note": (
            "Experimental one-hour-ahead estimate. Evaluation used a small "
            "dataset and should not be treated as a regulatory or health forecast."
        ),
    }


# =========================================================
# API PROVIDER CONFIGURATION
# =========================================================

@app.get("/api/settings/provider")
def read_provider_settings():
    """Return the selected provider and a masked key only."""
    return get_public_config()


@app.post("/api/settings/provider")
def update_provider_settings(payload: dict[str, Any] = Body(...)):
    """Save provider settings locally; never return the full API key."""
    provider = str(payload.get("provider", "")).strip().lower()
    api_key = payload.get("api_key")

    if api_key is not None and not isinstance(api_key, str):
        raise HTTPException(status_code=400, detail="API key must be text.")

    try:
        return save_config(provider, api_key)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except OSError as error:
        raise HTTPException(
            status_code=500,
            detail="Could not save local provider settings.",
        ) from error


@app.post("/api/settings/test")
def check_provider_connection(payload: dict[str, Any] = Body(...)):
    """Test a provider using the submitted key, if supplied."""
    provider = str(payload.get("provider", "")).strip().lower()
    api_key = payload.get("api_key")

    if api_key is not None and not isinstance(api_key, str):
        raise HTTPException(status_code=400, detail="API key must be text.")

    return test_provider(provider, api_key)


def get_city_locations(city: str | None = None) -> list[dict[str, Any]]:
    """Read city coordinates from PostgreSQL for provider API requests."""
    query = """
        SELECT city_id, city_name, state_name, country, latitude, longitude
        FROM cities
        WHERE (CAST(:city AS TEXT) IS NULL
               OR LOWER(city_name) = LOWER(CAST(:city AS TEXT)))
        ORDER BY city_name;
    """
    records = execute_query(query, {"city": city})
    if city and not records:
        raise HTTPException(status_code=404, detail=f"City not found: {city}")
    return records


def fetch_live_air_quality(city_record: dict[str, Any]) -> dict[str, Any]:
    """Fetch current air-quality data from the currently selected provider."""
    config = load_config()
    provider = config["provider"]
    lat = float(city_record["latitude"])
    lon = float(city_record["longitude"])

    try:
        if provider == "open_meteo":
            response = requests.get(
                "https://air-quality-api.open-meteo.com/v1/air-quality",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": (
                        "pm2_5,pm10,nitrogen_dioxide,sulphur_dioxide,"
                        "carbon_monoxide,ozone,ammonia,us_aqi"
                    ),
                    "timezone": "Asia/Kolkata",
                },
                timeout=15,
            )
            response.raise_for_status()
            result = response.json()
            current = result.get("current", {})
            return {
                "city_id": city_record["city_id"],
                "city_name": city_record["city_name"],
                "measured_at": current.get("time"),
                "pm25": current.get("pm2_5"),
                "pm10": current.get("pm10"),
                "no2": current.get("nitrogen_dioxide"),
                "so2": current.get("sulphur_dioxide"),
                "co": current.get("carbon_monoxide"),
                "o3": current.get("ozone"),
                "nh3": current.get("ammonia"),
                "aqi": current.get("us_aqi"),
                "aqi_scale": "US AQI",
                "data_source": "Open-Meteo",
                "provider": provider,
            }

        response = requests.get(
            "https://api.openweathermap.org/data/2.5/air_pollution",
            params={"lat": lat, "lon": lon, "appid": config["openweather_api_key"]},
            timeout=15,
        )
        response.raise_for_status()
        result = response.json()
        item = (result.get("list") or [{}])[0]
        components = item.get("components", {})
        timestamp = item.get("dt")
        observed = datetime.fromtimestamp(timestamp).astimezone().isoformat() if timestamp else None
        return {
            "city_id": city_record["city_id"],
            "city_name": city_record["city_name"],
            "measured_at": observed,
            "pm25": components.get("pm2_5"),
            "pm10": components.get("pm10"),
            "no2": components.get("no2"),
            "so2": components.get("so2"),
            "co": components.get("co"),
            "o3": components.get("o3"),
            "nh3": components.get("nh3"),
            # OpenWeather's AQI is a 1-5 category, not the same as US AQI.
            "aqi": item.get("main", {}).get("aqi"),
            "aqi_scale": "OpenWeather 1-5 category",
            "data_source": "OpenWeather",
            "provider": provider,
        }

    except requests.HTTPError as error:
        status = error.response.status_code if error.response is not None else 502
        if status == 401:
            detail = "Provider rejected the API key or account access. Check the key and activation."
        elif status == 429:
            detail = "Provider rate limit reached. Try again later."
        else:
            detail = f"Air-quality provider returned HTTP {status}."
        raise HTTPException(status_code=502, detail=detail) from error
    except requests.RequestException as error:
        raise HTTPException(status_code=502, detail="Could not reach the air-quality provider.") from error


def fetch_live_weather(city_record: dict[str, Any]) -> dict[str, Any]:
    """Fetch current weather from the currently selected provider."""
    config = load_config()
    provider = config["provider"]
    lat = float(city_record["latitude"])
    lon = float(city_record["longitude"])

    try:
        if provider == "open_meteo":
            response = requests.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": (
                        "temperature_2m,relative_humidity_2m,pressure_msl,"
                        "wind_speed_10m,wind_direction_10m,rain"
                    ),
                    "timezone": "Asia/Kolkata",
                },
                timeout=15,
            )
            response.raise_for_status()
            result = response.json()
            current = result.get("current", {})
            return {
                "city_id": city_record["city_id"],
                "city_name": city_record["city_name"],
                "observed_at": current.get("time"),
                "temperature_c": current.get("temperature_2m"),
                "humidity_pct": current.get("relative_humidity_2m"),
                "pressure_hpa": current.get("pressure_msl"),
                "wind_speed_mps": (
                    float(current["wind_speed_10m"]) / 3.6
                    if current.get("wind_speed_10m") is not None else None
                ),
                "wind_direction_deg": current.get("wind_direction_10m"),
                "rain_mm": current.get("rain"),
                "data_source": "Open-Meteo",
                "provider": provider,
            }

        response = requests.get(
            "https://api.openweathermap.org/data/2.5/weather",
            params={"lat": lat, "lon": lon, "appid": config["openweather_api_key"], "units": "metric"},
            timeout=15,
        )
        response.raise_for_status()
        result = response.json()
        main = result.get("main", {})
        wind = result.get("wind", {})
        timestamp = result.get("dt")
        observed = datetime.fromtimestamp(timestamp).astimezone().isoformat() if timestamp else None
        return {
            "city_id": city_record["city_id"],
            "city_name": city_record["city_name"],
            "observed_at": observed,
            "temperature_c": main.get("temp"),
            "humidity_pct": main.get("humidity"),
            "pressure_hpa": main.get("pressure"),
            "wind_speed_mps": wind.get("speed"),
            "wind_direction_deg": wind.get("deg"),
            "rain_mm": (result.get("rain") or {}).get("1h", 0),
            "data_source": "OpenWeather",
            "provider": provider,
        }

    except requests.HTTPError as error:
        status = error.response.status_code if error.response is not None else 502
        if status == 401:
            detail = "Provider rejected the API key or account access. Check the key and activation."
        elif status == 429:
            detail = "Provider rate limit reached. Try again later."
        else:
            detail = f"Weather provider returned HTTP {status}."
        raise HTTPException(status_code=502, detail=detail) from error
    except requests.RequestException as error:
        raise HTTPException(status_code=502, detail="Could not reach the weather provider.") from error


@app.get("/api/live/air-quality")
def get_live_air_quality(city: str | None = Query(default=None)):
    """Live air quality from the selected provider, normalized for the UI."""
    cities = get_city_locations(city)
    return {
        "provider": load_config()["provider"],
        "count": len(cities),
        "data": [fetch_live_air_quality(item) for item in cities],
    }


@app.get("/api/live/weather")
def get_live_weather(city: str | None = Query(default=None)):
    """Live weather from the selected provider, normalized for the UI."""
    cities = get_city_locations(city)
    return {
        "provider": load_config()["provider"],
        "count": len(cities),
        "data": [fetch_live_weather(item) for item in cities],
    }


# =========================================================
# CLEAN SHUTDOWN
# =========================================================

@app.on_event("shutdown")
def shutdown_event():
    engine.dispose()