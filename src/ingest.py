
import logging
import os
from pathlib import Path

import openmeteo_requests
import pandas as pd
import psycopg
import requests_cache
from dotenv import load_dotenv
from retry_requests import retry


# ============================================================
# 1. PROJECT CONFIGURATION
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "urbanpulse")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD")

if not DB_PASSWORD:
    raise RuntimeError(
        "DB_PASSWORD is missing. Check the .env file in the "
        "UrbanPulse project root."
    )

DATABASE_CONFIG = {
    "host": DB_HOST,
    "port": DB_PORT,
    "dbname": DB_NAME,
    "user": DB_USER,
    "password": DB_PASSWORD,
    "connect_timeout": 10,
}

CITY = "Pune"
LOCATION_ID = "pune_central"
LATITUDE = 18.5196
LONGITUDE = 73.8554

AIR_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"

CACHE_DIR = PROJECT_ROOT / ".cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)


# ============================================================
# 2. API CLIENT: CACHING AND RETRIES
# ============================================================

session = requests_cache.CachedSession(
    str(CACHE_DIR / "openmeteo_cache"),
    expire_after=900,
)

session = retry(
    session,
    retries=3,
    backoff_factor=0.3,
)

openmeteo = openmeteo_requests.Client(session=session)


# ============================================================
# 3. CONVERT API RESPONSES TO DATAFRAMES
# ============================================================

def get_hourly_dataframe(response, variables):
    """Convert an Open-Meteo hourly response into a DataFrame."""

    hourly = response.Hourly()

    if hourly is None:
        raise ValueError("The API response contains no hourly data.")

    first_variable = hourly.Variables(0)
    if first_variable is None:
        raise ValueError("The API response contains no hourly variables.")

    first_values = first_variable.ValuesAsNumpy()

    times = pd.date_range(
        start=pd.to_datetime(hourly.Time(), unit="s", utc=True),
        periods=len(first_values),
        freq=pd.Timedelta(seconds=hourly.Interval()),
    )

    data = {"valid_time": times}

    for index, variable in enumerate(variables):
        hourly_variable = hourly.Variables(index)

        if hourly_variable is None:
            raise ValueError(
                f"Missing expected API variable: {variable}"
            )

        values = hourly_variable.ValuesAsNumpy()

        if len(values) != len(times):
            raise ValueError(
                f"Unexpected data length for variable: {variable}"
            )

        data[variable] = values

    return pd.DataFrame(data)


# ============================================================
# 4. FETCH PUNE AIR-QUALITY AND WEATHER DATA
# ============================================================

def fetch_environmental_data():
    """Fetch and merge hourly air-quality and weather forecasts."""

    logging.info("Fetching environmental forecasts for %s", CITY)

    air_params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "hourly": [
            "pm2_5",
            "pm10",
            "nitrogen_dioxide",
            "ozone",
            "european_aqi",
            "us_aqi",
        ],
        "forecast_days": 2,
        "timezone": "UTC",
    }

    weather_params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "hourly": [
            "temperature_2m",
            "relative_humidity_2m",
            "wind_speed_10m",
            "precipitation",
        ],
        "forecast_days": 2,
        "timezone": "UTC",
    }

    air_responses = openmeteo.weather_api(
        AIR_URL,
        params=air_params,
    )

    weather_responses = openmeteo.weather_api(
        WEATHER_URL,
        params=weather_params,
    )

    if not air_responses or not weather_responses:
        raise RuntimeError("An Open-Meteo API returned no responses.")

    air_variables = [
        "pm2_5",
        "pm10",
        "nitrogen_dioxide",
        "ozone",
        "european_aqi",
        "us_aqi",
    ]

    weather_variables = [
        "temperature_2m",
        "relative_humidity_2m",
        "wind_speed_10m",
        "precipitation",
    ]

    air_df = get_hourly_dataframe(
        air_responses[0],
        air_variables,
    )

    weather_df = get_hourly_dataframe(
        weather_responses[0],
        weather_variables,
    )

    df = pd.merge(
        air_df,
        weather_df,
        on="valid_time",
        how="inner",
        validate="one_to_one",
    )

    if df.empty:
        raise RuntimeError(
            "The air-quality and weather APIs returned no matching "
            "hourly timestamps."
        )

    df["city"] = CITY
    df["location_id"] = LOCATION_ID

    columns = [
        "city",
        "location_id",
        "valid_time",
        "pm2_5",
        "pm10",
        "nitrogen_dioxide",
        "ozone",
        "european_aqi",
        "us_aqi",
        "temperature_2m",
        "relative_humidity_2m",
        "wind_speed_10m",
        "precipitation",
    ]

    df = df[columns].copy()

    # Replace infinite values with missing values.
    numeric_columns = df.select_dtypes(include="number").columns
    df[numeric_columns] = df[numeric_columns].replace(
        [float("inf"), float("-inf")],
        float("nan"),
    )

    logging.info(
        "Successfully combined %s hourly records.",
        len(df),
    )

    return df


# ============================================================
# 5. CLEAN DATA FOR POSTGRESQL
# ============================================================

INTEGER_COLUMNS = {"european_aqi", "us_aqi"}


def clean_value(value, column_name):
    """Convert pandas/NumPy values to PostgreSQL-compatible values."""

    if pd.isna(value):
        return None

    if column_name in INTEGER_COLUMNS:
        return int(value)

    if hasattr(value, "item"):
        value = value.item()

    return value


def prepare_records(df, run_id):
    """Prepare rows matching the environmental snapshots schema."""

    records = []

    data_columns = [
        "city",
        "location_id",
        "valid_time",
        "pm2_5",
        "pm10",
        "nitrogen_dioxide",
        "ozone",
        "european_aqi",
        "us_aqi",
        "temperature_2m",
        "relative_humidity_2m",
        "wind_speed_10m",
        "precipitation",
    ]

    for row in df[data_columns].itertuples(index=False, name=None):
        (
            city,
            location_id,
            valid_time,
            pm2_5,
            pm10,
            nitrogen_dioxide,
            ozone,
            european_aqi,
            us_aqi,
            temperature_2m,
            relative_humidity_2m,
            wind_speed_10m,
            precipitation,
        ) = row

        records.append(
            (
                run_id,
                city,
                location_id,
                "model_forecast",
                valid_time.to_pydatetime(),
                clean_value(pm2_5, "pm2_5"),
                clean_value(pm10, "pm10"),
                clean_value(nitrogen_dioxide, "nitrogen_dioxide"),
                clean_value(ozone, "ozone"),
                clean_value(european_aqi, "european_aqi"),
                clean_value(us_aqi, "us_aqi"),
                clean_value(temperature_2m, "temperature_2m"),
                clean_value(relative_humidity_2m, "relative_humidity_2m"),
                clean_value(wind_speed_10m, "wind_speed_10m"),
                clean_value(precipitation, "precipitation"),
            )
        )

    return records


# ============================================================
# 6. DATABASE INGESTION
# ============================================================


# ============================================================
# 6. DATABASE INGESTION
# ============================================================

INSERT_SNAPSHOT_SQL = """
    INSERT INTO environmental_hourly_snapshots (
        run_id, city, location_id, data_kind, valid_time,
        pm2_5, pm10, nitrogen_dioxide, ozone,
        european_aqi, us_aqi, temperature_2m,
        relative_humidity_2m, wind_speed_10m, precipitation
    )
    VALUES (
        %s, %s, %s, %s, %s, %s, %s, %s,
        %s, %s, %s, %s, %s, %s, %s
    )
"""

UPSERT_LATEST_SQL = """
    INSERT INTO latest_environmental_forecasts (
        city, location_id, data_kind, valid_time,
        fetched_at, last_run_id,
        pm2_5, pm10, nitrogen_dioxide, ozone,
        european_aqi, us_aqi, temperature_2m,
        relative_humidity_2m, wind_speed_10m, precipitation
    )
    VALUES (
        %s, %s, %s, %s, NOW(), %s,
        %s, %s, %s, %s, %s, %s,
        %s, %s, %s, %s
    )
    ON CONFLICT (location_id, data_kind, valid_time)
    DO UPDATE SET
        city = EXCLUDED.city,
        fetched_at = NOW(),
        last_run_id = EXCLUDED.last_run_id,
        pm2_5 = EXCLUDED.pm2_5,
        pm10 = EXCLUDED.pm10,
        nitrogen_dioxide = EXCLUDED.nitrogen_dioxide,
        ozone = EXCLUDED.ozone,
        european_aqi = EXCLUDED.european_aqi,
        us_aqi = EXCLUDED.us_aqi,
        temperature_2m = EXCLUDED.temperature_2m,
        relative_humidity_2m = EXCLUDED.relative_humidity_2m,
        wind_speed_10m = EXCLUDED.wind_speed_10m,
        precipitation = EXCLUDED.precipitation
"""


def ingest():
    """Fetch forecasts, preserve snapshots, and update latest forecasts."""

    run_id = None

    try:
        # Create the run record in its own transaction so that
        # a later ingestion failure can still be recorded.
        with psycopg.connect(**DATABASE_CONFIG) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO ingestion_runs (
                        source_name, status
                    )
                    VALUES (%s, 'running')
                    RETURNING run_id
                    """,
                    ("open_meteo_air_quality_and_weather",),
                )
                run_id = cur.fetchone()[0]

        logging.info("Started ingestion run_id=%s", run_id)

        # Fetch and prepare the data.
        df = fetch_environmental_data()
        records = prepare_records(df, run_id)

        if not records:
            raise RuntimeError("No records were prepared for insertion.")

        # Convert snapshot records into latest-forecast records.
        # Snapshot tuple:
        # run_id, city, location_id, data_kind, valid_time, metrics...
        # Latest tuple:
        # city, location_id, data_kind, valid_time, run_id, metrics...
        latest_records = [
            (record[1], record[2], record[3], record[4],
             record[0], *record[5:])
            for record in records
        ]

        # Both data writes and the success status are committed together.
        with psycopg.connect(**DATABASE_CONFIG) as conn:
            with conn.cursor() as cur:
                # Preserve each run's snapshots.
                cur.executemany(INSERT_SNAPSHOT_SQL, records)

                # Insert or update the current forecast for each timestamp.
                cur.executemany(UPSERT_LATEST_SQL, latest_records)

                cur.execute(
                    """
                    UPDATE ingestion_runs
                    SET status = 'succeeded',
                        finished_at = NOW(),
                        records_written = %s,
                        error_message = NULL
                    WHERE run_id = %s
                    """,
                    (len(records), run_id),
                )

        logging.info(
            "SUCCESS: run_id=%s, records_written=%s, "
            "latest_forecasts_updated=%s",
            run_id,
            len(records),
            len(latest_records),
        )

    except Exception as exc:
        logging.exception("Ingestion failed for run_id=%s", run_id)

        # Record failure outside the rolled-back data transaction.
        if run_id is not None:
            try:
                with psycopg.connect(**DATABASE_CONFIG) as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            UPDATE ingestion_runs
                            SET status = 'failed',
                                finished_at = NOW(),
                                error_message = %s
                            WHERE run_id = %s
                              AND status = 'running'
                            """,
                            (str(exc)[:4000], run_id),
                        )
            except Exception:
                logging.exception(
                    "Unable to save failure status for run_id=%s",
                    run_id,
                )

        raise


# ============================================================
# 7. ENTRY POINT
# ============================================================
if __name__ == "__main__":
    ingest()
