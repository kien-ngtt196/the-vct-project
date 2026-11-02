INSERT INTO team_aliases (team_id, alias_name)
SELECT team.team_id, alias.alias_name
FROM teams team
JOIN (
    VALUES
        ('krü esports', 'kr esports'),
        ('leviatán', 'leviat n')
) AS alias(canonical_name, alias_name)
  ON lower(team.canonical_name) = alias.canonical_name
ON CONFLICT (team_id, alias_name) DO NOTHING;
