"""Fill missing match IDs from a reviewed VLR tournament coverage file."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from src.db.database import connect
from src.db.import_vlr import import_snapshot, is_tier_one_event
from src.scraper.main import get_match_links, parse_match, parse_vlr_date, write_snapshot


def reconcile(coverage_path):
    coverage = json.loads(coverage_path.read_text(encoding="utf-8"))
    since = datetime(2022, 4, 10, tzinfo=timezone.utc)
    until = datetime.now(timezone.utc)
    stamp = until.strftime("%Y%m%dT%H%M%SZ")
    unresolved = {}
    connection = connect()
    try:
        for entry in coverage:
            event_id = entry["id"]
            with connection, connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT title, url, status FROM tournaments
                    WHERE id = %s AND tier = 'tier1'
                    """,
                    (event_id,),
                )
                tournament = cursor.fetchone()
                if not tournament or not is_tier_one_event(tournament[0]):
                    continue
                cursor.execute(
                    "SELECT id FROM matches WHERE tournament_id = %s",
                    (event_id,),
                )
                missing = set(entry["match_ids"]) - {row[0] for row in cursor}

            if entry["listing_requires_review"]:
                unresolved[event_id] = ["listing unavailable"]
                continue
            if not missing:
                continue
            matches = []
            for link in get_match_links(entry["listing"]):
                match_id = link.split("/")[3]
                if match_id not in missing:
                    continue
                match = parse_match(link)
                if match is None:
                    continue
                match_date = parse_vlr_date(match.get("date"))
                if match_date is None and entry["starts_before_cutoff"]:
                    continue
                missing.remove(match_id)
                if match_date is None or since <= match_date <= until:
                    matches.append(match)

            if matches:
                title, url, status = tournament
                snapshot = write_snapshot(
                    [{
                        "id": event_id,
                        "title": title,
                        "url": url,
                        "status": status,
                        "season": entry["year"],
                        "matches": matches,
                    }],
                    f"events_{stamp}_reconciled_{event_id}.json",
                )
                import_snapshot(snapshot)
            if missing:
                unresolved[event_id] = sorted(missing)
            print(f"{entry['year']} {event_id}: {len(matches)} imported, {len(missing)} unresolved")
    finally:
        connection.close()
    if unresolved:
        raise SystemExit(f"VLR coverage still needs review: {unresolved}")
    print(f"Reconciled listed match IDs across {len(coverage)} tournament records.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("coverage", type=Path)
    reconcile(parser.parse_args().coverage)
