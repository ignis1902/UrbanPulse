from datetime import timedelta

import pandas as pd
import plotly.express as px
import streamlit as st

DATA_PATH = (
    "data/historical/pune_station_hourly_aqi.csv"
)
TIMEZONE = "Asia/Kolkata"

st.set_page_config(
    page_title="UrbanPulse | Historical AQI",
    page_icon="🌆",
    layout="wide",
)

@st.cache_data
def load_data():
    df = pd.read_csv(DATA_PATH)
    df["timestamp"] = pd.to_datetime(
        df["timestamp"], utc=True
    ).dt.tz_convert(TIMEZONE)
    df["aqi"] = pd.to_numeric(df["aqi"], errors="coerce")
    df = df.dropna(subset=["timestamp", "station", "aqi"])
    return df.sort_values("timestamp")

try:
    df = load_data()
except Exception as exc:
    st.error(f"Could not load historical AQI data: {exc}")
    st.stop()

st.title("UrbanPulse")
st.subheader("Historical Air Quality Intelligence")
st.caption(
    "Pune monitoring-station AQI history | 2017–2023 "
    "| Historical station records, not live measurements"
)

min_date = df["timestamp"].min().date()
max_date = df["timestamp"].max().date()

with st.sidebar:
    st.header("Filters")

    stations = sorted(df["station"].unique())
    chosen_stations = st.multiselect(
        "Monitoring stations",
        stations,
        default=stations,
    )

    date_range = st.date_input(
        "Date range",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date,
    )

    st.caption("All dates and times are displayed in India Standard Time.")

if not chosen_stations:
    st.warning("Select at least one monitoring station.")
    st.stop()

if not isinstance(date_range, (tuple, list)) or len(date_range) != 2:
    st.info("Select both a start date and an end date.")
    st.stop()

start_date, end_date = date_range

if start_date > end_date:
    st.error("The start date must be before the end date.")
    st.stop()

start = pd.Timestamp(start_date, tz=TIMEZONE)
end = pd.Timestamp(
    end_date + timedelta(days=1), tz=TIMEZONE
)

filtered = df[
    df["station"].isin(chosen_stations)
    & (df["timestamp"] >= start)
    & (df["timestamp"] < end)
].copy()

if filtered.empty:
    st.warning("No readings exist for the selected filters.")
    st.stop()

st.caption(
    f"Showing {start_date} through {end_date}. "
    "Missing hours are not treated as zero."
)

# KPI cards
col1, col2, col3, col4 = st.columns(4)

col1.metric("Recorded readings", f"{len(filtered):,}")
col2.metric("Mean AQI", f"{filtered['aqi'].mean():.1f}")
col3.metric("Median AQI", f"{filtered['aqi'].median():.1f}")
col4.metric("Maximum AQI", f"{filtered['aqi'].max():.0f}")

st.divider()

# Coverage table for the selected period
st.subheader("Station coverage")

expected_hours = int((end - start).total_seconds() / 3600)
coverage_rows = []

for station in chosen_stations:
    station_df = filtered[filtered["station"] == station]
    coverage_rows.append({
        "Station": station,
        "Readings": len(station_df),
        "Expected hourly slots": expected_hours,
        "Coverage (%)": round(
            100 * len(station_df) / expected_hours, 2
        ),
        "First reading": (
            station_df["timestamp"].min().strftime("%Y-%m-%d %H:%M")
            if not station_df.empty else "—"
        ),
        "Last reading": (
            station_df["timestamp"].max().strftime("%Y-%m-%d %H:%M")
            if not station_df.empty else "—"
        ),
    })

coverage = pd.DataFrame(coverage_rows)
st.dataframe(coverage, hide_index=True, width="stretch")

st.caption(
    "Coverage is the proportion of possible hourly timestamps "
    "with a recorded reading. It does not imply continuous monitoring "
    "or independently verified data quality."
)

# Reindex each station onto a complete hourly timeline.
# Missing timestamps remain NaN, so the line chart shows gaps.
st.subheader("Hourly AQI timeline")
st.caption(
    "Breaks in the lines indicate missing readings. "
    "No missing values are interpolated."
)

full_index = pd.date_range(
    start=start,
    end=end - pd.Timedelta(hours=1),
    freq="h",
)

plot_parts = []

for station in chosen_stations:
    station_series = (
        filtered[filtered["station"] == station]
        .set_index("timestamp")["aqi"]
        .sort_index()
    )

    station_series = station_series.reindex(full_index)

    part = station_series.rename_axis("timestamp").reset_index()
    part["station"] = station
    plot_parts.append(part)

hourly_plot = pd.concat(plot_parts, ignore_index=True)

fig = px.line(
    hourly_plot,
    x="timestamp",
    y="aqi",
    color="station",
    title="Recorded AQI by time",
    labels={
        "timestamp": "Date and time (IST)",
        "aqi": "AQI",
        "station": "Monitoring station",
    },
)
fig.update_traces(connectgaps=False)
fig.update_layout(legend_title_text="Station")
st.plotly_chart(fig, width="stretch")

# Daily means, with missing dates retained as gaps.
st.subheader("Daily average AQI")

daily_parts = []

for station in chosen_stations:
    station_df = filtered[filtered["station"] == station].copy()

    daily = (
        station_df.set_index("timestamp")["aqi"]
        .resample("D")
        .mean()
        .rename("daily_mean_aqi")
        .reindex(pd.date_range(
            start=start.normalize(),
            end=(end - pd.Timedelta(days=1)).normalize(),
            freq="D",
        ))
        .rename_axis("date")
        .reset_index()
    )

    daily["station"] = station
    daily_parts.append(daily)

daily_plot = pd.concat(daily_parts, ignore_index=True)

daily_fig = px.line(
    daily_plot,
    x="date",
    y="daily_mean_aqi",
    color="station",
    title="Daily mean of available hourly readings",
    labels={
        "date": "Date",
        "daily_mean_aqi": "Mean AQI",
        "station": "Monitoring station",
    },
)
daily_fig.update_traces(connectgaps=False)
st.plotly_chart(daily_fig, width="stretch")

# Distribution
st.subheader("AQI distribution by station")

distribution_fig = px.box(
    filtered,
    x="station",
    y="aqi",
    color="station",
    points=False,
    title="Distribution of recorded AQI",
    labels={"station": "Monitoring station", "aqi": "AQI"},
)
st.plotly_chart(distribution_fig, width="stretch")

# Download filtered data
st.subheader("Export filtered records")

download_df = filtered.copy()
download_df["timestamp"] = download_df["timestamp"].astype(str)

st.download_button(
    "Download filtered CSV",
    data=download_df.to_csv(index=False).encode("utf-8"),
    file_name="urbanpulse_filtered_station_aqi.csv",
    mime="text/csv",
)

st.caption(
    "Data source: converted OpenCity station CSV files. "
    "Station labels and AQI definitions should be verified against "
    "the original source metadata before publication."
)
