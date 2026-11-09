# VCT Scout system workflow

This document describes how data moves through the project, what its current
outputs mean, and the recommended sequence for extending it.

## Current system

```text
VLR.gg tier-one event pages
        |
        v
src/scraper/main.py -- timestamped JSON snapshot in data/raw/
        |
        v
src/db/initialize.py -- ordered, versioned PostgreSQL migrations
        |
        v
src/db/import_vlr.py -- idempotent event/match/map/player-stat import
        |
        +--> PostgreSQL search and history queries
        |         |
        |         v
        |    src/web/app.py --> src/web/static/
        |
        +--> 2026 team power index
        |
        +--> VLR team/event profile enrichment and local image assets
                  |
                  v
          leaderboard
```

The scraper uses VLR.gg's `tier=60` event listing, stores that source scope as
`tier1`, and accepts a UTC `--since YYYY-MM-DD` cutoff. Its default is the
beginning of the current UTC year. Requests are retried with bounded backoff;
normal request spacing is intentionally slow to avoid hammering the source.
Review VLR.gg's terms and be considerate of its service before changing the
request rate or running frequent scrapes.

## Data model

| Entity | Purpose |
|---|---|
| `seasons` | Season name and optional numeric year. |
| `teams`, `team_aliases` | Canonical team identity, source/logo URLs, and scraped names. |
| `players`, `player_aliases` | Canonical player identity, VLR profile/image URLs, nationality, and scraped names. |
| `tournaments` | VLR event, tier, season, status, source URL, and available schedule metadata. |
| `matches` | Match-level participants, status, scores, date, and event. Scheduled matches can have no result. |
| `maps`, `games` | Map-level match scores. |
| `player_stats` | Per-player, per-map performance, linked to the game/team/player. |
| `match_players` | Dated evidence that a player appeared for a team in a particular match. This is not a contract or current-roster claim. |
| `roster_memberships` | Separate, source-backed roster tenure with start/end dates, verification status, and evidence URL. |
| `ingestion_runs` | Input snapshot and completion metadata for each import. |
| `schema_migrations` | Applied SQL migration versions. |

Roster movement must be represented by closing the old sourced membership with
an end date and recording the new membership with its own start date and source.
Keep `status` and `source` explicit. Match appearances alone belong in
`match_players`; they must not be used to assert that a player is currently
signed to that team. Do not invent dates when an announcement gives no effective
date—leave them null and preserve the source URL/notes.

The importer maps VLR's abbreviated player team tags to full match participants
only when the source's ten-player rows form two consistent groups of five in
match-header order. Ambiguous groupings are left unresolved rather than guessed.
Team tags and full names are canonicalized to one team identity (for example,
`PRX`/`Paper Rex` and `NS`/`Nongshim RedForce`); searches are case-insensitive.
The canonical team alias migration also consolidates previously split records
and reattaches their match, player-stat, appearance, and roster references.

Database changes go in a new ordered SQL file under `src/db/migrations/`.
Back up a database before applying a migration to a database with valuable
existing data. Do not edit an already-applied migration.

## Normal operating workflow

Run commands from the repository root in PowerShell.

1. Copy `.env.example` to `.env` and set the local PostgreSQL connection
   values there. `.env` is ignored by Git and loaded automatically; keep real
   credentials out of tracked files and chat.
2. Initialize or advance the schema:

   ```powershell
   python -m src.db.initialize
   ```

3. Scrape tier-one data. Use the current year for the first import, then set the
   cutoff to the last successfully imported date for a smaller refresh:

   ```powershell
   python -m src.scraper.main
   ```

   For an incremental refresh, use the last successfully imported date, such
   as `python -m src.scraper.main --since 2026-09-22`.

4. Inspect the printed snapshot path and check that its events are the intended
   tier. Do not overwrite or hand-edit the raw snapshot.
5. Import the newest snapshot, or choose one explicitly:

   ```powershell
   python -m src.db.import_vlr
   python -m src.db.import_vlr --input data/raw/events_YYYYMMDDTHHMMSSZ.json
   ```

   Imports use upserts, so rerunning the same snapshot should not duplicate
   events, matches, maps, or player rows.
6. Refresh VLR profile metadata for teams and players appearing in 2026
   tier-one matches. This also stores event prize-pool text and source-listed
   team notes, checks current VLR team-page rosters, and downloads supported
   team/player images into `src/web/static/assets/`:

   ```powershell
   python -m src.db.sync_vlr_profiles
   ```

   Use `--no-download` to refresh metadata without downloading image files.
   The command makes paced requests to VLR and can take several minutes.
   Event-page roster entries remain unverified historical evidence; current
   roster listings are sourced from VLR team profiles and are not contractual
   claims. Placement notes are shown as listed by VLR, not inferred final
   placements. Event prize pools are not team-specific prize payouts.
7. Run validation:

   ```powershell
   python -m unittest discover -s tests -v
   ```

8. Start the local web app and check search, a player profile, a team history,
   the matchup estimate, and the 2027 watchlist:

   ```powershell
   python -m src.web.app
   ```

   Open `http://127.0.0.1:8000`. If the database is not configured, the page
   remains viewable and the API reports the connection/configuration error.

## Search and player presentation

- Search is limited to imported tier-one data and aliases.
- Player cards show VLR-sourced images when the profile image URL is available,
  recent map-level stats, and a clearly labeled local form index.
- The form index is a presentation summary, not an official VLR rating.
- A player's most recently observed team is not treated as a confirmed roster.
- External player images/profile links are restricted in the UI to VLR-owned
  hostnames. A missing or blocked image gets a neutral fallback.

## Global team ranking

Rankings use completed Tier 1 matches from the selected season. International
achievement contributes 40%, regional achievement 15%, season match results 20%,
recent form 10%, in-game execution 10%, and opponent strength 5%.

For each international event, a winner, runner-up, top-four finisher, top-eight
finisher, or other confirmed participant earns 36/29/22/14/8 points at Champions
and 22/17/13/8/4 at Masters. The denominator is the sum of maximum points across
the season's international calendar. Regional placements earn 10/7/4/2 points
for the same placement bands and the best three finishes count against a
30-point maximum. Published final standings are the primary source. A unique
completed regional grand final can establish first and second place. Group
seeds are excluded from placement scoring.

Match results, execution and opponent strength use event multipliers of
Champions 3×, Masters 2×, and regional 1×. A draw is half a win. Recent form
uses up to five matches with additional recency weights from 5 down to 1.
Season win rate and recent form are pulled toward 50% using priors of five and
three actual series respectively. Execution blends map wins (40%), round share
(40%) and kills divided by kills plus deaths (20%).

Team scores display earned points out of 100. Coverage may be partial during the backfill, and
missing finishes receive only verified participation credit where applicable.

## Global player ranking

Players qualify with five actual maps in the selected season. The score uses
weighted rating (35%), ACS (25%), KAST (20%), ADR (10%), and kills divided by
kills plus deaths (10%). The first four rates are capped at 1.0 against
reference values of 1.2 rating, 300 ACS, 100 KAST, and 150 ADR. The score is
pulled toward the season's map-weighted player average with a ten-map prior.

Regional maps count 1×, Masters maps 1.75×, and Champions maps 2.5×. Recognized
bracket matches count 1.25×, 2.25×, and 3× respectively. The stage bonus uses
recognizable VLR match URL suffixes. Other matches use the event's base weight.
International map count and raw average international rating are reported
separately. The sample-adjusted player score is displayed out of 100.

## 2027 schedule and roster policy

The live VLR tier-one listing currently includes multiple 2027-season events,
including Kickoff qualifiers, [Masters Seoul](https://www.vlr.gg/event/3161/valorant-masters-seoul-2027),
[Masters Valencia](https://www.vlr.gg/event/3162/valorant-masters-valencia-2027),
and [Valorant Champions 2027](https://www.vlr.gg/event/3163/valorant-champions-2027).
The [EMEA Kickoff – Europe Qualifier](https://www.vlr.gg/event/3175/vct-2027-emea-kickoff-europe-qualifier)
page gives dates of November 5–December 6, 2026 and currently reports zero
matches. The season label and calendar dates are stored separately: a 2027
event can occur in 2026. The refresh records listed events, but it does not
invent fixtures or rosters; only source-backed future matches and dated roster
tenures are shown. Add roster records only when a reliable source provides them.

## Next implementation milestones

1. Add scraper HTML fixtures and broader importer/API tests using a disposable
   PostgreSQL database.
2. Add a reviewed VLR parser fixture set and import reconciliation counts.
3. Add a curated source-backed workflow for confirmed roster announcements and
   event dates.
4. Verify the power score against source match/map records and tune its
   transparent component weights only with a documented reason.
5. Extend player cards only after profile identity and recent-stat coverage
   are trustworthy; keep card attributes traceable to real stats.

## Data quality checklist

- Match date is UTC and comes from the source.
- A scheduled match without a result is never included in the power index.
- Player map stats are not accidentally described as match-level stats.
- Team/player aliases point to stable identities; avoid merging same-name
  players without supporting evidence.
- Observed match participation and verified roster membership remain separate.
- Every manual roster/date claim keeps a source URL, status, and notes.
- A new import updates existing VLR IDs without losing the source snapshot.
