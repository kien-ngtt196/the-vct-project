CREATE TEMP TABLE team_identity_aliases (
    source_name TEXT NOT NULL,
    canonical_name TEXT NOT NULL,
    PRIMARY KEY (source_name, canonical_name)
) ON COMMIT DROP;

INSERT INTO team_identity_aliases (source_name, canonical_name)
VALUES
    ('100 thieves', '100 thieves'), ('100t', '100 thieves'),
    ('a team', 'a team'), ('at', 'a team'),
    ('all gamers', 'all gamers'), ('ag', 'all gamers'),
    ('any questions gaming', 'any questions gaming'), ('aq', 'any questions gaming'),
    ('bbl esports', 'bbl esports'), ('bbl', 'bbl esports'),
    ('bilibili gaming', 'bilibili gaming'), ('blg', 'bilibili gaming'),
    ('cloud9', 'cloud9'), ('c9', 'cloud9'),
    ('detonation focusme', 'detonation focusme'), ('dfm', 'detonation focusme'),
    ('dragon ranger gaming', 'dragon ranger gaming'), ('drg', 'dragon ranger gaming'),
    ('edward gaming', 'edward gaming'), ('edg', 'edward gaming'),
    ('eternal fire', 'eternal fire'), ('ef', 'eternal fire'),
    ('evil geniuses', 'evil geniuses'), ('eg', 'evil geniuses'),
    ('fire flux esports', 'fire flux esports'), ('ff', 'fire flux esports'),
    ('fnatic', 'fnatic'), ('fnc', 'fnatic'),
    ('funplus phoenix', 'funplus phoenix'), ('fpx', 'funplus phoenix'),
    ('full sense', 'full sense'), ('fs', 'full sense'),
    ('furia', 'furia'), ('fur', 'furia'),
    ('fut esports', 'fut esports'), ('fut', 'fut esports'),
    ('g2 esports', 'g2 esports'), ('g2', 'g2 esports'),
    ('global esports', 'global esports'), ('ge', 'global esports'),
    ('geng', 'geng'), ('gen', 'geng'), ('gen g', 'geng'),
    ('giantx', 'giantx'), ('gx', 'giantx'),
    ('jd gaming', 'jd gaming'), ('jdg', 'jd gaming'),
    ('karmine corp', 'karmine corp'), ('kc', 'karmine corp'),
    ('keepbest gaming', 'keepbest gaming'), ('kbg', 'keepbest gaming'),
    ('kiwoom drx', 'kiwoom drx'), ('krx', 'kiwoom drx'),
    ('leviatán', 'leviatán'), ('lev', 'leviatán'),
    ('nova esports', 'nova esports'), ('nova', 'nova esports'),
    ('natus vincere', 'natus vincere'), ('navi', 'natus vincere'),
    ('nongshim redforce', 'nongshim redforce'),
    ('nongshin redforce', 'nongshim redforce'), ('ns', 'nongshim redforce'),
    ('octagonal disposition gaming', 'octagonal disposition gaming'),
    ('odg', 'octagonal disposition gaming'),
    ('onside gaming', 'onside gaming'), ('ong', 'onside gaming'),
    ('paper rex', 'paper rex'), ('paperrex', 'paper rex'), ('prx', 'paper rex'),
    ('pcific esports', 'pcific esports'), ('pcf', 'pcific esports'),
    ('rare atom', 'rare atom'), ('ra', 'rare atom'),
    ('rex regum qeon', 'rex regum qeon'), ('rrq', 'rex regum qeon'),
    ('sentinels', 'sentinels'), ('sen', 'sentinels'),
    ('team heretics', 'team heretics'), ('th', 'team heretics'),
    ('team liquid', 'team liquid'), ('tl', 'team liquid'),
    ('team secret', 'team secret'), ('ts', 'team secret'),
    ('team vitality', 'team vitality'), ('vit', 'team vitality'),
    ('titan esports club', 'titan esports club'), ('tec', 'titan esports club'),
    ('tyloo', 'tyloo'), ('tyl', 'tyloo'),
    ('trace esports', 'trace esports'), ('te', 'trace esports'),
    ('ulf esports', 'ulf esports'), ('ulf', 'ulf esports'),
    ('unsettled resentment', 'unsettled resentment'), ('ur', 'unsettled resentment'),
    ('victory no limits gaming', 'victory no limits gaming'),
    ('vlg', 'victory no limits gaming'),
    ('weibo gaming', 'weibo gaming'), ('wbg', 'weibo gaming'),
    ('wolves esports', 'wolves esports'), ('wol', 'wolves esports'),
    ('world sports invictus gaming', 'world sports invictus gaming'),
    ('wsig', 'world sports invictus gaming'),
    ('xi lai gaming', 'xi lai gaming'), ('xlg', 'xi lai gaming'),
    ('zeta division', 'zeta division'), ('zeta', 'zeta division');

CREATE TEMP TABLE team_identity_groups (
    canonical_name TEXT PRIMARY KEY,
    keeper_id INTEGER NOT NULL
) ON COMMIT DROP;

INSERT INTO team_identity_groups (canonical_name, keeper_id)
SELECT aliases.canonical_name,
       COALESCE(
           MAX(team.team_id) FILTER (WHERE team.canonical_name = aliases.canonical_name),
           MIN(team.team_id)
       )
FROM team_identity_aliases aliases
JOIN teams team ON lower(team.canonical_name) = aliases.source_name
GROUP BY aliases.canonical_name;

CREATE TEMP TABLE team_identity_members (
    team_id INTEGER PRIMARY KEY,
    keeper_id INTEGER NOT NULL,
    canonical_name TEXT NOT NULL
) ON COMMIT DROP;

INSERT INTO team_identity_members (team_id, keeper_id, canonical_name)
SELECT DISTINCT team.team_id, groups.keeper_id, groups.canonical_name
FROM team_identity_aliases aliases
JOIN teams team ON lower(team.canonical_name) = aliases.source_name
JOIN team_identity_groups groups ON groups.canonical_name = aliases.canonical_name;

INSERT INTO team_aliases (team_id, alias_name)
SELECT members.keeper_id, aliases.alias_name
FROM team_identity_members members
JOIN team_aliases aliases ON aliases.team_id = members.team_id
ON CONFLICT (team_id, alias_name) DO NOTHING;

INSERT INTO team_aliases (team_id, alias_name)
SELECT groups.keeper_id, aliases.source_name
FROM team_identity_aliases aliases
JOIN team_identity_groups groups ON groups.canonical_name = aliases.canonical_name
ON CONFLICT (team_id, alias_name) DO NOTHING;

UPDATE teams keeper
SET source_url = COALESCE(keeper.source_url, source.source_url),
    logo_url = COALESCE(keeper.logo_url, source.logo_url)
FROM team_identity_members members
JOIN teams source ON source.team_id = members.team_id
WHERE keeper.team_id = members.keeper_id
  AND members.team_id <> members.keeper_id;

UPDATE matches match
SET team1_id = members.keeper_id
FROM team_identity_members members
WHERE match.team1_id = members.team_id
  AND members.team_id <> members.keeper_id;

UPDATE matches match
SET team2_id = members.keeper_id
FROM team_identity_members members
WHERE match.team2_id = members.team_id
  AND members.team_id <> members.keeper_id;

UPDATE player_stats stats
SET team_id = members.keeper_id
FROM team_identity_members members
WHERE stats.team_id = members.team_id
  AND members.team_id <> members.keeper_id;

CREATE TEMP TABLE team_merged_appearances ON COMMIT DROP AS
SELECT appearances.match_id, appearances.player_id, members.keeper_id AS team_id,
       MIN(appearances.first_seen_at) AS first_seen_at,
       MIN(appearances.source_url) FILTER (WHERE appearances.source_url IS NOT NULL) AS source_url
FROM match_players appearances
JOIN team_identity_members members ON members.team_id = appearances.team_id
GROUP BY appearances.match_id, appearances.player_id, members.keeper_id;

DELETE FROM match_players appearances
USING team_identity_members members
WHERE appearances.team_id = members.team_id;

INSERT INTO match_players (match_id, player_id, team_id, first_seen_at, source_url)
SELECT match_id, player_id, team_id, first_seen_at, source_url
FROM team_merged_appearances
ON CONFLICT (match_id, player_id, team_id) DO UPDATE SET
    first_seen_at = LEAST(match_players.first_seen_at, EXCLUDED.first_seen_at),
    source_url = COALESCE(match_players.source_url, EXCLUDED.source_url);

UPDATE roster_memberships memberships
SET team_id = members.keeper_id
FROM team_identity_members members
WHERE memberships.team_id = members.team_id
  AND members.team_id <> members.keeper_id;

UPDATE teams team
SET canonical_name = groups.canonical_name
FROM team_identity_groups groups
WHERE team.team_id = groups.keeper_id
  AND team.canonical_name <> groups.canonical_name;

DELETE FROM team_aliases aliases
USING team_identity_members members
WHERE aliases.team_id = members.team_id
  AND members.team_id <> members.keeper_id;

DELETE FROM teams team
USING team_identity_members members
WHERE team.team_id = members.team_id
  AND members.team_id <> members.keeper_id;
