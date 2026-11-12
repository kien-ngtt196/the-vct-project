"""Refresh 2021 match-stage labels from VLR's tournament listings."""

import re

from bs4 import BeautifulSoup
from psycopg2.extras import execute_values

from src.db.database import connect
from src.db.initialize import initialize_database
from src.scraper.main import BASE_URL, safe_get


def match_series(html):
    for card in BeautifulSoup(html, "html.parser").select("a.match-item"):
        match_id = re.match(r"/(\d+)/", card.get("href", ""))
        event = card.select_one(".match-item-event")
        if not match_id or not event:
            continue
        round_name = event.select_one(".match-item-event-series")
        if round_name:
            round_name.decompose()
        yield match_id[1], event.get_text(" ", strip=True) or None


def main():
    initialize_database()
    connection = connect()
    try:
        with connection, connection.cursor() as cursor:
            cursor.execute("""
                SELECT tournament.id
                FROM tournaments tournament JOIN seasons season USING (season_id)
                WHERE tournament.tier = 'tier1' AND season.year = 2021
                ORDER BY tournament.id
                """)
            events = cursor.fetchall()
        failed = []
        for (event_id,) in events:
            response = safe_get(f"{BASE_URL}/event/matches/{event_id}/")
            labels = dict(match_series(response.text)) if response is not None else {}
            if not labels:
                failed.append(event_id)
                continue
            with connection, connection.cursor() as cursor:
                execute_values(cursor, """
                    UPDATE matches AS match
                    SET series_name = labels.series_name
                    FROM (VALUES %s) AS labels(id, series_name)
                    WHERE match.id = labels.id
                      AND match.series_name IS DISTINCT FROM labels.series_name
                    """, list(labels.items()))
            print(f"{event_id}: {len(labels)} match listings", flush=True)
        if failed:
            raise SystemExit(f"VLR listings unavailable for events: {', '.join(failed)}")
    finally:
        connection.close()


if __name__ == "__main__":
    main()
