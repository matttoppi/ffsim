SCHEMA_VERSION = 1

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS raw_objects (
    content_hash TEXT PRIMARY KEY,
    endpoint TEXT NOT NULL,
    relative_path TEXT NOT NULL UNIQUE,
    fetched_at TEXT NOT NULL,
    byte_count INTEGER NOT NULL,
    http_status INTEGER NOT NULL DEFAULT 200
);

CREATE TABLE IF NOT EXISTS endpoint_cache (
    endpoint TEXT PRIMARY KEY,
    content_hash TEXT NOT NULL REFERENCES raw_objects(content_hash),
    fetched_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    username TEXT,
    display_name TEXT,
    avatar TEXT,
    is_bot INTEGER,
    raw_hash TEXT REFERENCES raw_objects(content_hash),
    first_seen_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS seeds (
    user_id TEXT PRIMARY KEY REFERENCES users(user_id),
    username TEXT NOT NULL,
    source TEXT NOT NULL,
    added_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS league_seasons (
    league_id TEXT NOT NULL,
    season INTEGER NOT NULL,
    name TEXT NOT NULL,
    status TEXT,
    season_type TEXT,
    total_rosters INTEGER,
    previous_league_id TEXT,
    draft_id TEXT,
    league_type INTEGER,
    best_ball INTEGER,
    max_keepers INTEGER,
    playoff_teams INTEGER,
    playoff_week_start INTEGER,
    last_scored_leg INTEGER,
    settings_json TEXT NOT NULL,
    scoring_settings_json TEXT NOT NULL,
    roster_positions_json TEXT NOT NULL,
    scoring_format TEXT NOT NULL,
    is_candidate INTEGER NOT NULL DEFAULT 0,
    candidate_reasons_json TEXT NOT NULL DEFAULT '[]',
    raw_hash TEXT REFERENCES raw_objects(content_hash),
    first_seen_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (league_id, season)
);

CREATE TABLE IF NOT EXISTS league_provenance (
    league_id TEXT NOT NULL,
    season INTEGER NOT NULL,
    seed_user_id TEXT,
    discovery_depth INTEGER NOT NULL,
    discovering_user_id TEXT,
    source_league_id TEXT,
    mechanism TEXT NOT NULL,
    discovered_at TEXT NOT NULL,
    UNIQUE (
        league_id, season, seed_user_id, discovery_depth,
        discovering_user_id, source_league_id, mechanism
    )
);

CREATE TABLE IF NOT EXISTS rosters (
    league_id TEXT NOT NULL,
    season INTEGER NOT NULL,
    roster_id INTEGER NOT NULL,
    owner_id TEXT,
    co_owners_json TEXT NOT NULL,
    players_json TEXT NOT NULL,
    starters_json TEXT NOT NULL,
    reserve_json TEXT NOT NULL,
    settings_json TEXT NOT NULL,
    raw_hash TEXT REFERENCES raw_objects(content_hash),
    updated_at TEXT NOT NULL,
    PRIMARY KEY (league_id, season, roster_id),
    FOREIGN KEY (league_id, season) REFERENCES league_seasons(league_id, season)
);

CREATE TABLE IF NOT EXISTS drafts (
    draft_id TEXT PRIMARY KEY,
    league_id TEXT,
    season INTEGER NOT NULL,
    status TEXT,
    draft_type TEXT,
    season_type TEXT,
    team_count INTEGER,
    rounds INTEGER,
    start_time INTEGER,
    created_at_ms INTEGER,
    last_picked_ms INTEGER,
    scoring_type TEXT,
    draft_order_json TEXT NOT NULL,
    slot_to_roster_id_json TEXT NOT NULL,
    settings_json TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    raw_hash TEXT REFERENCES raw_objects(content_hash),
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS players (
    player_id TEXT PRIMARY KEY,
    full_name TEXT,
    first_name TEXT,
    last_name TEXT,
    position TEXT,
    nfl_team TEXT,
    status TEXT,
    active INTEGER,
    birth_date TEXT,
    years_exp INTEGER,
    raw_json TEXT NOT NULL,
    raw_hash TEXT REFERENCES raw_objects(content_hash),
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS draft_picks (
    draft_id TEXT NOT NULL REFERENCES drafts(draft_id),
    pick_no INTEGER NOT NULL,
    league_id TEXT,
    season INTEGER NOT NULL,
    round INTEGER,
    draft_slot INTEGER,
    roster_id INTEGER,
    effective_roster_id INTEGER,
    ownership_source TEXT NOT NULL,
    picked_by TEXT,
    player_id TEXT,
    is_keeper INTEGER,
    picked_at_ms INTEGER,
    position TEXT,
    nfl_team TEXT,
    metadata_json TEXT NOT NULL,
    raw_hash TEXT REFERENCES raw_objects(content_hash),
    PRIMARY KEY (draft_id, pick_no)
);

CREATE TABLE IF NOT EXISTS traded_draft_picks (
    draft_id TEXT NOT NULL REFERENCES drafts(draft_id),
    season INTEGER,
    round INTEGER NOT NULL,
    roster_id INTEGER NOT NULL,
    previous_owner_id INTEGER,
    owner_id INTEGER NOT NULL,
    raw_json TEXT NOT NULL,
    raw_hash TEXT REFERENCES raw_objects(content_hash),
    PRIMARY KEY (draft_id, round, roster_id)
);

CREATE TABLE IF NOT EXISTS weekly_matchups (
    league_id TEXT NOT NULL,
    season INTEGER NOT NULL,
    week INTEGER NOT NULL,
    roster_id INTEGER NOT NULL,
    matchup_id INTEGER,
    points REAL,
    custom_points REAL,
    starters_json TEXT NOT NULL,
    players_json TEXT NOT NULL,
    raw_hash TEXT REFERENCES raw_objects(content_hash),
    PRIMARY KEY (league_id, season, week, roster_id),
    FOREIGN KEY (league_id, season) REFERENCES league_seasons(league_id, season)
);

CREATE TABLE IF NOT EXISTS playoff_matches (
    league_id TEXT NOT NULL,
    season INTEGER NOT NULL,
    bracket_type TEXT NOT NULL,
    match_id INTEGER NOT NULL,
    round INTEGER,
    team_1 INTEGER,
    team_2 INTEGER,
    winner INTEGER,
    loser INTEGER,
    placement INTEGER,
    raw_json TEXT NOT NULL,
    raw_hash TEXT REFERENCES raw_objects(content_hash),
    PRIMARY KEY (league_id, season, bracket_type, match_id),
    FOREIGN KEY (league_id, season) REFERENCES league_seasons(league_id, season)
);

CREATE TABLE IF NOT EXISTS team_seasons (
    league_id TEXT NOT NULL,
    season INTEGER NOT NULL,
    roster_id INTEGER NOT NULL,
    owner_id TEXT,
    reported_wins INTEGER,
    reported_losses INTEGER,
    reported_ties INTEGER,
    reported_points_for REAL,
    reported_points_against REAL,
    h2h_wins INTEGER,
    h2h_losses INTEGER,
    h2h_ties INTEGER,
    matchup_points_for REAL,
    regular_season_games INTEGER,
    made_playoffs INTEGER,
    champion INTEGER,
    runner_up INTEGER,
    final_finish INTEGER,
    computed_at TEXT NOT NULL,
    PRIMARY KEY (league_id, season, roster_id),
    FOREIGN KEY (league_id, season, roster_id)
        REFERENCES rosters(league_id, season, roster_id)
);

CREATE TABLE IF NOT EXISTS quality_flags (
    id INTEGER PRIMARY KEY,
    scope TEXT NOT NULL,
    entity_key TEXT NOT NULL,
    code TEXT NOT NULL,
    severity TEXT NOT NULL,
    details_json TEXT NOT NULL,
    detected_at TEXT NOT NULL,
    UNIQUE (scope, entity_key, code)
);

CREATE TABLE IF NOT EXISTS crawl_queue (
    id INTEGER PRIMARY KEY,
    task_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    season INTEGER,
    depth INTEGER NOT NULL,
    seed_user_id TEXT,
    mechanism TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    available_at TEXT NOT NULL,
    claimed_at TEXT,
    completed_at TEXT,
    last_error TEXT,
    UNIQUE (task_type, entity_id, season)
);

CREATE TABLE IF NOT EXISTS hydration_queue (
    league_id TEXT NOT NULL,
    season INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    available_at TEXT NOT NULL,
    claimed_at TEXT,
    completed_at TEXT,
    last_error TEXT,
    PRIMARY KEY (league_id, season),
    FOREIGN KEY (league_id, season) REFERENCES league_seasons(league_id, season)
);

CREATE TABLE IF NOT EXISTS request_failures (
    id INTEGER PRIMARY KEY,
    queue_name TEXT NOT NULL,
    queue_key TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    attempt INTEGER NOT NULL,
    http_status INTEGER,
    error TEXT NOT NULL,
    occurred_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_crawl_queue_status
    ON crawl_queue(status, available_at, depth, id);
CREATE INDEX IF NOT EXISTS idx_hydration_queue_status
    ON hydration_queue(status, available_at, league_id);
CREATE INDEX IF NOT EXISTS idx_league_seasons_candidate
    ON league_seasons(is_candidate, season, league_id);
CREATE INDEX IF NOT EXISTS idx_rosters_owner ON rosters(owner_id);
CREATE INDEX IF NOT EXISTS idx_drafts_league ON drafts(league_id, season);
CREATE INDEX IF NOT EXISTS idx_draft_picks_league ON draft_picks(league_id, season, effective_roster_id);
CREATE INDEX IF NOT EXISTS idx_matchups_league_week ON weekly_matchups(league_id, season, week);
CREATE INDEX IF NOT EXISTS idx_quality_code ON quality_flags(code, severity);
"""
