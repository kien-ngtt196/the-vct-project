ALTER TABLE seasons ADD COLUMN IF NOT EXISTS year INTEGER;
ALTER TABLE tournaments ADD COLUMN IF NOT EXISTS season_id INTEGER REFERENCES seasons(season_id);
ALTER TABLE tournaments ADD COLUMN IF NOT EXISTS tier VARCHAR(20) NOT NULL DEFAULT 'tier1';
ALTER TABLE tournaments ADD COLUMN IF NOT EXISTS region VARCHAR(100);
ALTER TABLE tournaments ADD COLUMN IF NOT EXISTS start_date DATE;
ALTER TABLE tournaments ADD COLUMN IF NOT EXISTS end_date DATE;
ALTER TABLE tournaments ADD COLUMN IF NOT EXISTS logo_url TEXT;
ALTER TABLE tournaments ADD COLUMN IF NOT EXISTS last_scraped_at TIMESTAMPTZ;
ALTER TABLE teams ADD COLUMN IF NOT EXISTS source_url TEXT;
ALTER TABLE teams ADD COLUMN IF NOT EXISTS logo_url TEXT;
ALTER TABLE players ADD COLUMN IF NOT EXISTS source_url TEXT;
ALTER TABLE players ADD COLUMN IF NOT EXISTS image_url TEXT;
ALTER TABLE players ADD COLUMN IF NOT EXISTS nationality TEXT;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS team1_id INTEGER REFERENCES teams(team_id);
ALTER TABLE matches ADD COLUMN IF NOT EXISTS team2_id INTEGER REFERENCES teams(team_id);
ALTER TABLE matches ADD COLUMN IF NOT EXISTS season_id INTEGER REFERENCES seasons(season_id);
ALTER TABLE games ADD COLUMN IF NOT EXISTS map_id INTEGER REFERENCES maps(map_id);
ALTER TABLE games ADD COLUMN IF NOT EXISTS season_id INTEGER REFERENCES seasons(season_id);
ALTER TABLE player_stats ADD COLUMN IF NOT EXISTS team_id INTEGER REFERENCES teams(team_id);
ALTER TABLE player_stats ADD COLUMN IF NOT EXISTS player_id INTEGER REFERENCES players(player_id);
ALTER TABLE player_stats ADD COLUMN IF NOT EXISTS season_id INTEGER REFERENCES seasons(season_id);

UPDATE seasons
SET year = CASE
    WHEN season_name ~ '^[0-9]{4}$' THEN season_name::INTEGER
    ELSE NULL
END
WHERE year IS NULL;

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

DO $migration$
BEGIN
    IF to_regclass('public.team_roster_history') IS NOT NULL THEN
        INSERT INTO roster_memberships (
            player_id, team_id, start_date, end_date, status, source, notes
        )
        SELECT old_roster.player_id, old_roster.team_id,
               old_roster.start_date, old_roster.end_date, 'unverified',
               'legacy-season-roster',
               'Season-only membership imported from legacy schema: ' || season.season_name
        FROM team_roster_history old_roster
        JOIN seasons season ON season.season_id = old_roster.season_id
        ON CONFLICT DO NOTHING;
    END IF;
END;
$migration$;

INSERT INTO match_players (match_id, player_id, team_id, first_seen_at, source_url)
SELECT DISTINCT m.id, stats.player_id, stats.team_id, m.match_date, player.source_url
FROM player_stats stats
JOIN games game ON game.id = stats.game_id
JOIN matches m ON m.id = game.match_id
JOIN players player ON player.player_id = stats.player_id
WHERE stats.player_id IS NOT NULL
  AND stats.team_id IS NOT NULL
  AND m.match_date IS NOT NULL
ON CONFLICT (match_id, player_id, team_id) DO NOTHING;

CREATE INDEX IF NOT EXISTS idx_matches_date ON matches (match_date);
CREATE INDEX IF NOT EXISTS idx_matches_teams_date ON matches (team1_id, team2_id, match_date DESC);
CREATE INDEX IF NOT EXISTS idx_player_stats_player ON player_stats (player_id);
CREATE INDEX IF NOT EXISTS idx_player_stats_team ON player_stats (team_id);
CREATE INDEX IF NOT EXISTS idx_player_stats_game ON player_stats (game_id);
CREATE INDEX IF NOT EXISTS idx_match_players_player ON match_players (player_id, first_seen_at DESC);
CREATE INDEX IF NOT EXISTS idx_roster_memberships_player_dates
    ON roster_memberships (player_id, start_date, end_date);
CREATE INDEX IF NOT EXISTS idx_roster_memberships_team_dates
    ON roster_memberships (team_id, start_date, end_date);
