
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "data" / "historical"
OUTPUT_FILE = OUTPUT_DIR / "open_meteo_air_quality_history.csv"

# Pune coordinates
LATITUDE = 18.5196
LONGITUDE = 73.8554

API_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"

HOURLY_VARIABLES = [
    "pm2_5",
    "pm10",
    "nitrogen_dioxide",
    "ozone",
    "european_aqi",
    "us_aqi",
]

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "hourly": ",".join(HOURLY_VARIABLES),
        "past_days": 90,
        "forecast_days": 0,
        "timezone": "Asia/Kolkata",
    }

    print("Requesting historical air-quality model data for Pune...")

    response = requests.get(API_URL, params=params, timeout=90)
    response.raise_for_status()
    payload = response.json()

    if payload.get("error"):
        raise RuntimeError(payload.get("reason", "API returned an error"))

    hourly = payload.get("hourly", {})
    if "time" not in hourly:
        raise RuntimeError("API response did not contain hourly timestamps.")

    df = pd.DataFrame(hourly)
    df["city"] = "Pune"
    df["latitude"] = payload.get("latitude")
    df["longitude"] = payload.get("longitude")
    df["data_source"] = "Open-Meteo Air Quality API"
    df["data_type"] = "model-based historical series"

    df["time"] = pd.to_datetime(df["time"], errors="coerce")
    df = df.dropna(subset=["time"])
    df = df.sort_values("time").drop_duplicates("time")

    if df.empty:
        raise RuntimeError("The API returned no usable hourly records.")

    df.to_csv(OUTPUT_FILE, index=False)

    print(f"Records saved: {len(df)}")
    print(f"First timestamp: {df['time'].min()}")
    print(f"Last timestamp:  {df['time'].max()}")
    print(f"Missing values by column:\n{df[HOURLY_VARIABLES].isna().sum()}")
    print(f"Saved file: {OUTPUT_FILE}")
    print(
        "\nImportant: these are model-based air-quality values, "
        "not independent ground-station observations."
    )

if __name__ == "__main__":
    main()
