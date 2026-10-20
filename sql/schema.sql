
CREATE TABLE IF NOT EXISTS ingestion_runs (
    run_id BIGSERIAL PRIMARY KEY,
    source_name TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'running'
        CHECK (status IN ('running', 'succeeded', 'failed')),
    records_written INTEGER NOT NULL DEFAULT 0,
    error_message TEXT
);

CREATE TABLE IF NOT EXISTS environmental_hourly_snapshots (
    snapshot_id BIGSERIAL PRIMARY KEY,
    run_id BIGINT NOT NULL REFERENCES ingestion_runs(run_id),
    city TEXT NOT NULL,
    location_id TEXT NOT NULL,
    data_kind TEXT NOT NULL DEFAULT 'model_forecast'
        CHECK (data_kind IN ('model_forecast', 'observed')),
    valid_time TIMESTAMPTZ NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    pm2_5 DOUBLE PRECISION,
    pm10 DOUBLE PRECISION,
    nitrogen_dioxide DOUBLE PRECISION,
    ozone DOUBLE PRECISION,
    european_aqi INTEGER,
    us_aqi INTEGER,
    temperature_2m DOUBLE PRECISION,
    relative_humidity_2m DOUBLE PRECISION,
    wind_speed_10m DOUBLE PRECISION,
    precipitation DOUBLE PRECISION,
    CONSTRAINT uq_snapshot_per_run
        UNIQUE (run_id, location_id, valid_time)
);

CREATE INDEX IF NOT EXISTS idx_environmental_valid_time
    ON environmental_hourly_snapshots (valid_time);

CREATE INDEX IF NOT EXISTS idx_environmental_city_time
    ON environmental_hourly_snapshots (city, valid_time DESC);

CREATE INDEX IF NOT EXISTS idx_environmental_run
    ON environmental_hourly_snapshots (run_id);

-- Latest forecast values, updated on each successful ingestion.
CREATE TABLE IF NOT EXISTS latest_environmental_forecasts (
    forecast_id BIGSERIAL PRIMARY KEY,
    city TEXT NOT NULL,
    location_id TEXT NOT NULL,
    data_kind TEXT NOT NULL DEFAULT 'model_forecast'
        CHECK (data_kind IN ('model_forecast', 'observed')),
    valid_time TIMESTAMPTZ NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_run_id BIGINT NOT NULL REFERENCES ingestion_runs(run_id),
    pm2_5 DOUBLE PRECISION,
    pm10 DOUBLE PRECISION,
    nitrogen_dioxide DOUBLE PRECISION,
    ozone DOUBLE PRECISION,
    european_aqi INTEGER,
    us_aqi INTEGER,
    temperature_2m DOUBLE PRECISION,
    relative_humidity_2m DOUBLE PRECISION,
    wind_speed_10m DOUBLE PRECISION,
    precipitation DOUBLE PRECISION,
    CONSTRAINT uq_latest_location_kind_time
        UNIQUE (location_id, data_kind, valid_time)
);

CREATE INDEX IF NOT EXISTS idx_latest_environmental_valid_time
    ON latest_environmental_forecasts (valid_time);

CREATE INDEX IF NOT EXISTS idx_latest_environmental_city_time
    ON latest_environmental_forecasts (city, valid_time DESC);
