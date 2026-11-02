CREATE TABLE IF NOT EXISTS seasons (
    season_id SERIAL PRIMARY KEY,
    season_name VARCHAR(20) UNIQUE NOT NULL,
    year INTEGER UNIQUE
);

CREATE TABLE IF NOT EXISTS teams (
    team_id SERIAL PRIMARY KEY,
    canonical_name TEXT UNIQUE NOT NULL,
    source_url TEXT,
    logo_url TEXT
);

CREATE TABLE IF NOT EXISTS team_aliases (
    alias_id SERIAL PRIMARY KEY,
    team_id INTEGER NOT NULL REFERENCES teams(team_id) ON DELETE CASCADE,
    alias_name TEXT NOT NULL,
    UNIQUE (team_id, alias_name)
);

CREATE TABLE IF NOT EXISTS players (
    player_id SERIAL PRIMARY KEY,
    canonical_name TEXT UNIQUE NOT NULL,
    source_url TEXT,
    image_url TEXT,
    nationality TEXT
);

CREATE TABLE IF NOT EXISTS player_aliases (
    alias_id SERIAL PRIMARY KEY,
    player_id INTEGER NOT NULL REFERENCES players(player_id) ON DELETE CASCADE,
    alias_name TEXT NOT NULL,
    UNIQUE (player_id, alias_name)
);

CREATE TABLE IF NOT EXISTS maps (
    map_id SERIAL PRIMARY KEY,
    canonical_name TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS tournaments (
    id VARCHAR(50) PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    url VARCHAR(500) NOT NULL,
    status VARCHAR(50) NOT NULL,
    season_id INTEGER REFERENCES seasons(season_id),
    tier VARCHAR(20) NOT NULL DEFAULT 'tier1',
    region VARCHAR(100),
    start_date DATE,
    end_date DATE,
    logo_url TEXT,
    last_scraped_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS matches (
    id VARCHAR(50) PRIMARY KEY,
    tournament_id VARCHAR(50) REFERENCES tournaments(id) ON DELETE CASCADE,
    season_id INTEGER REFERENCES seasons(season_id),
    url VARCHAR(500) NOT NULL,
    status VARCHAR(50),
    format VARCHAR(50),
    team1 VARCHAR(100),
    team2 VARCHAR(100),
    team1_id INTEGER REFERENCES teams(team_id),
    team2_id INTEGER REFERENCES teams(team_id),
    team1_score INTEGER,
    team2_score INTEGER,
    match_date TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS games (
    id VARCHAR(50) PRIMARY KEY,
    match_id VARCHAR(50) REFERENCES matches(id) ON DELETE CASCADE,
    season_id INTEGER REFERENCES seasons(season_id),
    map_name VARCHAR(100),
    map_id INTEGER REFERENCES maps(map_id),
    team1_score INTEGER,
    team2_score INTEGER
);

CREATE TABLE IF NOT EXISTS player_stats (
    id SERIAL PRIMARY KEY,
    game_id VARCHAR(50) REFERENCES games(id) ON DELETE CASCADE,
    player_name VARCHAR(100) NOT NULL,
    player_id INTEGER REFERENCES players(player_id),
    team VARCHAR(100),
    team_id INTEGER REFERENCES teams(team_id),
    season_id INTEGER REFERENCES seasons(season_id),
    nationality VARCHAR(100),
    agent VARCHAR(50),
    rating NUMERIC(5, 3),
    acs NUMERIC(7, 2),
    kills INTEGER,
    deaths INTEGER,
    assists INTEGER,
    kd_diff INTEGER,
    kast_percentage NUMERIC(5, 2),
    adr NUMERIC(7, 2),
    headshot_percentage NUMERIC(5, 2),
    first_kills INTEGER,
    first_deaths INTEGER,
    CONSTRAINT unique_game_player UNIQUE (game_id, player_name)
);

CREATE TABLE IF NOT EXISTS match_players (
    match_id VARCHAR(50) NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    player_id INTEGER NOT NULL REFERENCES players(player_id) ON DELETE CASCADE,
    team_id INTEGER NOT NULL REFERENCES teams(team_id),
    first_seen_at TIMESTAMPTZ NOT NULL,
    source_url TEXT,
    PRIMARY KEY (match_id, player_id, team_id)
);

CREATE TABLE IF NOT EXISTS roster_memberships (
    roster_membership_id BIGSERIAL PRIMARY KEY,
    player_id INTEGER NOT NULL REFERENCES players(player_id) ON DELETE CASCADE,
    team_id INTEGER NOT NULL REFERENCES teams(team_id) ON DELETE CASCADE,
    start_date DATE,
    end_date DATE,
    status VARCHAR(20) NOT NULL DEFAULT 'unverified',
    source VARCHAR(40) NOT NULL,
    source_url TEXT,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT roster_membership_dates_valid
        CHECK (start_date IS NULL OR end_date IS NULL OR end_date >= start_date)
);

CREATE TABLE IF NOT EXISTS ingestion_runs (
    ingestion_run_id BIGSERIAL PRIMARY KEY,
    source VARCHAR(40) NOT NULL,
    input_path TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    events_seen INTEGER NOT NULL DEFAULT 0,
    matches_seen INTEGER NOT NULL DEFAULT 0,
    error TEXT
);
