# VCT Scout historical database design

## Coverage

Include Tier 1 VCT events from Masters Reykjavík 2022 (VLR event 926) through the date of each refresh. Include Reykjavík in full and review events that span the starting cutoff. The scope covers Masters, Champions, and Tier 1 regional VCT competition. Exclude Tier 2 Challengers, Ascension, and Game Changers. Review historical regional events against the circuit structure of their season and document the evidence for each inclusion. Store season and calendar dates separately so events are evaluated against the cutoff even if their season label differs from their calendar year.

Maintain a reviewed event manifest by season, with source event ID, circuit, region, event type, inclusion decision, and expected series count where independently available. Start from VLR season archives and cross-check event lists, schedules, and results against Riot event pages where available. Use VLR for match, map, and player-stat detail. Evaluate Riot/GRID as an additional source once credentials and historical coverage are confirmed.

## Proposed PostgreSQL model

| Tables | Grain and constraints |
| --- | --- |
| `sources`, `source_records`, `ingestion_runs` | Preserve source IDs, URLs, fetch times, response status, and snapshot references. Retain parser version and run outcome. Preserve source values so records can be replayed and audited. |
| `teams`, `players` | Stable internal IDs. Display names may change and player handles can collide. Map stable external IDs to internal IDs through separate team and player source-ID tables, unique by source and external ID. |
| `team_aliases`, `player_aliases` | Preserve observed text and store a normalized lookup key using Unicode normalization, whitespace cleanup, and case folding. Allow source and validity periods for reused tags and renamed entities. Route ambiguous matches to review. |
| `seasons`, `events`, `event_stages`, `event_entries` | Season year is separate from calendar dates. Model stage, region, format, event registration and placing independently. An event entry can exist without a match. |
| `matches`, `match_teams`, `games`, `maps` | A series belongs to an event stage. Use stable source IDs and unique series slots. Each map played has a unique sequence within its series. Allow scheduled, canceled and forfeited matches, and preserve unknown scores as null. |
| `match_appearances`, `game_player_stats` | Link a player to a participating team and store stats once per game and player. Preserve missing metrics as null. Send unresolved source rows to staging until the player or team can be identified. |
| `roster_memberships`, `roster_evidence`, `event_roster_entries` | Store team, player, role, status, effective start and end, date precision, and supporting sources. Represent active, substitute, loan and bench periods where supported. Event registrations and played maps are separate observations. |
| `team_media`, `player_media` | Track logo or photo, asset URL, source page, credit, reuse status, retrieval date, and optional cached path. Support historical variants and select one preferred asset per display context. |

Resolve `PRX`, `prx`, `Paper Rex`, and `paper rex` to one team ID using a reviewed alias mapping. Normalize casing for lookup. Stable IDs and evidence determine whether a rename represents the same team, a roster transfer, or a different organization. Preserve the label shown in each historical source. Apply the same approach to player handles and avoid automatic merges on name alone.

Roster periods use inclusive starts and exclusive ends when exact dates are known. Keep unknown dates and conflicting evidence visible. Derive moves from evidenced membership changes and retain the announcements behind them. An overlap can be legitimate for a loan, stand-in, or distinct roster, so review overlaps in context. Use VLR profile or event media first, then official team sites, press kits, or verified team/player accounts. Cache assets when reuse is permitted and use a placeholder when no suitable asset is available.

## Backfill and validation

1. Use a disposable database and preserve the existing database and snapshots. Add forward migrations after migration 007 and keep existing web API contracts during the transition.
2. Add manifest-driven event selection and a per-event fetch log. Reuse the parser with throttling, cached raw snapshots and retryable failures. Record discovered, parsed, imported and unresolved match IDs separately.
3. Pilot Reykjavík. VLR lists 24 completed series. Reconcile all 24 source IDs, compare match scores to maps where applicable, and account for missing stats, roster evidence and parser failures. Reimport the same snapshots to verify row counts and identity links stay stable.
4. Audit 2026 with the same manifest process. Compare the expected and stored event and series IDs before filling gaps. Repeat season by season through the remaining scope and publish a coverage report with exclusions and known gaps.
5. Backfill identity and roster evidence before replacing name-based keys. Compare existing profile, history and ranking outputs against the new database before switching the app over. Refresh in-season events incrementally and revisit incomplete or recently corrected results.

References

- [VLR 2022 season archive](https://www.vlr.gg/vct-2022/?region=all)
- [VLR Reykjavík match listing](https://www.vlr.gg/event/matches/926/valorant-champions-tour-stage-1-masters-reykjav-k)
- [Riot and GRID VALORANT Data Portal](https://valorantesports.com/en-US/news/riot-games-and-grid-launch-new-valorant-data-portal/)
