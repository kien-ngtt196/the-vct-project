-- Riot's Swiss brackets confirm these finishes without a stored prize.
WITH finishes (event_id, team_name, placement, source_url) AS (
    VALUES
        ('2281', 'kiwoom drx', '5th–6th', 'https://valorantesports.com/en-US/tournament/113481672092259605/stage/113481722807050061'),
        ('2281', 'team liquid', '5th–6th', 'https://valorantesports.com/en-US/tournament/113481672092259605/stage/113481722807050061'),
        ('2281', 'sentinels', '7th–8th', 'https://valorantesports.com/en-US/tournament/113481672092259605/stage/113481722807050061'),
        ('2281', 'trace esports', '7th–8th', 'https://valorantesports.com/en-US/tournament/113481672092259605/stage/113481722807050061'),
        ('2282', 'team liquid', '9th–10th', 'https://valorantesports.com/en-GB/tournament/113482053125573837/stage/113482257443381257'),
        ('2282', 'bilibili gaming', '9th–10th', 'https://valorantesports.com/en-GB/tournament/113482053125573837/stage/113482257443381257'),
        ('2282', 'team heretics', '11th–12th', 'https://valorantesports.com/en-GB/tournament/113482053125573837/stage/113482257443381257'),
        ('2282', 'mibr', '11th–12th', 'https://valorantesports.com/en-GB/tournament/113482053125573837/stage/113482257443381257')
)
INSERT INTO team_event_results (tournament_id, team_id, placement_text, source_url)
SELECT event.id, team.team_id, finishes.placement, finishes.source_url
FROM finishes
JOIN tournaments event ON event.id = finishes.event_id
JOIN teams team ON team.canonical_name = finishes.team_name
ON CONFLICT (tournament_id, team_id) DO UPDATE
SET placement_text = EXCLUDED.placement_text, source_url = EXCLUDED.source_url
WHERE team_event_results.placement_text IS NULL;
