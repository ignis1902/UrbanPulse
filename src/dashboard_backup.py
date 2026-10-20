
from pathlib import Path
import os
import subprocess
import sys

import pandas as pd
import plotly.express as px
import psycopg
import streamlit as st
from dotenv import load_dotenv


# --------------------------------------------------
# Configuration
# --------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env", override=True)

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "dbname": os.getenv("DB_NAME", "urbanpulse"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD"),
}

st.set_page_config(
    page_title="UrbanPulse | Environmental Intelligence",
    page_icon="🌍",
    layout="wide",
)

st.title("🌍 UrbanPulse")
st.subheader("Environmental Analytics & Predictive Decision Support")
st.caption(
    "Pune, India | Hourly model forecasts | "
    "Forecast data is not equivalent to ground-station observations."
)


# --------------------------------------------------
# Data loading
# --------------------------------------------------

@st.cache_data(ttl=60)
def load_data():
    query = """
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
FROM latest_environmental_forecasts
        ORDER BY valid_time;
    """

    with psycopg.connect(**DB_CONFIG) as conn:
        df = pd.read_sql_query(query, conn)

    if not df.empty:
        df["valid_time"] = pd.to_datetime(
            df["valid_time"], utc=True
        )

    return df


# --------------------------------------------------
# Sidebar controls
# --------------------------------------------------
with st.sidebar:
    st.header("Dashboard controls")

    if st.button(
        "Fetch latest forecasts",
        use_container_width=True,
    ):
        with st.spinner("Fetching fresh forecasts from Open-Meteo..."):
            try:
                result = subprocess.run(
                    [sys.executable, str(ROOT / "src" / "ingest.py")],
                    cwd=str(ROOT),
                    capture_output=True,
                    text=True,
                    timeout=180,
                )

                if result.returncode == 0:
                    st.session_state["ingestion_message"] = (
                        "Forecast ingestion completed successfully."
                    )
                    st.session_state["ingestion_is_error"] = False
                else:
                    st.session_state["ingestion_message"] = (
                        "Ingestion failed. Check the output below."
                    )
                    st.session_state["ingestion_is_error"] = True

                st.session_state["ingestion_output"] = (
                    result.stdout + "\n" + result.stderr
                ).strip()[-5000:]

            except subprocess.TimeoutExpired:
                st.session_state["ingestion_message"] = (
                    "Ingestion timed out after 180 seconds."
                )
                st.session_state["ingestion_is_error"] = True
                st.session_state["ingestion_output"] = (
                    "Check the terminal and application logs."
                )

        load_data.clear()
        st.rerun()

    if "ingestion_message" in st.session_state:
        if st.session_state.get("ingestion_is_error", False):
            st.error(st.session_state["ingestion_message"])
        else:
            st.success(st.session_state["ingestion_message"])

        output = st.session_state.get("ingestion_output", "")
        if output:
            with st.expander("Ingestion details"):
                st.code(output)

    st.caption("Data is read from PostgreSQL.")
    st.caption(
        "Use Fetch latest forecasts to retrieve and store new forecasts."
    )


# --------------------------------------------------
# Main dashboard
# --------------------------------------------------

try:
    df = load_data()

    if df.empty:
        st.warning(
            "No data found. Run the ingestion script first:\n\n"
            "`python .\\src\\ingest.py`"
        )
        st.stop()

    # Use the selected city's data.
    cities = sorted(df["city"].dropna().unique().tolist())

    with st.sidebar:
        selected_city = st.selectbox("Select city", cities)

    city_df = df[df["city"] == selected_city].copy()

    # Filters use UTC internally.
    start_date = city_df["valid_time"].min().date()
    end_date = city_df["valid_time"].max().date()

    with st.sidebar:
        date_range = st.date_input(
            "Forecast date range (UTC)",
            value=(start_date, end_date),
            min_value=start_date,
            max_value=end_date,
        )

    if isinstance(date_range, (tuple, list)) and len(date_range) == 2:
        start, end = date_range
        city_df = city_df[
            (city_df["valid_time"].dt.date >= start)
            & (city_df["valid_time"].dt.date <= end)
        ]

    if city_df.empty:
        st.warning("No records match the selected filters.")
        st.stop()

    latest = city_df.sort_values("valid_time").iloc[-1]

    # --------------------------------------------------
    # KPI cards
    # --------------------------------------------------

    st.markdown("### Environmental overview")

    c1, c2, c3, c4, c5 = st.columns(5)

    c1.metric(
        "PM2.5",
        f"{latest['pm2_5']:.1f}" if pd.notna(latest["pm2_5"]) else "N/A",
        help="Forecast concentration in µg/m³.",
    )
    c2.metric(
        "PM10",
        f"{latest['pm10']:.1f}" if pd.notna(latest["pm10"]) else "N/A",
        help="Forecast concentration in µg/m³.",
    )
    c3.metric(
        "European AQI",
        f"{latest['european_aqi']:.0f}"
        if pd.notna(latest["european_aqi"]) else "N/A",
        help="European Air Quality Index, as supplied by the source.",
    )
    c4.metric(
        "Temperature",
        f"{latest['temperature_2m']:.1f} °C"
        if pd.notna(latest["temperature_2m"]) else "N/A",
    )
    c5.metric(
        "Wind speed",
        f"{latest['wind_speed_10m']:.1f} km/h"
        if pd.notna(latest["wind_speed_10m"]) else "N/A",
        help="Open-Meteo wind speed is represented here in km/h.",
    )

    st.caption(
        "KPI values represent the latest timestamp inside the selected date range."
    )

    # --------------------------------------------------
    # Trend charts
    # --------------------------------------------------

    st.markdown("### Pollution trends")

    left, right = st.columns(2)

    with left:
        fig = px.line(
            city_df,
            x="valid_time",
            y="pm2_5",
            markers=True,
            title="PM2.5 forecast",
            labels={
                "valid_time": "Forecast time (UTC)",
                "pm2_5": "PM2.5 (µg/m³)",
            },
        )
        st.plotly_chart(fig, use_container_width=True)

    with right:
        fig = px.line(
            city_df,
            x="valid_time",
            y="european_aqi",
            markers=True,
            title="European AQI forecast",
            labels={
                "valid_time": "Forecast time (UTC)",
                "european_aqi": "European AQI",
            },
        )
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("### Weather trends")

    left, right = st.columns(2)

    with left:
        fig = px.line(
            city_df,
            x="valid_time",
            y="temperature_2m",
            markers=True,
            title="Temperature forecast",
            labels={
                "valid_time": "Forecast time (UTC)",
                "temperature_2m": "Temperature (°C)",
            },
        )
        st.plotly_chart(fig, use_container_width=True)

    with right:
        fig = px.line(
            city_df,
            x="valid_time",
            y="wind_speed_10m",
            markers=True,
            title="Wind speed forecast",
            labels={
                "valid_time": "Forecast time (UTC)",
                "wind_speed_10m": "Wind speed (km/h)",
            },
        )
        st.plotly_chart(fig, use_container_width=True)

    # --------------------------------------------------
    # Correlation analysis
    # --------------------------------------------------

    st.markdown("### Forecast variable relationships")

    variables = [
        "pm2_5",
        "pm10",
        "european_aqi",
        "temperature_2m",
        "wind_speed_10m",
    ]

    corr = city_df[variables].corr()

    fig = px.imshow(
        corr,
        text_auto=".2f",
        aspect="auto",
        zmin=-1,
        zmax=1,
        color_continuous_scale="RdBu_r",
        title="Correlation matrix",
    )
    st.plotly_chart(fig, use_container_width=True)

    st.caption(
        "Correlation shows association, not causation. "
        "These relationships are based on forecast values."
    )

    # --------------------------------------------------
    # Data table and export
    # --------------------------------------------------

    st.markdown("### Forecast records")

    display_df = city_df.sort_values(
        "valid_time", ascending=False
    ).copy()

    st.dataframe(display_df, use_container_width=True, hide_index=True)

    csv = display_df.to_csv(index=False).encode("utf-8")

    st.download_button(
        "Download filtered data (CSV)",
        data=csv,
        file_name="urbanpulse_forecast_data.csv",
        mime="text/csv",
    )

    st.caption(
        f"Showing {len(display_df)} records | "
        f"Forecast type: {', '.join(display_df['data_kind'].dropna().unique())}"
    )

except Exception as exc:
    st.error("Unable to load the UrbanPulse dashboard.")
    st.exception(exc)
