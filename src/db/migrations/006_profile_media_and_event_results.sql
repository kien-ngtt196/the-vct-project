ALTER TABLE teams
    ADD COLUMN IF NOT EXISTS logo_local_path TEXT;

ALTER TABLE players
    ADD COLUMN IF NOT EXISTS image_local_path TEXT;

ALTER TABLE tournaments
    ADD COLUMN IF NOT EXISTS prize_pool TEXT;

CREATE TABLE IF NOT EXISTS team_event_results (
    tournament_id VARCHAR(50) NOT NULL REFERENCES tournaments(id) ON DELETE CASCADE,
    team_id INTEGER NOT NULL REFERENCES teams(team_id) ON DELETE CASCADE,
    placement_text TEXT,
    prize TEXT,
    source_url TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tournament_id, team_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_vlr_current_roster_membership
    ON roster_memberships (player_id, team_id)
    WHERE status = 'current' AND source = 'vlr-team-page';

CREATE UNIQUE INDEX IF NOT EXISTS idx_vlr_event_roster_membership
    ON roster_memberships (player_id, team_id, source_url)
    WHERE source = 'vlr-event-page';

CREATE INDEX IF NOT EXISTS idx_team_event_results_team
    ON team_event_results (team_id, tournament_id);
