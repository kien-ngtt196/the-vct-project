"""Look for missing portraits and logos in 2021–2026 VLR profiles."""

import json
import logging
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

from src.db.database import connect
from src.db.import_vlr import RAW_DIR, is_placeholder_media
from src.db.sync_vlr_profiles import (
    PLAYER_PROFILE, STATIC_DIR, TEAM_PROFILE, _image_url, _profile_id, _request,
)


def candidates(cursor):
    cursor.execute("""
        WITH scoped_matches AS (
            SELECT match.id, match.team1_id, match.team2_id, season.year
            FROM matches match
            JOIN tournaments tournament ON tournament.id = match.tournament_id
            JOIN seasons season ON season.season_id = tournament.season_id
            WHERE tournament.tier = 'tier1' AND season.year BETWEEN 2021 AND 2026
        ),
        player_activity AS (
            SELECT appearance.player_id, MAX(match.year) AS year, COUNT(*) AS appearances
            FROM match_players appearance JOIN scoped_matches match ON match.id = appearance.match_id
            GROUP BY appearance.player_id
        ),
        team_activity AS (
            SELECT side.team_id, MAX(match.year) AS year, COUNT(*) AS appearances
            FROM scoped_matches match
            CROSS JOIN LATERAL (VALUES (match.team1_id), (match.team2_id)) AS side(team_id)
            GROUP BY side.team_id
        )
        SELECT 'player' AS kind, player_id AS id, canonical_name, source_url,
               image_url AS media_url, image_local_path AS local_path, year, appearances
        FROM player_activity JOIN players USING (player_id)
        UNION ALL
        SELECT 'team', team_id, canonical_name, source_url,
               logo_url, logo_local_path, year, appearances
        FROM team_activity JOIN teams USING (team_id)
        ORDER BY year DESC, kind DESC, appearances DESC, id
        """)
    return cursor.fetchall()


def has_local_image(path):
    if not path or not path.startswith("/assets/"):
        return False
    root = STATIC_DIR / "assets"
    file = (STATIC_DIR / path.lstrip("/")).resolve()
    return file.is_relative_to(root.resolve()) and file.is_file() and file.stat().st_size > 0


def main():
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    checkpoint = RAW_DIR / "missing-media-vlr-checkpoint.jsonl"
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    seen = set()
    if checkpoint.exists():
        with checkpoint.open(encoding="utf-8") as saved:
            for line in saved:
                try:
                    seen.add(tuple(json.loads(line)))
                except (ValueError, TypeError):
                    continue

    settings = {
        "player": ("players", "player_id", "image_url", "image_local_path",
                   ".wf-avatar.mod-player img", PLAYER_PROFILE),
        "team": ("teams", "team_id", "logo_url", "logo_local_path",
                 ".team-header-logo img", TEAM_PROFILE),
    }
    db = connect()
    try:
        with db, db.cursor() as cursor:
            rows = [
                row for row in candidates(cursor)
                if is_placeholder_media(row[4]) and not has_local_image(row[5])
                and row[3] and _profile_id(row[3], settings[row[0]][5])
                and (row[0], row[1], row[3]) not in seen
            ]
        print(f"{len(rows)} missing images to check", flush=True)
        updated = 0
        with checkpoint.open("a", encoding="utf-8") as saved:
            for index, (kind, entity_id, name, profile, _, local_path, year, _) in enumerate(rows, 1):
                table, id_col, media_col, local_col, selector, pattern = settings[kind]
                response = _request(profile)
                if response is not None and (
                    urlsplit(response.url).hostname in {"vlr.gg", "www.vlr.gg"}
                    and _profile_id(response.url, pattern) == _profile_id(profile, pattern)
                ):
                    img = BeautifulSoup(response.text, "html.parser").select_one(selector)
                    asset = _image_url(img.get("src")) if img else None
                    if not is_placeholder_media(asset):
                        with db, db.cursor() as cursor:
                            cursor.execute(f"""
                                UPDATE {table} SET {media_col} = %s
                                WHERE {id_col} = %s AND source_url = %s
                                  AND {local_col} IS NOT DISTINCT FROM %s
                                  AND ({media_col} IS NULL OR {media_col} = ''
                                       OR {media_col} ~* '/(sil|vlr)[.]png([?#]|$)')
                                """, (asset, entity_id, profile, local_path))
                            if cursor.rowcount:
                                updated += 1
                                print(f"Updated {year} {kind} {name}: {asset}", flush=True)
                    saved.write(json.dumps([kind, entity_id, profile]) + "\n")
                    saved.flush()
                if index % 25 == 0 or index == len(rows):
                    print(f"{index}/{len(rows)} profiles checked · {updated} updated · {year}", flush=True)
        print(f"Finished VLR profile scan: {updated} new images", flush=True)
    finally:
        db.close()


if __name__ == "__main__":
    main()
