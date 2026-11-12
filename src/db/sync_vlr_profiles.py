import argparse
import logging
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup
from curl_cffi import requests
from curl_cffi.requests.exceptions import RequestException

from src.analytics.power import placement_rank
from src.db.database import connect
from src.db.import_vlr import (
    canonical_team_name, get_or_create_player, is_placeholder_media, normalize_name,
)
from src.db.initialize import initialize_database


ROOT = Path(__file__).resolve().parents[2]
STATIC_DIR = ROOT / "src" / "web" / "static"
BASE_URL = "https://www.vlr.gg"
PAGE_INTERVAL_SECONDS = 1.0
IMAGE_INTERVAL_SECONDS = 0.2
MAX_IMAGE_BYTES = 10 * 1024 * 1024
PLAYER_PROFILE = re.compile(r"^/player/(\d+)/([^/]+)/?$")
TEAM_PROFILE = re.compile(r"^/team/(\d+)/([^/]+)/?$")
LOG = logging.getLogger("vct.profile_sync")

session = requests.Session(impersonate="chrome120")
last_page_request = 0.0
last_image_request = 0.0


def _request(url, image=False):
    global last_page_request, last_image_request
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in {
        "vlr.gg",
        "www.vlr.gg",
        "owcdn.net",
    }:
        LOG.warning("Skipping URL outside VLR image hosts: %s", url)
        return None

    last_request = last_image_request if image else last_page_request
    interval = IMAGE_INTERVAL_SECONDS if image else PAGE_INTERVAL_SECONDS
    elapsed = time.monotonic() - last_request
    if elapsed < interval:
        time.sleep(interval - elapsed)

    for attempt in range(3):
        try:
            response = session.get(url, timeout=30)
        except RequestException as error:
            if attempt == 2:
                LOG.warning("VLR request failed for %s: %s", url, error)
                return None
            time.sleep(2**attempt)
            continue

        if image:
            last_image_request = time.monotonic()
        else:
            last_page_request = time.monotonic()

        if response.status_code == 200:
            return response
        if response.status_code != 429 and response.status_code < 500:
            LOG.warning("VLR returned HTTP %s for %s", response.status_code, url)
            return None
        if attempt == 2:
            LOG.warning("VLR returned HTTP %s for %s after retries", response.status_code, url)
            return None
        time.sleep(2**attempt)
    return None


def _image_url(value):
    if not value:
        return None
    url = urljoin(BASE_URL, value)
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in {
        "vlr.gg",
        "www.vlr.gg",
        "owcdn.net",
    }:
        return None
    return url


def _is_placeholder_image(url):
    return is_placeholder_media(url)


def _profile_id(url, pattern):
    match = pattern.fullmatch(urlsplit(url).path)
    return match.group(1) if match else None


def _source_team_id(slug, aliases):
    normalized = normalize_name(slug.replace("-", " "))
    return aliases.get(canonical_team_name(normalized)) or aliases.get(normalized)


def _player_tag(url):
    match = PLAYER_PROFILE.fullmatch(urlsplit(url).path)
    return match.group(2).replace("-", " ") if match else None


def _team_lookup(cursor):
    cursor.execute("SELECT team_id, canonical_name, source_url FROM teams")
    teams = cursor.fetchall()
    aliases = {}
    source_urls = {}
    for team_id, canonical_name, source_url in teams:
        aliases[canonical_team_name(canonical_name)] = team_id
        aliases[normalize_name(canonical_name)] = team_id
        if source_url:
            source_urls[source_url.rstrip("/")] = team_id

    cursor.execute("SELECT team_id, alias_name FROM team_aliases")
    for team_id, alias_name in cursor.fetchall():
        normalized = normalize_name(alias_name)
        aliases[normalized] = team_id
        aliases[canonical_team_name(normalized)] = team_id
    return aliases, source_urls


def _current_2026_data(cursor):
    cursor.execute(
        """
        SELECT DISTINCT team.team_id, team.canonical_name, team.source_url
        FROM teams team
        JOIN matches match
          ON match.team1_id = team.team_id OR match.team2_id = team.team_id
        JOIN tournaments tournament ON tournament.id = match.tournament_id
        LEFT JOIN seasons event_season ON event_season.season_id = tournament.season_id
        WHERE tournament.tier = 'tier1'
          AND match.match_date >= DATE '2026-01-01'
          AND match.match_date < DATE '2027-01-01'
          AND COALESCE(
              event_season.year,
              EXTRACT(YEAR FROM match.match_date)::INTEGER
          ) = 2026
        ORDER BY team.canonical_name
        """
    )
    teams = cursor.fetchall()
    cursor.execute(
        """
        SELECT DISTINCT tournament.id, tournament.title, tournament.url
        FROM tournaments tournament
        JOIN matches match ON match.tournament_id = tournament.id
        LEFT JOIN seasons event_season ON event_season.season_id = tournament.season_id
        WHERE tournament.tier = 'tier1'
          AND match.match_date >= DATE '2026-01-01'
          AND match.match_date < DATE '2027-01-01'
          AND COALESCE(
              event_season.year,
              EXTRACT(YEAR FROM match.match_date)::INTEGER
          ) = 2026
        ORDER BY tournament.title
        """
    )
    return teams, cursor.fetchall()


def _save_event_results(cursor, event, aliases, source_urls, *, placements_only=False):
    tournament_id, title, event_url = event
    response = _request(event_url)
    if response is None:
        return {}, False

    soup = BeautifulSoup(response.text, "html.parser")
    team_profiles = {}
    player_profiles = set()

    for link in soup.select("a[href^='/team/']"):
        profile_url = urljoin(BASE_URL, link.get("href", ""))
        team_profile_id = _profile_id(profile_url, TEAM_PROFILE)
        if not team_profile_id:
            continue
        team_id = source_urls.get(profile_url.rstrip("/"))
        match = TEAM_PROFILE.fullmatch(urlsplit(profile_url).path)
        if team_id is None and match:
            team_id = _source_team_id(match.group(2), aliases)
        if team_id is None:
            LOG.warning("No 2026 database team matches VLR profile %s", profile_url)
            continue

        image = link.select_one("img") or link.parent.select_one("img")
        image_url = _image_url(image.get("src") if image else None)
        if _is_placeholder_image(image_url):
            image_url = None
        team_profiles[team_profile_id] = (team_id, profile_url, image_url)

    for row in soup.select(".wf-ptable--standings .row"):
        cells = row.select(":scope > .cell")
        if len(cells) < 3:
            continue
        placement = cells[0].get_text(strip=True)
        link = row.select_one(".mod-team a[href^='/team/']")
        if placement_rank(placement) is None or link is None:
            continue
        profile_id = _profile_id(urljoin(BASE_URL, link["href"]), TEAM_PROFILE)
        team_data = team_profiles.get(profile_id)
        if team_data is None:
            continue
        cursor.execute(
            """
            INSERT INTO team_event_results (
                tournament_id, team_id, placement_text, prize, source_url
            )
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (tournament_id, team_id) DO UPDATE SET
                placement_text = EXCLUDED.placement_text,
                prize = EXCLUDED.prize,
                source_url = EXCLUDED.source_url,
                updated_at = now()
            """,
            (tournament_id, team_data[0], placement, cells[1].get_text(strip=True), event_url),
        )

    if placements_only:
        return team_profiles, True

    for card in soup.select(".event-team"):
        link = card.select_one("a[href^='/team/']")
        if link is None:
            continue
        profile_url = urljoin(BASE_URL, link["href"])
        team_data = team_profiles.get(_profile_id(profile_url, TEAM_PROFILE))
        if team_data is None:
            continue
        team_id, _, _ = team_data
        for player_link in card.select("a[href^='/player/']"):
            player_url = urljoin(BASE_URL, player_link.get("href", ""))
            tag = _player_tag(player_url)
            if tag:
                player_profiles.add((team_id, tag, player_url))

    meta = soup.select_one(".event-header-main-meta")
    if meta:
        meta_text = meta.get_text(" ", strip=True)
        prize_match = re.search(
            r"\bPrize\s+(.+?)(?:\s+Location\b|\s+Organizer\b|$)",
            meta_text,
            re.IGNORECASE,
        )
        if prize_match:
            cursor.execute(
                "UPDATE tournaments SET prize_pool = %s WHERE id = %s",
                (prize_match.group(1).strip(), tournament_id),
            )

    for team_id, profile_url, image_url in team_profiles.values():
        cursor.execute(
            """
            UPDATE teams
            SET source_url = %s,
                logo_url = COALESCE(%s, logo_url)
            WHERE team_id = %s
            """,
            (profile_url, image_url, team_id),
        )

    for team_id, tag, player_url in player_profiles:
        player_id = _get_or_create_player(cursor, tag, player_url, None)
        cursor.execute(
            """
            INSERT INTO roster_memberships (
                player_id, team_id, status, source, source_url, notes
            )
            VALUES (%s, %s, 'unverified', 'vlr-event-page', %s, %s)
            ON CONFLICT (player_id, team_id, source_url)
                WHERE source = 'vlr-event-page'
            DO UPDATE SET
                notes = EXCLUDED.notes,
                updated_at = now()
            """,
            (
                player_id,
                team_id,
                event_url,
                f"Listed on {title}; this event roster is not a current-roster claim.",
            ),
        )
        cursor.execute(
            "UPDATE players SET source_url = %s WHERE player_id = %s",
            (player_url, player_id),
        )

    return team_profiles, True


def _get_or_create_player(cursor, tag, profile_url, image_url):
    canonical_tag = normalize_name(tag)
    cursor.execute(
        """
        SELECT player.player_id
        FROM players player
        WHERE player.source_url = %s
           OR player.canonical_name = %s
           OR EXISTS (
               SELECT 1 FROM player_aliases alias
               WHERE alias.player_id = player.player_id
                 AND lower(alias.alias_name) = lower(%s)
           )
        ORDER BY (player.source_url = %s) DESC
        LIMIT 1
        """,
        (profile_url, canonical_tag, tag, profile_url),
    )
    row = cursor.fetchone()
    if row:
        player_id = row[0]
        cursor.execute(
            """
            UPDATE players
            SET source_url = %s,
                image_url = CASE
                    WHEN %s IS NOT NULL THEN %s
                    ELSE image_url
                END
            WHERE player_id = %s
            """,
            (
                profile_url,
                image_url if not _is_placeholder_image(image_url) else None,
                image_url,
                player_id,
            ),
        )
        cursor.execute(
            """
            INSERT INTO player_aliases (player_id, alias_name)
            VALUES (%s, %s)
            ON CONFLICT (player_id, alias_name) DO NOTHING
            """,
            (player_id, tag),
        )
        return player_id

    player_id = get_or_create_player(
        cursor,
        {
            "name": tag,
            "profile_url": profile_url,
            "image_url": image_url if not _is_placeholder_image(image_url) else None,
        },
    )
    return player_id


def _extract_roster(soup):
    entries = []
    for item in soup.select(".team-roster-item"):
        link = item.select_one("a[href^='/player/']")
        if link is None:
            continue
        profile_url = urljoin(BASE_URL, link.get("href", ""))
        tag = _player_tag(profile_url)
        if not tag:
            continue
        image = item.select_one("img")
        image_url = _image_url(image.get("src") if image else None)
        role_text = item.get_text(" ", strip=True)
        role_match = re.search(
            r"\b(head coach|assistant coach|performance coach|coach|manager|analyst|substitute|reserve|loan)\b",
            role_text,
            re.IGNORECASE,
        )
        role = role_match.group(1).title() if role_match else "Player"
        entries.append((tag, profile_url, image_url, role))
    return entries


def _scrape_team_profiles(cursor, teams, team_profiles):
    profiles = {
        team_id: profile_url
        for team_id, profile_url, _ in team_profiles.values()
    }
    for team_id, _, source_url in teams:
        if source_url and source_url.startswith("https://www.vlr.gg/team/"):
            profiles.setdefault(team_id, source_url)

    scraped = 0
    roster_count = 0
    player_profile_urls = set()
    for team_id, profile_url in profiles.items():
        response = _request(profile_url)
        if response is None:
            continue
        soup = BeautifulSoup(response.text, "html.parser")
        logo = soup.select_one(".team-header-logo img")
        logo_url = _image_url(logo.get("src") if logo else None)
        roster = _extract_roster(soup)
        if not _is_placeholder_image(logo_url):
            cursor.execute(
                """
                UPDATE teams
                SET source_url = %s, logo_url = %s
                WHERE team_id = %s
                """,
                (profile_url, logo_url, team_id),
            )
        else:
            cursor.execute(
                "UPDATE teams SET source_url = %s WHERE team_id = %s",
                (profile_url, team_id),
            )

        if roster:
            cursor.execute(
                """
                UPDATE roster_memberships
                SET status = 'unverified',
                    notes = 'No longer listed on the latest VLR team profile.',
                    updated_at = now()
                WHERE team_id = %s
                  AND source = 'vlr-team-page'
                  AND status = 'current'
                """,
                (team_id,),
            )

        for tag, player_url, image_url, role in roster:
            player_id = _get_or_create_player(cursor, tag, player_url, image_url)
            cursor.execute(
                """
                INSERT INTO roster_memberships (
                    player_id, team_id, status, source, source_url, notes
                )
                VALUES (%s, %s, 'current', 'vlr-team-page', %s, %s)
                ON CONFLICT (player_id, team_id)
                    WHERE status = 'current' AND source = 'vlr-team-page'
                DO UPDATE SET
                    source_url = EXCLUDED.source_url,
                    notes = EXCLUDED.notes,
                    updated_at = now()
                """,
                (player_id, team_id, profile_url, role),
            )
            player_profile_urls.add(player_url)
            roster_count += 1

        scraped += 1
        LOG.info(
            "Synced VLR team profile %s (%s roster entries)",
            profile_url,
            len(roster),
        )
    return scraped, roster_count, player_profile_urls


def _refresh_missing_player_images(cursor, first_year=2026):
    cursor.execute(
        """
        SELECT DISTINCT player.player_id, player.source_url
        FROM players player
        JOIN player_stats stats ON stats.player_id = player.player_id
        JOIN games game ON game.id = stats.game_id
        JOIN matches match ON match.id = game.match_id
        JOIN tournaments tournament ON tournament.id = match.tournament_id
        LEFT JOIN seasons event_season ON event_season.season_id = tournament.season_id
        WHERE tournament.tier = 'tier1'
          AND match.match_date >= make_date(%s, 1, 1)
          AND match.match_date < DATE '2027-01-01'
          AND COALESCE(
              event_season.year,
              EXTRACT(YEAR FROM match.match_date)::INTEGER
          ) BETWEEN %s AND 2026
          AND player.source_url IS NOT NULL
          AND (
              player.image_url IS NULL
              OR player.image_url LIKE '%/sil.png'
          )
        ORDER BY player.player_id
        """,
        (first_year, first_year),
    )
    players = cursor.fetchall()
    refreshed = 0
    for player_id, profile_url in players:
        response = _request(profile_url)
        if response is None:
            continue
        soup = BeautifulSoup(response.text, "html.parser")
        image = soup.select_one(".wf-avatar.mod-player img")
        image_url = _image_url(image.get("src") if image else None)
        if _is_placeholder_image(image_url):
            continue
        cursor.execute(
            "UPDATE players SET image_url = %s WHERE player_id = %s",
            (image_url, player_id),
        )
        refreshed += 1
    return refreshed


def _download_image(url, target):
    response = _request(url, image=True)
    if response is None:
        return False
    content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
    extensions = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/webp": ".webp",
        "image/gif": ".gif",
    }
    extension = extensions.get(content_type)
    if extension is None:
        LOG.warning("Skipping unsupported image type %s from %s", content_type, url)
        return False
    if len(response.content) > MAX_IMAGE_BYTES:
        LOG.warning("Skipping oversized VLR image at %s", url)
        return False

    target = target.with_suffix(extension)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(response.content)
    return target


def _safe_asset_name(url):
    name = Path(urlsplit(url).path).name
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", name)
    return safe_name if safe_name and safe_name != "." else "image"


def _download_all_images(cursor, first_year=2026):
    cursor.execute(
        """
        SELECT team.team_id, team.logo_url, team.logo_local_path
        FROM teams team
        WHERE team.logo_url IS NOT NULL
          AND team.logo_url <> ''
          AND EXISTS (
              SELECT 1
              FROM matches match
              JOIN tournaments tournament ON tournament.id = match.tournament_id
              LEFT JOIN seasons event_season ON event_season.season_id = tournament.season_id
              WHERE tournament.tier = 'tier1'
                AND match.match_date >= make_date(%s, 1, 1)
                AND match.match_date < DATE '2027-01-01'
                AND COALESCE(
                    event_season.year,
                    EXTRACT(YEAR FROM match.match_date)::INTEGER
                ) BETWEEN %s AND 2026
                AND (match.team1_id = team.team_id OR match.team2_id = team.team_id)
          )
        """,
        (first_year, first_year),
    )
    team_images = cursor.fetchall()
    cursor.execute(
        """
        SELECT DISTINCT player.player_id, player.image_url, player.image_local_path
        FROM players player
        JOIN player_stats stats ON stats.player_id = player.player_id
        JOIN games game ON game.id = stats.game_id
        JOIN matches match ON match.id = game.match_id
        JOIN tournaments tournament ON tournament.id = match.tournament_id
        LEFT JOIN seasons event_season ON event_season.season_id = tournament.season_id
        WHERE tournament.tier = 'tier1'
          AND match.match_date >= make_date(%s, 1, 1)
          AND match.match_date < DATE '2027-01-01'
          AND COALESCE(
              event_season.year,
              EXTRACT(YEAR FROM match.match_date)::INTEGER
          ) BETWEEN %s AND 2026
          AND player.image_url IS NOT NULL
          AND player.image_url NOT LIKE '%/sil.png'
        """,
        (first_year, first_year),
    )
    player_images = cursor.fetchall()
    downloaded = 0

    for table, rows in (("teams", team_images), ("players", player_images)):
        for entity_id, image_url, _ in rows:
            if _is_placeholder_image(image_url):
                continue
            asset_path = (
                f"/assets/{table}/{entity_id}_{_safe_asset_name(image_url)}"
            )
            target = STATIC_DIR / asset_path.lstrip("/")
            if not target.is_file():
                downloaded_target = _download_image(image_url, target)
                if not downloaded_target:
                    continue
                asset_path = (
                    f"/{downloaded_target.relative_to(STATIC_DIR).as_posix()}"
                )
                downloaded += 1
            column = "logo_local_path" if table == "teams" else "image_local_path"
            cursor.execute(
                f"UPDATE {table} SET {column} = %s WHERE "
                f"{'team_id' if table == 'teams' else 'player_id'} = %s",
                (asset_path, entity_id),
            )

    return downloaded, len(team_images), len(player_images)


def sync_vlr_profiles(
    download_images=True, historical_events=False, placements_only=False, through_year=2026,
):
    initialize_database()
    first_year = 2021 if historical_events else 2026
    counts = {
        "events": 0,
        "team_profiles": 0,
        "roster_entries": 0,
        "player_images_refreshed": 0,
        "images_downloaded": 0,
    }
    connection = connect()
    try:
        connection.autocommit = True
        with connection.cursor() as cursor:
            teams, events = _current_2026_data(cursor)
            if historical_events:
                cursor.execute(
                    """
                    SELECT tournament.id, tournament.title, tournament.url
                    FROM tournaments tournament
                    JOIN seasons season ON season.season_id = tournament.season_id
                    WHERE tournament.tier = 'tier1' AND season.year BETWEEN %s AND %s
                      AND EXISTS (
                          SELECT 1 FROM matches WHERE tournament_id = tournament.id
                      )
                    ORDER BY season.year, tournament.start_date NULLS FIRST, tournament.id
                    """,
                    (first_year, through_year),
                )
                events = cursor.fetchall()
            aliases, source_urls = _team_lookup(cursor)
            all_team_profiles = {}

            for event in events:
                team_profiles, succeeded = _save_event_results(
                    cursor,
                    event,
                    aliases,
                    source_urls,
                    placements_only=placements_only,
                )
                if succeeded:
                    counts["events"] += 1
                all_team_profiles.update(team_profiles)

            if placements_only:
                return counts
            scraped, roster_entries, _ = _scrape_team_profiles(
                cursor,
                teams,
                all_team_profiles,
            )
            counts["team_profiles"] = scraped
            counts["roster_entries"] = roster_entries
            counts["player_images_refreshed"] = _refresh_missing_player_images(
                cursor, first_year
            )
            if download_images:
                (
                    counts["images_downloaded"],
                    counts["teams_with_image_urls"],
                    counts["players_with_image_urls"],
                ) = _download_all_images(cursor, first_year)
    finally:
        connection.close()
    return counts


def main():
    parser = argparse.ArgumentParser(
        description="Refresh 2026 VLR team, roster, event, and image data."
    )
    parser.add_argument(
        "--no-download",
        action="store_true",
        help="Refresh metadata without downloading image files.",
    )
    parser.add_argument(
        "--historical-events", action="store_true",
        help="Include event placements and roster evidence for imported 2021–2026 events.",
    )
    parser.add_argument("--placements-only", action="store_true", help="Refresh final placements and prizes only.")
    parser.add_argument("--through-year", type=int, choices=range(2021, 2027), default=2026)
    args = parser.parse_args()
    if args.through_year != 2026 and not args.historical_events:
        parser.error("--through-year requires --historical-events")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    print(sync_vlr_profiles(
        download_images=not args.no_download,
        historical_events=args.historical_events,
        placements_only=args.placements_only,
        through_year=args.through_year,
    ))


if __name__ == "__main__":
    main()
