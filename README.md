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

For a historical refresh, run `python -m src.scraper.main --backfill`.
It uses the VLR Tier 1 event listing, starts with Masters Reykjavík 2022,
and writes and imports a snapshot after each event. The full run can take
substantial time because requests are throttled. Start the web app separately
and use the season picker on a team profile to inspect imports as they land.
After the match import, run
`python -m src.db.sync_vlr_profiles --historical-events` to refresh event
placements, roster evidence, and VLR profile images.

To fill the 2021 and 2022 seasons, run:

```powershell
python -m src.scraper.main --backfill --since 2021-01-01 --through-year 2022
python -m src.db.sync_vlr_profiles --historical-events --through-year 2022 --placements-only
```

The bounded backfill skips matches that already have player-map stats. It
imports each event as it finishes, so it can be resumed with the same command.


## Vercel deployment

Import the repository root as a FastAPI project. The root `app.py` serves the
same routes as the local Python server. The function runs in Singapore to
match the project's hosted PostgreSQL region.

Set `DATABASE_URL` in Vercel to the pooled PostgreSQL connection string for
the deployment environment, then redeploy. Preview deployments can use a
separate database branch. Restore or migrate the hosted database separately
and check `/api/health`, the tournament archive, and both ranking pages.

The deployment includes checked-in artwork. If an image cached on a developer's
machine is absent, the frontend tries its source URL. Locally sourced portraits
without a usable source URL need separate hosting to appear online.

## What is included

- Player/team search, VLR profile links and images, recent map stats, clickable
  team/player profiles, team event participation, sourced roster listings, and
  team match history.
- A global team ranking with a season selector for 2021–2026, combining
  international achievement (40%), regional achievement (15%), season
  results (20%), recent form (10%), in-game execution (10%), and opponent
  strength (5%). It describes
  season performance; it weights Champions 3×, Masters 2×, and regional
  matches 1×, and displays earned points out of 100. The player ranking uses
  weighted rating, ACS, KAST, ADR, and K/D, requires at least five maps,
  and displays the sample-adjusted score out of 100. Both rankings use completed Tier 1 matches
  in the selected season. Team region labels are inferred from the most frequent
  regional Tier 1 tournament region in VLR data for that season. Neither
  ranking predicts match outcomes.
- Explicitly sourced roster-tenure records and separately stored observed
  match participation, so an appearance is never mislabeled as a current
  roster. The profile refresh reads current roster listings from VLR team
  pages and labels event-page roster evidence separately.
- A four-region 2027 roadmap for Open Qualifiers, regional Cups, Masters, and
  Champions. Event listings and dates appear only when present in imported VLR
  data; unannounced stages are clearly marked. VLR regional event logos are
  saved locally in `vct_images/`.

See [workflow.md](./workflow.md) for the architecture, data model, refresh,
profile/image refresh, validation, team and player power formulas, roster
handling, and future-feature workflow.
