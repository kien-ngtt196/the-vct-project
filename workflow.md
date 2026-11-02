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
          leaderboard and comparison
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

## 2026 global team ranking

The app does not generate match probabilities or tournament forecasts. The
global ranking is a descriptive 0–100 summary of completed 2026 tier-one
results only:

1. Season match results contribute 35%; each match has an event multiplier and
   a draw counts as half a win. Champions matches count 3×, Masters 2×, and
   regional events 1×. The event type is inferred from the tournament title:
   titles containing `Champions` or `Masters` get those weights; other tier-one
   events use the regional weight.
2. Recent form contributes 25%, using the last five completed matches with
   recency weights from 5 (most recent) down to 1 (oldest), multiplied by the
   event-importance weight.
3. In-game execution contributes 25%: 40% event-weighted map win rate, 40%
   event-weighted normalized round strength, and 20% event-weighted normalized
   K/D strength (`kills / (kills + deaths)`).
4. Opponent strength contributes 15%, using the event-weighted average 2026
   match win rate of opponents.
5. Each component is normalized from 0 to 1. The final score is
   `100 * (0.35 * season_results + 0.25 * recent_form + 0.25 * execution + 0.15 * opponent_strength)`.
   Missing component data uses a neutral 0.5 rather than a guessed value.

After computing this component score, each team's displayed score is divided
by the highest score in the current ranking and multiplied by 100. Therefore
the current leader is always 100; values are relative to the 2026 teams present
in the database, not fixed ratings across refreshes.

The leaderboard exposes component rates and match record beside each score.
Regional-strength and event-stage factors beyond the tournament-tier
multipliers are not included because the current source data does not provide
reliable team-region and stage labels. Gold metrics are not applicable to
Valorant. Opponent strength is only a basic average win-rate adjustment. The
ranking is not a forecast, does not account for roster changes, and is not an
official rating. All player and team performance views are scoped to
calendar-year 2026; the 2027 watchlist is only sourced event metadata and is
not included in the power calculation.

## 2026 global player ranking

Players with at least five completed 2026 tier-one maps are ranked using their
event-weighted per-map averages. Rating contributes 35% (normalized against
1.2), ACS 25% (against 300), KAST 20% (against 100), ADR 10% (against 150),
and `kills / (kills + deaths)` 10%. The first four component rates are capped
at 1.0; the resulting score is then normalized so the highest-ranked player
is 100. Champion and Masters maps use the same event weights as the team
ranking. This is a relative season-performance summary, not an official player
rating or a prediction.

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
