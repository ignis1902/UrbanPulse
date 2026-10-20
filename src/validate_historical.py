
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
FILE = ROOT / "data" / "historical" / "open_meteo_air_quality_history.csv"

df = pd.read_csv(FILE, parse_dates=["time"])

pollutants = [
    "pm2_5",
    "pm10",
    "nitrogen_dioxide",
    "ozone",
    "european_aqi",
    "us_aqi",
]

print("\n===== DATASET OVERVIEW =====")
print("Rows:", len(df))
print("Columns:", len(df.columns))
print("Date range:", df["time"].min(), "to", df["time"].max())
print("Duplicate timestamps:", df["time"].duplicated().sum())

print("\n===== MISSING VALUES =====")
print(df[pollutants].isna().sum())

print("\n===== SUMMARY STATISTICS =====")
print(df[pollutants].describe().round(2).to_string())

print("\n===== HOURLY COVERAGE =====")
hours = df["time"].sort_values().diff().dropna()
print("Most common time interval:")
print(hours.value_counts().head())

print("\n===== SAMPLE RECORDS =====")
print(df[["time"] + pollutants].head(5).to_string(index=False))

print("\nValidation complete.")
