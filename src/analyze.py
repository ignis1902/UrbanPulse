
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import psycopg
from dotenv import load_dotenv
import os


# --------------------------------------------------
# 1. Project configuration
# --------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = PROJECT_ROOT / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

load_dotenv(PROJECT_ROOT / ".env", override=True)

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "dbname": os.getenv("DB_NAME", "urbanpulse"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD"),
}

if not DB_CONFIG["password"]:
    raise RuntimeError("DB_PASSWORD is missing from .env")


# --------------------------------------------------
# 2. Load data from PostgreSQL
# --------------------------------------------------

QUERY = """
SELECT
    city,
    location_id,
    valid_time,
    fetched_at,
    pm2_5,
    pm10,
    european_aqi,
    temperature_2m,
    wind_speed_10m,
    data_kind
FROM environmental_hourly_snapshots
ORDER BY valid_time;
"""


def main():
    print("Connecting to UrbanPulse database...")

    with psycopg.connect(**DB_CONFIG) as conn:
        df = pd.read_sql_query(QUERY, conn)

    if df.empty:
        raise RuntimeError(
            "No environmental records found. Run ingest.py first."
        )

    df["valid_time"] = pd.to_datetime(
        df["valid_time"], utc=True
    )

    df = df.sort_values("valid_time").reset_index(drop=True)

    print(f"Loaded {len(df)} records.")

    # --------------------------------------------------
    # 3. Export analysis dataset
    # --------------------------------------------------

    csv_path = REPORTS_DIR / "urbanpulse_forecast_data.csv"
    df.to_csv(csv_path, index=False)
    print(f"Dataset saved: {csv_path}")

    # --------------------------------------------------
    # 4. Generate summary statistics
    # --------------------------------------------------

    numeric_columns = [
        "pm2_5",
        "pm10",
        "european_aqi",
        "temperature_2m",
        "wind_speed_10m",
    ]

    summary = df[numeric_columns].describe().T
    summary["missing_values"] = df[numeric_columns].isna().sum()
    summary_path = REPORTS_DIR / "summary_statistics.csv"
    summary.to_csv(summary_path)

    print("\nSummary statistics:")
    print(summary.round(2).to_string())
    print(f"\nSummary saved: {summary_path}")

    # --------------------------------------------------
    # 5. PM2.5 time-series chart
    # --------------------------------------------------

    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(
        df["valid_time"],
        df["pm2_5"],
        marker="o",
        markersize=3,
        linewidth=1.8,
        label="PM2.5 forecast",
    )
    ax.set_title("UrbanPulse | Pune PM2.5 Forecast")
    ax.set_xlabel("Forecast time (UTC)")
    ax.set_ylabel("PM2.5 (µg/m³)")
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.autofmt_xdate()
    fig.tight_layout()

    pm25_path = REPORTS_DIR / "pm25_timeseries.png"
    fig.savefig(pm25_path, dpi=160)
    plt.close(fig)

    # --------------------------------------------------
    # 6. European AQI time-series chart
    # --------------------------------------------------

    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(
        df["valid_time"],
        df["european_aqi"],
        marker="o",
        markersize=3,
        linewidth=1.8,
        label="European AQI forecast",
    )
    ax.set_title("UrbanPulse | Pune European AQI Forecast")
    ax.set_xlabel("Forecast time (UTC)")
    ax.set_ylabel("European AQI")
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.autofmt_xdate()
    fig.tight_layout()

    aqi_path = REPORTS_DIR / "european_aqi_timeseries.png"
    fig.savefig(aqi_path, dpi=160)
    plt.close(fig)

    # --------------------------------------------------
    # 7. Weather time-series chart
    # --------------------------------------------------

    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(
        df["valid_time"],
        df["temperature_2m"],
        marker="o",
        markersize=3,
        label="Temperature (°C)",
    )
    ax.set_title("UrbanPulse | Pune Temperature Forecast")
    ax.set_xlabel("Forecast time (UTC)")
    ax.set_ylabel("Temperature (°C)")
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.autofmt_xdate()
    fig.tight_layout()

    weather_path = REPORTS_DIR / "temperature_timeseries.png"
    fig.savefig(weather_path, dpi=160)
    plt.close(fig)

    # --------------------------------------------------
    # 8. Correlation analysis
    # --------------------------------------------------

    correlation = df[numeric_columns].corr()
    correlation_path = REPORTS_DIR / "correlation_matrix.csv"
    correlation.to_csv(correlation_path)

    fig, ax = plt.subplots(figsize=(8, 6))
    image = ax.imshow(correlation, vmin=-1, vmax=1)
    ax.set_xticks(range(len(numeric_columns)))
    ax.set_yticks(range(len(numeric_columns)))
    ax.set_xticklabels(numeric_columns, rotation=35, ha="right")
    ax.set_yticklabels(numeric_columns)
    ax.set_title("UrbanPulse | Forecast Variable Correlations")

    for i in range(len(numeric_columns)):
        for j in range(len(numeric_columns)):
            value = correlation.iloc[i, j]
            label = f"{value:.2f}" if pd.notna(value) else "N/A"
            ax.text(j, i, label, ha="center", va="center")

    fig.colorbar(image, ax=ax, label="Correlation")
    fig.tight_layout()

    correlation_image = REPORTS_DIR / "correlation_matrix.png"
    fig.savefig(correlation_image, dpi=160)
    plt.close(fig)

    # --------------------------------------------------
    # 9. Final report
    # --------------------------------------------------

    print("\nAnalysis completed successfully!")
    print(f"Rows analyzed: {len(df)}")
    print(f"Cities: {df['city'].nunique()}")
    print(f"Forecast types: {df['data_kind'].unique().tolist()}")
    print(f"Reports folder: {REPORTS_DIR}")

    print("\nGenerated files:")
    for path in sorted(REPORTS_DIR.iterdir()):
        if path.is_file():
            print(f" - {path.name}")


if __name__ == "__main__":
    main()
