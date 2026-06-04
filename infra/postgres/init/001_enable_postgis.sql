CREATE EXTENSION IF NOT EXISTS postgis;

CREATE SCHEMA IF NOT EXISTS raw_tdx;

CREATE TABLE IF NOT EXISTS raw_tdx.motorcycle_waiting_zones (
    id BIGSERIAL PRIMARY KEY,
    source_endpoint TEXT NOT NULL,
    source_id TEXT NOT NULL,
    city TEXT,
    district TEXT,
    name TEXT,
    road_name TEXT,
    direction TEXT,
    raw JSONB NOT NULL,
    geom geometry(Geometry, 4326),
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source_endpoint, source_id)
);

CREATE INDEX IF NOT EXISTS idx_motorcycle_waiting_zones_geom
    ON raw_tdx.motorcycle_waiting_zones
    USING GIST (geom);

CREATE TABLE IF NOT EXISTS raw_tdx.motorcycle_lane_restrictions (
    id BIGSERIAL PRIMARY KEY,
    source_endpoint TEXT NOT NULL,
    source_id TEXT NOT NULL,
    city TEXT,
    district TEXT,
    road_name TEXT,
    direction TEXT,
    lane_pattern TEXT,
    restriction_type TEXT,
    raw JSONB NOT NULL,
    geom geometry(Geometry, 4326),
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source_endpoint, source_id)
);

CREATE INDEX IF NOT EXISTS idx_motorcycle_lane_restrictions_geom
    ON raw_tdx.motorcycle_lane_restrictions
    USING GIST (geom);

CREATE TABLE IF NOT EXISTS raw_tdx.ingest_runs (
    id BIGSERIAL PRIMARY KEY,
    dataset TEXT NOT NULL,
    source_endpoint TEXT NOT NULL,
    row_count INTEGER NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);
