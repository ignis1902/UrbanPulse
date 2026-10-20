from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

DATA_PATH = Path("data/historical/pune_station_hourly_aqi.csv")
METRICS_PATH = Path("reports/aqi_model_metrics.csv")
PREDICTIONS_PATH = Path("reports/aqi_model_predictions.csv")

df = pd.read_csv(DATA_PATH)
df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
df["aqi"] = pd.to_numeric(df["aqi"], errors="coerce")
df = df.dropna(subset=["timestamp", "station", "aqi"])
df = df.sort_values(["station", "timestamp"])
df["timestamp"] = df["timestamp"].dt.floor("h")
df = df.drop_duplicates(["station", "timestamp"], keep="last")

# Four small candidate configurations; validation selects the winner.
candidates = [
    {"max_depth": 5, "min_samples_leaf": 5},
    {"max_depth": 10, "min_samples_leaf": 5},
    {"max_depth": 10, "min_samples_leaf": 15},
    {"max_depth": None, "min_samples_leaf": 15},
]

results = []
prediction_tables = []

for station, group in df.groupby("station"):
    series = (
        group.set_index("timestamp")["aqi"]
        .sort_index()
        .resample("h")
        .mean()
    )

    # Reindexing preserves missing hours as NaN.
    hourly = series.to_frame("current_aqi")
    hourly["lag_1"] = series.shift(1)
    hourly["lag_2"] = series.shift(2)
    hourly["lag_3"] = series.shift(3)
    hourly["lag_24"] = series.shift(24)
    hourly["lag_168"] = series.shift(168)

    previous = series.shift(1)
    hourly["rolling_mean_24"] = previous.rolling(
        24, min_periods=18
    ).mean()
    hourly["rolling_std_24"] = previous.rolling(
        24, min_periods=18
    ).std()

    hourly["target"] = series.shift(-1)
    hourly["target_time"] = hourly.index + pd.Timedelta(hours=1)
    hourly["target_hour"] = hourly["target_time"].dt.hour
    hourly["target_day_of_week"] = hourly["target_time"].dt.dayofweek

    features = [
        "current_aqi", "lag_1", "lag_2", "lag_3",
        "lag_24", "lag_168", "rolling_mean_24",
        "rolling_std_24", "target_hour", "target_day_of_week",
    ]

    # The target must exist at exactly the next hourly timestamp.
    valid = hourly[
        hourly["target"].notna()
        & hourly["current_aqi"].notna()
        & hourly[features].notna().all(axis=1)
    ].copy()

    # Split using the complete hourly timeline, not just valid rows.
    # This keeps the validation and test periods chronologically defined.
    timeline = hourly.index
    if len(timeline) < 500:
        print(f"Skipping {station}: insufficient hourly history.")
        continue

    validation_start = timeline[int(len(timeline) * 0.70)]
    test_start = timeline[int(len(timeline) * 0.85)]

    train = valid[valid["target_time"] < validation_start]
    validation = valid[
        (valid["target_time"] >= validation_start)
        & (valid["target_time"] < test_start)
    ]
    test = valid[valid["target_time"] >= test_start]

    if min(len(train), len(validation), len(test)) < 30:
        print(
            f"Skipping {station}: insufficient valid examples "
            "in one or more chronological splits."
        )
        continue

    X_train = train[features]
    y_train = train["target"]
    X_val = validation[features]
    y_val = validation["target"]

    best_params = None
    best_val_mae = float("inf")

    print(f"\nTUNING: {station}")
    print(f"Training examples: {len(train)}")
    print(f"Validation examples: {len(validation)}")
    print(f"Test examples: {len(test)}")
    print(f"Validation target period starts: {validation_start}")
    print(f"Final test target period starts: {test_start}")

    for params in candidates:
        candidate = RandomForestRegressor(
            n_estimators=100,
            max_depth=params["max_depth"],
            min_samples_leaf=params["min_samples_leaf"],
            random_state=42,
            n_jobs=-1,
        )
        candidate.fit(X_train, y_train)
        val_prediction = candidate.predict(X_val)
        val_mae = mean_absolute_error(y_val, val_prediction)

        print(f"  {params} -> validation MAE: {val_mae:.3f}")

        if val_mae < best_val_mae:
            best_val_mae = val_mae
            best_params = params

    # Once tuning is complete, refit on train + validation.
    combined = pd.concat([train, validation]).sort_index()
    model = RandomForestRegressor(
        n_estimators=100,
        max_depth=best_params["max_depth"],
        min_samples_leaf=best_params["min_samples_leaf"],
        random_state=42,
        n_jobs=-1,
    )
    model.fit(combined[features], combined["target"])

    X_test = test[features]
    y_test = test["target"]
    baseline_prediction = test["current_aqi"].to_numpy()
    rf_prediction = model.predict(X_test)

    for model_name, prediction in [
        ("Persistence baseline", baseline_prediction),
        ("Tuned Random Forest", rf_prediction),
    ]:
        results.append({
            "station": station,
            "model": model_name,
            "train_examples": len(train),
            "validation_examples": len(validation),
            "test_examples": len(test),
            "test_start": str(test_start),
            "test_end": str(test["target_time"].max()),
            "MAE": mean_absolute_error(y_test, prediction),
            "RMSE": np.sqrt(mean_squared_error(y_test, prediction)),
            "R2": r2_score(y_test, prediction),
        })

    prediction_tables.append(pd.DataFrame({
        "station": station,
        "target_time": test["target_time"].astype(str).to_numpy(),
        "actual_aqi": y_test.to_numpy(),
        "persistence_prediction": baseline_prediction,
        "random_forest_prediction": rf_prediction,
    }))

if not results:
    raise RuntimeError(
        "No station produced sufficient train, validation, and test data."
    )

metrics = pd.DataFrame(results)
predictions = pd.concat(prediction_tables, ignore_index=True)

METRICS_PATH.parent.mkdir(parents=True, exist_ok=True)
metrics.to_csv(METRICS_PATH, index=False)
predictions.to_csv(PREDICTIONS_PATH, index=False)

print("\nFINAL TEST METRICS")
print(metrics.round(3).to_string(index=False))
print(f"\nSaved metrics: {METRICS_PATH}")
print(f"Saved predictions: {PREDICTIONS_PATH}")
