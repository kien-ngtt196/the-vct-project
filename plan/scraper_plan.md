# VLR.gg VCT Tier 1 Scraper Plan

## Goal

Build a Python scraper that collects only 2026 Valorant Champions Tour (VCT) Tier 1 tournaments from VLR.gg and the details of every match in each tournament.

The source event page is:

```text
https://www.vlr.gg/events/?region=all&tier=60
```

The `region=all` filter covers the four VCT regions:

- Americas
- EMEA
- Pacific
- China

The `tier=60` filter identifies the VCT Tier 1 event category. The scraper must still verify the event year and keep only 2026 tournaments.

## Crawl Flow

```text
VLR Tier 1 events page
        |
        v
2026 tournament links
        |
        v
Each tournament page
        |
        v
Match links for that tournament
        |
        v
Each match detail page
        |
        v
Normalized match records and database upserts
```

## Phase 1: Discover 2026 Events

1. Request the Tier 1 events URL with `requests`.
2. Use a descriptive User-Agent and a timeout.
3. Parse the response with BeautifulSoup.
4. Find every tournament link on the events page.
5. Extract each event's VLR source ID, name, URL, region, and dates.
6. Keep only events whose start year is 2026.
7. Store the event metadata before processing its matches.

Use stable VLR IDs from URLs as `source_id` values. For example, an event URL shaped like `/event/<id>/<slug>` should use `<id>` as the event identifier.

The event-year rule should be explicit and configurable:

```python
event.start_date.year == 2026
```

For the first version, use the tournament start year. Later, this can be changed to include tournaments with any matches played during 2026.

## Phase 2: Discover Tournament Matches

For each qualifying tournament page:

1. Request the tournament URL.
2. Parse tournament metadata.
3. Find all match links in the tournament page HTML.
4. Extract each match ID and URL.
5. Associate every match with its tournament source ID.
6. Remove duplicate match URLs before fetching detail pages.

Do not construct match URLs manually. Discover them from each tournament page.

## Phase 3: Parse Match Details

Request every discovered match page and extract:

- VLR match source ID
- Tournament source ID
- Match URL
- Scheduled date and time
- Match status
- Event stage
- Round or week
- Series format, such as BO3 or BO5
- Team 1 name and source ID
- Team 2 name and source ID
- Team scores
- Winner
- Maps played
- Per-map scores
- Match start and end times when available

Handle these states explicitly:

- `scheduled`
- `live`
- `completed`
- `postponed`
- `cancelled`
- `TBD`

Scheduled matches may not have scores. Live scores can change between requests. Completed matches should contain final scores.

A normalized match record can look like:

```python
{
    "source_id": "match-id",
    "tournament_source_id": "event-id",
    "team1_source_id": "team-id-1",
    "team2_source_id": "team-id-2",
    "status": "completed",
    "team1_score": 2,
    "team2_score": 1,
    "scheduled_at": "2026-06-15T18:00:00+00:00",
    "stage": "Regular Season",
    "round": "Week 3",
    "series_format": "bo3",
    "maps": [
        {"name": "Ascent", "team1_score": 13, "team2_score": 9}
    ],
    "url": "https://www.vlr.gg/..."
}
```

## Core Data Model

The first milestone should store:

### Tournaments

- Internal database ID
- VLR source ID, unique
- Name
- Region
- Start date
- End date
- Tier
- Year
- URL
- Last updated time

### Teams

- Internal database ID
- VLR source ID, unique
- Name
- URL
- Last updated time

### Matches

- Internal database ID
- VLR source ID, unique
- Tournament relationship
- Team 1 relationship
- Team 2 relationship
- Status
- Scores
- Map results
- Scheduled/start/end timestamps
- Stage and round
- URL
- Content hash
- Last updated time

### Changelog

Record an entry only when normalized data changes:

- Entity type
- Entity source ID or database ID
- Previous state or content hash
- New state or content hash
- Changed time

Player, roster, and team-page scraping can be added after tournament and match ingestion is reliable. Player/map statistics are explicitly deferred from this milestone.

## Project Structure

```text
src/
  main.py                 # command-line entry point
  scraper/
    __init__.py
    client.py             # HTTP requests, retries, delays
    config.py             # year, URL, intervals, environment settings
    parser.py             # BeautifulSoup event and match parsers
    models.py             # typed normalized records
    database.py            # SQLAlchemy/PostgreSQL persistence
    events.py              # event discovery and filtering
    matches.py             # tournament match discovery and parsing
    poller.py              # one-shot and continuous polling

tests/
  test_parser.py
  fixtures/
    events_tier1.html
    tournament.html
    match.html

requirements.txt
README.md
plan.md
```

The repository's broader roadmap points toward PostgreSQL and SQLAlchemy. Use that as the persistence target. Keep parser and crawl logic independent of the database so tests can run without a live database.

## HTTP Client Requirements

The HTTP client must:

- Use `requests` or `httpx`.
- Set a descriptive User-Agent.
- Set an explicit timeout.
- Rate-limit requests to VLR.gg.
- Add a small delay between requests.
- Retry temporary `429` and `5xx` responses with bounded backoff.
- Log failed requests and parser failures.
- Check and respect `robots.txt` and VLR.gg terms of service.
- Avoid unsupported or private endpoints.

Example starting point:

```python
import requests

headers = {
    "User-Agent": "VCTProjectScraper/1.0 contact@example.com"
}

response = requests.get(
    "https://www.vlr.gg/events/?region=all&tier=60",
    headers=headers,
    timeout=30,
)
response.raise_for_status()
```

## Implementation Order

1. Correct the BeautifulSoup import in `src/scraper/main.py`:

   ```python
   from bs4 import BeautifulSoup
   ```

2. Request the Tier 1 events URL.
3. Print the response status code.
4. Parse and print all discovered event names and URLs.
5. Filter and print only 2026 events.
6. Save one downloaded events page as a test fixture.
7. Fetch one 2026 tournament page.
8. Print all match URLs found on that tournament page.
9. Fetch one match page.
10. Print its normalized match details.
11. Add parser functions and unit tests.
12. Add SQLAlchemy models and PostgreSQL persistence.
13. Implement idempotent upserts using VLR source IDs.
14. Add content-hash change detection and changelog records.
15. Expand from one tournament to all qualifying 2026 events.
16. Add one-shot polling.
17. Add continuous polling only after one-shot polling is reliable.

Start with one event before crawling everything. This makes selector and parser problems easy to isolate.

## Polling Strategy

Use separate polling frequencies:

- Event discovery: every 10 to 60 minutes
- Live matches: every 15 to 30 seconds while live
- Scheduled or recently completed matches: every 5 to 15 minutes
- Team and roster metadata: every 1 to 3 hours

Keep each polling cycle as a callable function. The scheduler should be separate so tests can execute one cycle without starting an endless process.

## Idempotency and Change Detection

Use VLR source IDs as unique keys:

```text
new source_id       -> insert
existing source_id  -> update
```

Before updating an entity:

1. Normalize the parsed data.
2. Serialize it consistently.
3. Calculate a content hash.
4. Compare it with the stored hash.
5. Skip the update if unchanged.
6. If changed, update the record and insert one changelog entry.

Running the seed command twice must not create duplicate tournaments, teams, or matches.

## Testing Plan

Save representative HTML fixtures and test parser behavior without requiring live network access.

Test at least:

- Event ID, name, region, and dates
- 2026 filtering
- Non-2026 event exclusion
- Tournament match-link extraction
- Match IDs and URLs
- Scheduled match with no score
- Live match with changing score
- Completed match with final score
- Postponed or cancelled match
- TBD teams or missing fields
- Unknown or changed markup
- Duplicate match-link removal
- Malformed HTML handling
- Database upsert idempotency
- Content-hash change detection
- Transaction rollback

Useful commands:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
pytest
python -m src.main
```

## Expected First Milestone Output

The first working crawl should produce a summary similar to:

```text
Found 4 regions
Found 2026 Tier 1 events: N
Processing: VCT 2026: Americas ...
Found matches: N
Completed: N
Scheduled: N
Live: N
```

The exact counts depend on VLR.gg's current 2026 event listings.

## Definition of Done

The first scraper milestone is complete when:

- All qualifying official 2026 Tier 1 events are discovered from the filtered events page.
- Every match link from each qualifying tournament is discovered.
- Match detail pages are parsed into normalized records.
- Scheduled, live, completed, postponed, cancelled, and TBD cases do not crash the scraper.
- Data is stored in PostgreSQL through SQLAlchemy.
- Re-running the seed creates no duplicate records.
- A changed match creates an appropriate changelog record.
- Parser tests pass using saved fixtures.
- Requests are rate-limited and compliant with robots.txt and terms of service.
- The scraper supports a bounded one-shot run before continuous polling.
