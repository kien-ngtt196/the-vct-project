CREATE TEMP TABLE team_identity_aliases_005 (
    source_name TEXT NOT NULL,
    canonical_name TEXT NOT NULL,
    PRIMARY KEY (source_name, canonical_name)
) ON COMMIT DROP;

INSERT INTO team_identity_aliases_005 (source_name, canonical_name)
VALUES
    ('bilibili gaming', 'bilibili gaming'),
    ('blg', 'bilibili gaming'),
    ('guangzhou huadu bilibili gamingbilibili gaming', 'bilibili gaming'),
    ('jd gaming', 'jd gaming'),
    ('jdg', 'jd gaming'),
    ('jd mall jdg esportsjd gaming', 'jd gaming'),
    ('krü esports', 'krü esports'),
    ('krü', 'krü esports'),
    ('kru', 'krü esports'),
    ('kru esports', 'krü esports'),
    ('titan esports club', 'titan esports club'),
    ('tec', 'titan esports club'),
    ('wuxi titan esports clubtitan esports club', 'titan esports club');

CREATE TEMP TABLE team_identity_groups_005 (
    canonical_name TEXT PRIMARY KEY,
    keeper_id INTEGER NOT NULL
) ON COMMIT DROP;

INSERT INTO team_identity_groups_005 (canonical_name, keeper_id)
SELECT aliases.canonical_name,
       COALESCE(
           MAX(team.team_id) FILTER (WHERE team.canonical_name = aliases.canonical_name),
           MIN(team.team_id)
       )
FROM team_identity_aliases_005 aliases
JOIN teams team ON lower(team.canonical_name) = aliases.source_name
GROUP BY aliases.canonical_name;

CREATE TEMP TABLE team_identity_members_005 (
    team_id INTEGER PRIMARY KEY,
    keeper_id INTEGER NOT NULL,
    canonical_name TEXT NOT NULL
) ON COMMIT DROP;

INSERT INTO team_identity_members_005 (team_id, keeper_id, canonical_name)
SELECT DISTINCT team.team_id, groups.keeper_id, groups.canonical_name
FROM team_identity_aliases_005 aliases
JOIN teams team ON lower(team.canonical_name) = aliases.source_name
JOIN team_identity_groups_005 groups ON groups.canonical_name = aliases.canonical_name;

INSERT INTO team_aliases (team_id, alias_name)
SELECT members.keeper_id, aliases.alias_name
FROM team_identity_members_005 members
JOIN team_aliases aliases ON aliases.team_id = members.team_id
ON CONFLICT (team_id, alias_name) DO NOTHING;

INSERT INTO team_aliases (team_id, alias_name)
SELECT groups.keeper_id, aliases.source_name
FROM team_identity_aliases_005 aliases
JOIN team_identity_groups_005 groups ON groups.canonical_name = aliases.canonical_name
ON CONFLICT (team_id, alias_name) DO NOTHING;

UPDATE teams keeper
SET source_url = COALESCE(keeper.source_url, source.source_url),
    logo_url = COALESCE(keeper.logo_url, source.logo_url)
FROM team_identity_members_005 members
JOIN teams source ON source.team_id = members.team_id
WHERE keeper.team_id = members.keeper_id
  AND members.team_id <> members.keeper_id;

UPDATE matches match
SET team1_id = members.keeper_id
FROM team_identity_members_005 members
WHERE match.team1_id = members.team_id
  AND members.team_id <> members.keeper_id;

UPDATE matches match
SET team2_id = members.keeper_id
FROM team_identity_members_005 members
WHERE match.team2_id = members.team_id
  AND members.team_id <> members.keeper_id;

UPDATE player_stats stats
SET team_id = members.keeper_id
FROM team_identity_members_005 members
WHERE stats.team_id = members.team_id
  AND members.team_id <> members.keeper_id;

CREATE TEMP TABLE team_merged_appearances_005 ON COMMIT DROP AS
SELECT appearances.match_id, appearances.player_id, members.keeper_id AS team_id,
       MIN(appearances.first_seen_at) AS first_seen_at,
       MIN(appearances.source_url) FILTER (WHERE appearances.source_url IS NOT NULL) AS source_url
FROM match_players appearances
JOIN team_identity_members_005 members ON members.team_id = appearances.team_id
GROUP BY appearances.match_id, appearances.player_id, members.keeper_id;

DELETE FROM match_players appearances
USING team_identity_members_005 members
WHERE appearances.team_id = members.team_id;

INSERT INTO match_players (match_id, player_id, team_id, first_seen_at, source_url)
SELECT match_id, player_id, team_id, first_seen_at, source_url
FROM team_merged_appearances_005
ON CONFLICT (match_id, player_id, team_id) DO UPDATE SET
    first_seen_at = LEAST(match_players.first_seen_at, EXCLUDED.first_seen_at),
    source_url = COALESCE(match_players.source_url, EXCLUDED.source_url);

UPDATE roster_memberships memberships
SET team_id = members.keeper_id
FROM team_identity_members_005 members
WHERE memberships.team_id = members.team_id
  AND members.team_id <> members.keeper_id;

UPDATE teams team
SET canonical_name = groups.canonical_name
FROM team_identity_groups_005 groups
WHERE team.team_id = groups.keeper_id
  AND team.canonical_name <> groups.canonical_name;

DELETE FROM team_aliases aliases
USING team_identity_members_005 members
WHERE aliases.team_id = members.team_id
  AND members.team_id <> members.keeper_id;

DELETE FROM teams team
USING team_identity_members_005 members
WHERE team.team_id = members.team_id
  AND members.team_id <> members.keeper_id;
