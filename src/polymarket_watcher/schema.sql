-- polymarket-watcher schema (MVP)

CREATE TABLE IF NOT EXISTS markets (
    condition_id TEXT PRIMARY KEY,
    token_id_yes TEXT,
    token_id_no TEXT,
    slug TEXT,
    question TEXT,
    end_date_ts INTEGER,
    closed INTEGER NOT NULL DEFAULT 0,
    resolution_outcome TEXT,
    event_slug TEXT,
    created_at INTEGER,
    updated_at INTEGER
);

CREATE TABLE IF NOT EXISTS price_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    condition_id TEXT NOT NULL,
    snapshot_at_ts INTEGER NOT NULL,
    price REAL NOT NULL,
    source TEXT,
    FOREIGN KEY (condition_id) REFERENCES markets(condition_id)
);

CREATE TABLE IF NOT EXISTS price_series (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    condition_id TEXT NOT NULL,
    t INTEGER NOT NULL,
    p REAL NOT NULL,
    FOREIGN KEY (condition_id) REFERENCES markets(condition_id)
);

CREATE INDEX IF NOT EXISTS idx_price_series_condition_t ON price_series(condition_id, t);
CREATE UNIQUE INDEX IF NOT EXISTS idx_price_series_condition_t_unique ON price_series(condition_id, t);

CREATE TABLE IF NOT EXISTS live_ticks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    condition_id TEXT NOT NULL,
    t INTEGER NOT NULL,
    price REAL NOT NULL,
    event_type TEXT,
    FOREIGN KEY (condition_id) REFERENCES markets(condition_id)
);

CREATE TABLE IF NOT EXISTS predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    condition_id TEXT NOT NULL,
    model_type TEXT NOT NULL,
    predicted_prob REAL NOT NULL,
    created_at INTEGER,
    FOREIGN KEY (condition_id) REFERENCES markets(condition_id)
);

CREATE TABLE IF NOT EXISTS brier_aggregates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period TEXT NOT NULL,
    period_start_ts INTEGER,
    n_markets INTEGER NOT NULL,
    brier_score REAL NOT NULL,
    updated_at INTEGER
);

CREATE TABLE IF NOT EXISTS particle_filter_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    condition_id TEXT NOT NULL,
    run_type TEXT NOT NULL,
    started_at INTEGER,
    final_estimate REAL,
    outcome INTEGER,
    created_at INTEGER,
    FOREIGN KEY (condition_id) REFERENCES markets(condition_id)
);

CREATE TABLE IF NOT EXISTS pf_live_estimates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    condition_id TEXT NOT NULL,
    ts INTEGER NOT NULL,
    estimate REAL NOT NULL,
    created_at INTEGER,
    FOREIGN KEY (condition_id) REFERENCES markets(condition_id)
);

CREATE TABLE IF NOT EXISTS watched_markets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    condition_id TEXT NOT NULL UNIQUE,
    token_id_yes TEXT NOT NULL,
    slug TEXT,
    created_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_watched_markets_condition_id ON watched_markets(condition_id);
