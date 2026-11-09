UPDATE tournaments
SET tier = 'outside-tier1'
WHERE tier = 'tier1'
  AND title ~* '(ascension|game changers|china evolution series|china threshold)';

UPDATE tournaments AS tournament
SET season_id = season.season_id
FROM seasons AS season
WHERE tournament.season_id IS NULL
  AND season.year BETWEEN 2022 AND 2026
  AND tournament.title ~ ('\m' || season.year::text || '\M');
