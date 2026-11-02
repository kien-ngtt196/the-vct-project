# VCT Scout

A local-first VCT tier-one data explorer. It collects VLR.gg event, match, map,
player-stat, and profile-image references; imports them into PostgreSQL; and
serves a small search and 2026 team power-ranking web app.

## Get started

1. Install Python 3.9+ and PostgreSQL. From the repository root, install the
   dependencies with `python -m pip install -r requirements.txt`.
2. Create a local database (for example, `createdb vct_db -U postgres`), copy
   `.env.example` to `.env`, and set the local PostgreSQL connection values
   there. `.env` is ignored by Git and loaded automatically. Never commit or
   share its real password.
3. Initialize the versioned schema: `python -m src.db.initialize`.
4. Scrape VLR.gg's tier-one event listing. By default the scraper starts at
   January 1 of the current UTC year:

   ```powershell
   python -m src.scraper.main
   ```

   Scrapes are written as timestamped snapshots under `data/raw/`. Set
   `--since YYYY-MM-DD` to a later UTC date for a smaller refresh.
5. Import the newest snapshot: `python -m src.db.import_vlr`.
6. Start the UI: `python -m src.web.app`, then open
   `http://127.0.0.1:8000`.

The legacy import entry point `python -m src.scraper.migrate_json_to_pg` remains
available and forwards to the versioned importer.

## What is included

- Player/team search, VLR profile links and images, recent map stats, clickable
  team/player profiles, team event participation, sourced roster listings, and
  team match history.
- A transparent 2026 global team ranking combining season results (35%), recent
  form (25%), in-game execution (25%), and opponent strength (15%). It describes
  season performance; it weights Champions 3×, Masters 2×, and regional
  matches 1×, then scales the current leader to 100. The player ranking uses
  weighted 2026 rating, ACS, KAST, ADR, and K/D, requires at least five maps,
  and also scales its leader to 100. Neither ranking predicts match outcomes.
- Explicitly sourced roster-tenure records and separately stored observed
  match participation, so an appearance is never mislabeled as a current
  roster. The profile refresh reads current roster listings from VLR team
  pages and labels event-page roster evidence separately.
- A 2027 watchlist that shows only events and fixtures actually present in the
  imported data. Unknown events, rosters, and fixtures are not invented.

See [workflow.md](./workflow.md) for the architecture, data model, refresh,
profile/image refresh, validation, team and player power formulas, roster
handling, and future-feature workflow.
