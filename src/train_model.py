
from pathlib import Path
import os

import numpy as np
import pandas as pd
import psycopg
from dotenv import load_dotenv
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env", override=True)

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "dbname": os.getenv("DB_NAME", "urbanpulse"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD"),
}

QUERY = """
    SELECT
        location_id,
        valid_time,
        fetched_at,
        pm2_5,
        pm10,
        nitrogen_dioxide,
        ozone,
        european_aqi,
        us_aqi,
        temperature_2m,
        relative_humidity_2m,
        wind_speed_10m,
        precipitation
    FROM environmental_hourly_snapshots
    ORDER BY fetched_at, valid_time
"""

TARGET = "pm2_5"

FEATURES = [
    "pm10",
    "nitrogen_dioxide",
    "ozone",
    "temperature_2m",
    "relative_humidity_2m",
    "wind_speed_10m",
    "precipitation",
    "hour",
    "day_of_week",
]


def main():
    with psycopg.connect(**DB_CONFIG) as conn:
        df = pd.read_sql_query(QUERY, conn)

    if df.empty:
        raise RuntimeError("No snapshot data found.")

    # Remove repeated captures of the same forecast hour.
    # Keep the latest capture for each location and valid time.
    df["valid_time"] = pd.to_datetime(df["valid_time"], utc=True)
    df["fetched_at"] = pd.to_datetime(df["fetched_at"], utc=True)

    df = (
        df.sort_values("fetched_at")
        .drop_duplicates(["location_id", "valid_time"], keep="last")
        .sort_values("valid_time")
        .reset_index(drop=True)
    )

    df["hour"] = df["valid_time"].dt.hour
    df["day_of_week"] = df["valid_time"].dt.dayofweek

    df = df.dropna(subset=[TARGET]).copy()

    print(f"Unique location-hour rows: {len(df)}")
    print(f"Target: {TARGET}")

    if len(df) < 20:
        raise RuntimeError(
            "Too few unique hourly records for a useful experiment. "
            "Collect more history before evaluating a model."
        )

    # Chronological split: never shuffle time-series data.
    split = int(len(df) * 0.8)
    train_df = df.iloc[:split].copy()
    test_df = df.iloc[split:].copy()

    X_train = train_df[FEATURES]
    y_train = train_df[TARGET]
    X_test = test_df[FEATURES]
    y_test = test_df[TARGET]

    models = {
        "Baseline (training median)": Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("model", DummyRegressor(strategy="median")),
        ]),
        "Random Forest": Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("model", RandomForestRegressor(
                n_estimators=100,
                max_depth=5,
                random_state=42,
            )),
        ]),
    }

    results = []

    for name, model in models.items():
        model.fit(X_train, y_train)
        predictions = model.predict(X_test)

        mae = mean_absolute_error(y_test, predictions)
        rmse = np.sqrt(mean_squared_error(y_test, predictions))
        r2 = r2_score(y_test, predictions)

        results.append({
            "model": name,
            "MAE": mae,
            "RMSE": rmse,
            "R2": r2,
        })

    results_df = pd.DataFrame(results)
    reports_dir = ROOT / "reports"
    reports_dir.mkdir(exist_ok=True)

    results_path = reports_dir / "baseline_model_metrics.csv"
    results_df.to_csv(results_path, index=False)

    print("\nExperimental results:")
    print(results_df.to_string(index=False))
    print(f"\nSaved metrics to: {results_path}")

    print(
        "\nIMPORTANT: This is an experimental forecast-data benchmark, "
        "not proof of real-world future pollution prediction. "
        "The dataset contains forecast values, not independent "
        "ground-station observations."
    )


if __name__ == "__main__":
    main()
