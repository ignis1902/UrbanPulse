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
    page_icon="🌿",
    layout="wide",
)

# Small, restrained styling layer. Streamlit remains responsive on narrow screens.
st.markdown(
    """
    <style>
    .block-container {padding-top: 1.6rem; padding-bottom: 2.5rem;}
    [data-testid="stMetric"] {
        background: rgba(100, 116, 139, 0.08);
        border: 1px solid rgba(100, 116, 139, 0.20);
        padding: 14px 16px;
        border-radius: 12px;
    }
    .up-eyebrow {
        text-transform: uppercase;
        letter-spacing: .12em;
        font-size: .78rem;
        font-weight: 700;
        color: #0d9488;
        margin-bottom: .25rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown('<div class="up-eyebrow">Environmental intelligence platform</div>', unsafe_allow_html=True)
st.title("🌿 UrbanPulse")
st.subheader("Environmental Analytics & Predictive Decision Support")
st.caption(
    "Pune, India · Hourly model forecasts · Forecast data is not equivalent "
    "to ground-station observations."
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
            us_aqi,
            temperature_2m,
            relative_humidity_2m,
            wind_speed_10m,
            precipitation,
            data_kind,
            last_run_id
        FROM latest_environmental_forecasts
        ORDER BY valid_time;
    """
    with psycopg.connect(**DB_CONFIG) as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()
            columns = [column.name for column in cur.description]
    df = pd.DataFrame(rows, columns=columns)

    if not df.empty:
        df["valid_time"] = pd.to_datetime(df["valid_time"], utc=True)
        df["fetched_at"] = pd.to_datetime(df["fetched_at"], utc=True)
    return df


def safe_metric(value, suffix="", decimals=1):
    if pd.isna(value):
        return "N/A"
    return f"{value:.{decimals}f}{suffix}"


def aqi_description(value):
    if pd.isna(value):
        return "Unavailable"
    # European AQI bands, expressed as a concise dashboard description.
    if value <= 20:
        return "Good"
    if value <= 40:
        return "Fair"
    if value <= 60:
        return "Moderate"
    if value <= 80:
        return "Poor"
    if value <= 100:
        return "Very poor"
    return "Extremely poor"


# --------------------------------------------------
# Sidebar controls
# --------------------------------------------------
with st.sidebar:
    st.header("Dashboard controls")
    st.caption("Source: Open-Meteo · Storage: PostgreSQL")

    if st.button("Fetch latest forecasts", type="primary", width="stretch"):
        with st.spinner("Fetching forecasts from Open-Meteo..."):
            try:
                result = subprocess.run(
                    [sys.executable, str(ROOT / "src" / "ingest.py")],
                    cwd=str(ROOT),
                    capture_output=True,
                    text=True,
                    timeout=180,
                )
                st.session_state["ingestion_message"] = (
                    "Forecast ingestion completed successfully."
                    if result.returncode == 0
                    else "Ingestion failed. Review the details below."
                )
                st.session_state["ingestion_is_error"] = result.returncode != 0
                st.session_state["ingestion_output"] = (
                    result.stdout + "\n" + result.stderr
                ).strip()[-5000:]
            except subprocess.TimeoutExpired:
                st.session_state["ingestion_message"] = (
                    "Ingestion timed out after 180 seconds."
                )
                st.session_state["ingestion_is_error"] = True
                st.session_state["ingestion_output"] = (
                    "The process exceeded the time limit. Check the terminal and logs."
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

    st.divider()
    st.caption("The dashboard displays model forecasts, not live sensor readings.")

# --------------------------------------------------
# Main dashboard
# --------------------------------------------------
try:
    df = load_data()

    if df.empty:
        st.warning(
            "No forecasts are available yet. Use the sidebar button or run "
            "`python .\\src\\ingest.py` from the project folder."
        )
        st.stop()

    cities = sorted(df["city"].dropna().unique().tolist())
    with st.sidebar:
        selected_city = st.selectbox("City", cities)

    city_df = df[df["city"] == selected_city].copy()
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

    city_df = city_df.sort_values("valid_time")
    latest = city_df.iloc[-1]
    latest_fetch = city_df["fetched_at"].max()

    # Status row
    status_col, refresh_col = st.columns([3, 2])
    with status_col:
        st.markdown("### Current forecast snapshot")
        st.caption(
            f"Latest forecast valid time: "
            f"{latest['valid_time'].strftime('%d %b %Y, %H:%M UTC')}"
        )
    with refresh_col:
        if pd.notna(latest_fetch):
            st.caption(
                f"Last data fetch: {latest_fetch.strftime('%d %b %Y, %H:%M UTC')}"
            )
        st.caption(f"Latest ingestion run ID: {int(latest['last_run_id'])}")

    # KPIs
    st.markdown("### Environmental overview")
    c1, c2, c3, c4, c5 = st.columns(5)

    c1.metric("PM2.5", safe_metric(latest["pm2_5"]), help="Forecast concentration in µg/m³.")
    c2.metric("PM10", safe_metric(latest["pm10"]), help="Forecast concentration in µg/m³.")
    c3.metric(
        "European AQI",
        safe_metric(latest["european_aqi"], decimals=0),
        help="European Air Quality Index supplied by the forecast source.",
    )
    c4.metric(
        "Temperature",
        safe_metric(latest["temperature_2m"], " °C"),
        help="Forecast air temperature at 2 metres.",
    )
    c5.metric(
        "Wind speed",
        safe_metric(latest["wind_speed_10m"], " km/h"),
        help="Forecast wind speed at 10 metres.",
    )

    aqi_status = aqi_description(latest["european_aqi"])
    st.info(
        f"European AQI category for the latest selected forecast: **{aqi_status}**. "
        "This category describes the forecast index; it is not a direct measurement "
        "of conditions at a monitoring station."
    )

    # Pollution trends
    st.markdown("### Pollution trends")
    left, right = st.columns(2)

    with left:
        fig = px.line(
            city_df, x="valid_time", y="pm2_5", markers=True,
            title="PM2.5 forecast",
            labels={"valid_time": "Forecast time (UTC)", "pm2_5": "PM2.5 (µg/m³)"},
        )
        fig.update_layout(margin=dict(l=10, r=10, t=55, b=10), hovermode="x unified")
        st.plotly_chart(fig, width="stretch")

    with right:
        fig = px.line(
            city_df, x="valid_time", y="european_aqi", markers=True,
            title="European AQI forecast",
            labels={"valid_time": "Forecast time (UTC)", "european_aqi": "European AQI"},
        )
        fig.update_layout(margin=dict(l=10, r=10, t=55, b=10), hovermode="x unified")
        st.plotly_chart(fig, width="stretch")

    # Weather trends
    st.markdown("### Weather trends")
    left, right = st.columns(2)

    with left:
        fig = px.line(
            city_df, x="valid_time", y="temperature_2m", markers=True,
            title="Temperature forecast",
            labels={"valid_time": "Forecast time (UTC)", "temperature_2m": "Temperature (°C)"},
        )
        fig.update_layout(margin=dict(l=10, r=10, t=55, b=10), hovermode="x unified")
        st.plotly_chart(fig, width="stretch")

    with right:
        fig = px.line(
            city_df, x="valid_time", y="wind_speed_10m", markers=True,
            title="Wind speed forecast",
            labels={"valid_time": "Forecast time (UTC)", "wind_speed_10m": "Wind speed (km/h)"},
        )
        fig.update_layout(margin=dict(l=10, r=10, t=55, b=10), hovermode="x unified")
        st.plotly_chart(fig, width="stretch")

    # Correlation analysis
    st.markdown("### Forecast variable relationships")
    variables = ["pm2_5", "pm10", "european_aqi", "temperature_2m", "wind_speed_10m"]
    corr = city_df[variables].corr(numeric_only=True)
    fig = px.imshow(
        corr, text_auto=".2f", aspect="auto", zmin=-1, zmax=1,
        color_continuous_scale="RdBu_r", title="Correlation matrix",
    )
    fig.update_layout(margin=dict(l=10, r=10, t=55, b=10))
    st.plotly_chart(fig, width="stretch")
    st.caption(
        "Correlation indicates association, not causation. These relationships are "
        "calculated from forecast values and should not be interpreted as proof of cause."
    )

    # Data table and export
    st.markdown("### Forecast records")
    display_df = city_df.sort_values("valid_time", ascending=False).copy()
    st.dataframe(display_df, width="stretch", hide_index=True)

    csv = display_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download filtered data (CSV)",
        data=csv,
        file_name="urbanpulse_forecast_data.csv",
        mime="text/csv",
        width="stretch",
    )
    st.caption(
        f"Showing {len(display_df)} records · Forecast type: "
        f"{', '.join(display_df['data_kind'].dropna().unique())}"
    )

except Exception as exc:
    st.error("Unable to load the UrbanPulse dashboard.")
    st.exception(exc)
