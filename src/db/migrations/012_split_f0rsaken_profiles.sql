-- VLR IDs 9801 and 12088 belong to different players with the same alias.
INSERT INTO players (canonical_name, source_url, nationality)
SELECT 'f0rsaken (brazil)', 'https://www.vlr.gg/player/12088/f0rsaken', 'Brazil'
FROM players original
WHERE original.canonical_name = 'f0rsaken'
  AND EXISTS (
      SELECT 1 FROM match_players appearance
      WHERE appearance.player_id = original.player_id
        AND appearance.source_url ~ '/player/12088(/|$)'
  )
ON CONFLICT (canonical_name) DO NOTHING;

INSERT INTO player_aliases (player_id, alias_name)
SELECT player_id, 'f0rsaken' FROM players WHERE canonical_name = 'f0rsaken (brazil)'
ON CONFLICT (player_id, alias_name) DO NOTHING;

UPDATE player_stats stats
SET player_id = brazil.player_id
FROM players original, players brazil, games game, match_players appearance
WHERE original.canonical_name = 'f0rsaken'
  AND brazil.canonical_name = 'f0rsaken (brazil)'
  AND stats.player_id = original.player_id
  AND stats.game_id = game.id
  AND appearance.match_id = game.match_id
  AND appearance.team_id = stats.team_id
  AND appearance.player_id = original.player_id
  AND appearance.source_url ~ '/player/12088(/|$)';

UPDATE match_players appearance
SET player_id = brazil.player_id
FROM players original, players brazil
WHERE original.canonical_name = 'f0rsaken'
  AND brazil.canonical_name = 'f0rsaken (brazil)'
  AND appearance.player_id = original.player_id
  AND appearance.source_url ~ '/player/12088(/|$)';

UPDATE players
SET source_url = 'https://www.vlr.gg/player/9801/f0rsaken',
    nationality = 'Indonesia'
WHERE canonical_name = 'f0rsaken';
