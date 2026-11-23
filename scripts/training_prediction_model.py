"""
AirVision: One-Hour-Ahead PM2.5 Forecasting Model

Loads historical air-quality observations from PostgreSQL,
creates time-safe forecasting features, trains a Random Forest
regressor, evaluates it chronologically, and saves the model.

Run from the project root:
    python scripts/training_prediction_model.py
"""

import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

# Make the project root importable.
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from backend.database import engine  # noqa: E402


# ---------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------

MODEL_DIR = BASE_DIR / "model"
MODEL_PATH = MODEL_DIR / "pm25_prediction_model.joblib"
METRICS_PATH = MODEL_DIR / "pm25_model_metrics.json"

FORECAST_HOURS = 1
MINIMUM_RECORDS = 30
TEST_FRACTION = 0.20
RANDOM_STATE = 42

NUMERIC_FEATURES = [
    "hour",
    "day_of_week",
    "month",
    "pm2_5_lag_1",
    "pm2_5_lag_2",
    "pm2_5_lag_3",
    "pm10",
    "temperature_c",
    "relative_humidity",
]

CATEGORICAL_FEATURES = ["city"]

FEATURES = CATEGORICAL_FEATURES + NUMERIC_FEATURES
TARGET = "target_pm2_5"


# ---------------------------------------------------------
# LOGGING
# ---------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger("AirVisionForecast")


# ---------------------------------------------------------
# LOAD HISTORICAL DATA
# ---------------------------------------------------------

def load_historical_data():
    """Read observations from PostgreSQL."""

    query = """
        SELECT
            city,
            observed_at,
            pm2_5,
            pm10,
            temperature_c,
            relative_humidity
        FROM air_quality_observations
        WHERE pm2_5 IS NOT NULL
        ORDER BY city, observed_at
    """

    with engine.connect() as connection:
        df = pd.read_sql_query(query, connection)

    if df.empty:
        raise ValueError(
            "No observations found in air_quality_observations."
        )

    df["observed_at"] = pd.to_datetime(
        df["observed_at"],
        errors="coerce",
        utc=True,
    )

    numeric_columns = [
        "pm2_5",
        "pm10",
        "temperature_c",
        "relative_humidity",
    ]

    for column in numeric_columns:
        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        )

    df = df.dropna(
        subset=["city", "observed_at", "pm2_5"]
    )

    df = df[df["pm2_5"] >= 0]

    # One observation per city and timestamp.
    df = df.drop_duplicates(
        subset=["city", "observed_at"],
        keep="last",
    )

    df = df.sort_values(
        ["city", "observed_at"]
    ).reset_index(drop=True)

    logger.info("Historical observations: %s", len(df))
    logger.info("Cities: %s", df["city"].nunique())

    return df


# ---------------------------------------------------------
# FEATURE ENGINEERING AND FUTURE TARGET
# ---------------------------------------------------------

def create_forecasting_dataset(df):
    """
    Use current and past observations to predict PM2.5
    exactly one hour into the future.

    Lag features are retained only when their timestamps
    are exactly 1, 2, and 3 hours before the current row.
    The target must exist exactly one hour after the row.
    """

    frames = []

    for city, group in df.groupby("city"):
        group = group.sort_values(
            "observed_at"
        ).copy()

        group = group.set_index(
            "observed_at",
            drop=False,
        )

        # Time-based features at prediction issue time.
        group["hour"] = group.index.hour
        group["day_of_week"] = group.index.dayofweek
        group["month"] = group.index.month

        # Historical PM2.5 features from exact timestamps.
        for lag in (1, 2, 3):
            previous = group["pm2_5"].shift(0)
            previous.index = group.index + pd.Timedelta(
                hours=lag
            )

            group[f"pm2_5_lag_{lag}"] = previous.reindex(
                group.index
            )

        # The target must be the observation exactly one
        # hour after the current timestamp.
        future_pm25 = group["pm2_5"].shift(-1)
        future_times = group.index.to_series().shift(-1)

        group["target_pm2_5"] = future_pm25
        group["target_timestamp"] = future_times

        expected_target_time = (
            group["observed_at"]
            + pd.Timedelta(hours=FORECAST_HOURS)
        )

        valid_target = (
            group["target_timestamp"] == expected_target_time
        )

        # Ensure the lag measurements really are from
        # exactly 1, 2, and 3 hours before the current row.
        for lag in (1, 2, 3):
            lag_times = (
                group.index.to_series()
                - pd.Timedelta(hours=lag)
            )

            available_times = group.index

            group[f"_lag_{lag}_valid"] = (
                lag_times.isin(available_times).to_numpy()
            )

        valid_lags = (
            group["_lag_1_valid"]
            & group["_lag_2_valid"]
            & group["_lag_3_valid"]
        )

        group = group[valid_target & valid_lags].copy()

        if not group.empty:
            frames.append(group.reset_index(drop=True))

    if not frames:
        raise ValueError(
            "No valid one-hour training examples found. "
            "Check that each city has consecutive hourly observations."
        )

    data = pd.concat(
        frames,
        ignore_index=True,
    )

    data = data.replace(
        [np.inf, -np.inf],
        np.nan,
    )

    data = data.dropna(
        subset=[
            "city",
            "observed_at",
            "target_timestamp",
            "target_pm2_5",
            "pm2_5_lag_1",
            "pm2_5_lag_2",
            "pm2_5_lag_3",
        ]
    )

    data = data.sort_values(
        "observed_at"
    ).reset_index(drop=True)

    logger.info(
        "Valid one-hour forecasting examples: %s",
        len(data),
    )

    return data


# ---------------------------------------------------------
# TRAIN AND EVALUATE
# ---------------------------------------------------------

def train_model(data):
    """Train and evaluate a chronological forecasting model."""

    if len(data) < MINIMUM_RECORDS:
        raise ValueError(
            f"Only {len(data)} valid forecasting examples found. "
            f"At least {MINIMUM_RECORDS} are required."
        )

    data = data.sort_values(
        "observed_at"
    ).reset_index(drop=True)

    # Split at a timestamp boundary so the same issue time
    # is not divided between training and testing.
    unique_times = np.sort(
        data["observed_at"].unique()
    )

    if len(unique_times) < 2:
        raise ValueError(
            "Not enough distinct timestamps for chronological evaluation."
        )

    split_position = int(
        len(unique_times) * (1 - TEST_FRACTION)
    )

    split_position = max(
        1,
        min(split_position, len(unique_times) - 1),
    )

    split_time = unique_times[split_position]

    train_df = data[
        data["observed_at"] < split_time
    ].copy()

    test_df = data[
        data["observed_at"] >= split_time
    ].copy()

    if train_df.empty or test_df.empty:
        raise ValueError(
            "Chronological split produced an empty training or test set."
        )

    X_train = train_df[FEATURES]
    y_train = train_df[TARGET]

    X_test = test_df[FEATURES]
    y_test = test_df[TARGET]

    preprocessing = ColumnTransformer(
        transformers=[
            (
                "numeric",
                SimpleImputer(strategy="median"),
                NUMERIC_FEATURES,
            ),
            (
                "categorical",
                Pipeline(
                    steps=[
                        (
                            "imputer",
                            SimpleImputer(
                                strategy="most_frequent"
                            ),
                        ),
                        (
                            "encoder",
                            OneHotEncoder(
                                handle_unknown="ignore"
                            ),
                        ),
                    ]
                ),
                CATEGORICAL_FEATURES,
            ),
        ],
        remainder="drop",
    )

    model = Pipeline(
        steps=[
            ("preprocessing", preprocessing),
            (
                "regressor",
                RandomForestRegressor(
                    n_estimators=200,
                    max_depth=10,
                    min_samples_leaf=2,
                    random_state=RANDOM_STATE,
                    n_jobs=-1,
                ),
            ),
        ]
    )

    logger.info("Training rows: %s", len(X_train))
    logger.info("Testing rows: %s", len(X_test))
    logger.info("Training cutoff: %s", split_time)

    model.fit(X_train, y_train)

    predictions = model.predict(X_test)

    mae = float(
        mean_absolute_error(y_test, predictions)
    )

    rmse = float(
        np.sqrt(mean_squared_error(y_test, predictions))
    )

    r2 = (
        float(r2_score(y_test, predictions))
        if len(y_test) >= 2
        else None
    )

    metrics = {
        "model_name": "Random Forest Regressor",
        "forecast_horizon_hours": FORECAST_HOURS,
        "target": "PM2.5",
        "target_unit": "µg/m³",
        "training_rows": int(len(X_train)),
        "testing_rows": int(len(X_test)),
        "total_usable_rows": int(len(data)),
        "city_count": int(data["city"].nunique()),
        "mae": mae,
        "rmse": rmse,
        "r2": r2,
        "trained_at": datetime.now().astimezone().isoformat(),
        "first_issue_time": data["observed_at"].min().isoformat(),
        "last_issue_time": data["observed_at"].max().isoformat(),
        "limitations": (
            "Experimental one-hour-ahead forecast. "
            "Performance requires validation on a longer historical period."
        ),
    }

    MODEL_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    artifact = {
        "model": model,
        "input_features": FEATURES,
        "numeric_features": NUMERIC_FEATURES,
        "categorical_features": CATEGORICAL_FEATURES,
        "target": TARGET,
        "forecast_horizon_hours": FORECAST_HOURS,
        "metrics": metrics,
    }

    joblib.dump(
        artifact,
        MODEL_PATH,
    )

    with METRICS_PATH.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            metrics,
            file,
            indent=4,
        )

    logger.info("Model saved: %s", MODEL_PATH)
    logger.info("Metrics saved: %s", METRICS_PATH)

    print("\n" + "=" * 55)
    print("AIRVISION ONE-HOUR FORECAST MODEL TRAINED")
    print("=" * 55)
    print(f"Forecast horizon : {FORECAST_HOURS} hour")
    print(f"Usable examples  : {len(data)}")
    print(f"Cities           : {data['city'].nunique()}")
    print(f"Training rows    : {len(X_train)}")
    print(f"Testing rows     : {len(X_test)}")
    print(f"MAE              : {mae:.3f} µg/m³")
    print(f"RMSE             : {rmse:.3f} µg/m³")

    if r2 is not None:
        print(f"R²               : {r2:.3f}")

    print("\nModel:")
    print(MODEL_PATH)
    print("\nMetrics:")
    print(METRICS_PATH)

    print(
        "\nIMPORTANT: Results are experimental. "
        "Use a longer historical dataset for stronger validation."
    )
    print("=" * 55)

    return artifact


# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------

def main():
    try:
        logger.info("Starting one-hour forecast training...")

        historical_df = load_historical_data()
        forecasting_df = create_forecasting_dataset(
            historical_df
        )

        train_model(forecasting_df)

    except Exception as error:
        logger.exception(
            "Forecast model training failed: %s",
            error,
        )
        raise

    finally:
        engine.dispose()


if __name__ == "__main__":
    main()