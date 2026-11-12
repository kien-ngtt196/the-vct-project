import re
import time
import json
import os
import argparse
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from curl_cffi import requests
from curl_cffi.requests.exceptions import RequestException
from urllib.parse import urljoin

session = requests.Session(impersonate="chrome120")
MIN_EVENT_YEAR = 2021
BASE_URL = "https://www.vlr.gg"
TIER_QUERY_VALUE = "60"
REQUEST_INTERVAL_SECONDS = 1.0
last_request_started = 0.0
player_image_cache = {}
event_details_cache = {}


def safe_get(url, max_retries=3):
    global last_request_started
    for attempt in range(max_retries):
        response = None
        try:
            elapsed = time.monotonic() - last_request_started
            if elapsed < REQUEST_INTERVAL_SECONDS:
                time.sleep(REQUEST_INTERVAL_SECONDS - elapsed)
            last_request_started = time.monotonic()
            response = session.get(url, timeout=30)
            if response.status_code == 429 or response.status_code >= 500:
                raise RequestException(f"HTTP {response.status_code}")
            response.raise_for_status()
            return response

        except RequestException as e:
            print(f"  -> Warning: Attempt {attempt + 1} failed for {url}. Error: {e}")
            if response is not None and 400 <= response.status_code < 500 and response.status_code != 429:
                return None
            if attempt < max_retries - 1:
                retry_after = None
                if response is not None:
                    try:
                        retry_after = float(response.headers.get("Retry-After", ""))
                    except (TypeError, ValueError):
                        retry_after = None
                delay = min(60, max(2 ** attempt, retry_after or 0))
                print(f"  -> Waiting {delay} seconds before retrying...")
                time.sleep(delay)
            else:
                print(f"  -> Giving up on {url} after {max_retries} attempts.")
                return None


def extract_year_from_text(text):
    if not text:
        return None

    match = re.search(r"(20\d{2})", text)
    if match is None:
        return None

    return int(match.group(1))


def normalize_url(value):
    if not value:
        return None

    return urljoin(BASE_URL, value)


def parse_vlr_date(value):
    if value is None or str(value).strip() == "":
        return None
    text = str(value).strip()
    try:
        if text.isdigit():
            return datetime.fromtimestamp(int(text), tz=timezone.utc)
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (ValueError, OverflowError, OSError):
        return None


def parse_event_dates(text):
    match = re.search(
        r"Dates\s+([A-Za-z]+)\s+(\d{1,2})\s*[–—-]\s*"
        r"(?:(?P<end_month>[A-Za-z]+)\s+)?(\d{1,2})(?:,\s*(20\d{2}))?",
        text or "",
        re.IGNORECASE,
    )
    if match is None or match.group(5) is None:
        single_day = re.search(
            r"Dates\s+([A-Za-z]+)\s+(\d{1,2}),\s*(20\d{2})\b",
            text or "",
            re.IGNORECASE,
        )
        if single_day is None:
            return None, None
        for month_format in ("%b", "%B"):
            try:
                date = datetime.strptime(" ".join(single_day.groups()), f"{month_format} %d %Y").date()
                return date.isoformat(), date.isoformat()
            except ValueError:
                continue
        return None, None

    end_year = int(match.group(5))

    def month_number(month_name):
        try:
            return datetime.strptime(month_name, "%b").month
        except ValueError:
            return datetime.strptime(month_name, "%B").month

    start_month_name = match.group(1)
    end_month_name = match.group("end_month") or start_month_name
    start_day = int(match.group(2))
    end_day = int(match.group(4))
    start_month = month_number(start_month_name)
    end_month = month_number(end_month_name)
    start_year = end_year - 1 if start_month > end_month else end_year
    start_date = datetime.strptime(
        f"{start_month_name} {start_day} {start_year}", "%b %d %Y"
    ).date()
    end_date = datetime.strptime(
        f"{end_month_name} {end_day} {end_year}", "%b %d %Y"
    ).date()
    return start_date.isoformat(), end_date.isoformat()


def get_event_details(event_url):
    if event_url in event_details_cache:
        return event_details_cache[event_url]

    response = safe_get(event_url)
    if response is None:
        details = {
            "season": None,
            "logo_url": None,
            "region": None,
            "start_date": None,
            "end_date": None,
            "matches_page_url": None,
        }
        event_details_cache[event_url] = details
        return details

    soup = BeautifulSoup(response.text, "html.parser")
    page_text = " ".join(soup.stripped_strings)
    logo_element = soup.select_one(".event-header img")
    region_element = soup.select_one(".event-header-main-bc-tags a[href*='region=']")
    matches_link = soup.find("a", href=re.compile(r"^/event/matches/\d+/"))
    start_date, end_date = parse_event_dates(page_text)

    details = {
        "season": extract_year_from_text(page_text),
        "logo_url": normalize_url(logo_element.get("src") if logo_element else None),
        "region": region_element.get_text(" ", strip=True) if region_element else None,
        "start_date": start_date,
        "end_date": end_date,
        "matches_page_url": (
            normalize_url(matches_link["href"].split("?", 1)[0]) if matches_link else None
        ),
    }
    event_details_cache[event_url] = details
    return details


def parse_tournaments(html):
    soup = BeautifulSoup(html, "html.parser")
    events = soup.find_all("a", class_="event-item", href=re.compile(r"^/event/\d+/"))

    tournaments = []

    for event in events:
        title_element = event.find(class_="event-item-title")
        if title_element is None:
            continue

        event_title = title_element.get_text(" ", strip=True)
        event_url = urljoin("https://www.vlr.gg", event.get("href", ""))

        season = extract_year_from_text(event_title)
        logo_element = event.find("img")
        logo_url = normalize_url(logo_element.get("src") if logo_element else None)
        event_details = get_event_details(event_url)
        season = season or extract_year_from_text(event_details["end_date"]) or event_details["season"]
        logo_url = logo_url or event_details["logo_url"]

        if season is None or season < MIN_EVENT_YEAR:
            continue

        status_element = event.find(class_="event-item-desc-item-status")
        event_status = (
            status_element.get_text(" ", strip=True).lower()
            if status_element
            else "unknown"
        )
        event_href = event.get("href", "")
        event_id_match = re.search(r"/event/(\d+)/", event_href)
        event_id = event_id_match.group(1) if event_id_match else None

        tournaments.append({
            "title": event_title,
            "season": season,
            "tier": "tier1",
            "url": event_url,
            "logo_url": logo_url,
            "region": event_details.get("region"),
            "start_date": event_details.get("start_date"),
            "end_date": event_details.get("end_date"),
            "status": event_status,
            "id": event_id,
            "matches": [],
        })

    return tournaments

def get_matches_page_url(tournament_url):
    cached_details = event_details_cache.get(tournament_url)
    if cached_details is not None and cached_details.get("matches_page_url"):
        return cached_details.get("matches_page_url")

    response = safe_get(tournament_url)
    if response is None:
        print(f"Skipping tournament page due to failed request: {tournament_url}")
        return None

    soup = BeautifulSoup(response.text, "html.parser")

    matches_link = soup.find("a", href=re.compile(r"^/event/matches/\d+/"))

    if matches_link is None:
        return None

    return urljoin(
        "https://www.vlr.gg",
        matches_link["href"].split("?", 1)[0]
    )

def get_match_links(matches_page_url):
    response = safe_get(matches_page_url)
    if response is None:
        print(f"Skipping matches page due to failed request: {matches_page_url}")
        return []

    soup = BeautifulSoup(response.text, "html.parser")

    match_links = []
    seen_links = set()
    for match in soup.find_all("a", href=re.compile(r"^/\d+/")):
        link = urljoin(BASE_URL, match["href"])
        match_id = match["href"].split("/")[1]
        if match_id not in seen_links:
            seen_links.add(match_id)
            match_links.append(link)

    return match_links

def get_player_image(player_url):
    if not player_url:
        return None

    if player_url in player_image_cache:
        return player_image_cache[player_url]

    response = safe_get(player_url)
    if response is None:
        player_image_cache[player_url] = None
        return None

    soup = BeautifulSoup(response.text, "html.parser")
    image_element = soup.select_one(".wf-avatar.mod-player img")
    image_url = normalize_url(image_element.get("src") if image_element else None)
    player_image_cache[player_url] = image_url
    return image_url


def parse_player(map_section, *, fetch_images=True):
    players = []

    player_rows = map_section.select(".ovw-row:not(.mod-head)")

    for player_row in player_rows:
        name_element = player_row.select_one(".ovw-player-name")
        team_element = player_row.select_one(".ovw-player-tag")
        player_link_element = player_row.select_one(".ovw-player a[href^='/player/']")
        profile_url = normalize_url(player_link_element.get("href") if player_link_element else None)
        nationality_element = player_row.select_one(".ovw-player .flag")
        agent_element = player_row.select_one(".ovw-agents .stats-sq img")
        rating_element = player_row.select_one("div[data-col='rating2'] .side.mod-both")
        acs_element = player_row.select_one("div[data-col='acs'] .side.mod-both")
        kills_element = player_row.select_one("span[data-col='kills'] .side.mod-both")
        deaths_element = player_row.select_one("span[data-col='deaths'] .side.mod-both")
        assists_element = player_row.select_one("span[data-col='assists'] .side.mod-both")
        kd_diff_element = player_row.select_one("div[data-col='kd-diff'] .side.mod-both")
        kast_element = player_row.select_one("div[data-col='kast'] .side.mod-both")
        adr_element = player_row.select_one("div[data-col='adr'] .side.mod-both")
        headshot_percentage_element = player_row.select_one("div[data-col='hsp'] .side.mod-both")
        first_kills_element = player_row.select_one("div[data-col='fb'] .side.mod-both")
        first_deaths_element = player_row.select_one("div[data-col='fd'] .side.mod-both")

        player_data = {
            'name': name_element.get_text(strip=True) if name_element else None,
            'team': team_element.get_text(strip=True) if team_element else None,
            'profile_url': profile_url,
            'image_url': get_player_image(profile_url) if fetch_images else None,
            'nationality': nationality_element.get("title") if nationality_element else None,
            'agent': agent_element.get("alt") if agent_element else None,
            'rating': rating_element.get_text(strip=True) if rating_element else None,
            'acs': acs_element.get_text(strip=True) if acs_element else None,
            'kills': kills_element.get_text(strip=True) if kills_element else None,
            'deaths': deaths_element.get_text(strip=True) if deaths_element else None,
            'assists': assists_element.get_text(strip=True) if assists_element else None,
            'kd_diff': kd_diff_element.get_text(strip=True) if kd_diff_element else None,
            'kast': kast_element.get_text(strip=True) if kast_element else None,
            'adr': adr_element.get_text(strip=True) if adr_element else None,
            'headshot_percentage': headshot_percentage_element.get_text(strip=True) if headshot_percentage_element else None,
            'first_kills': first_kills_element.get_text(strip=True) if first_kills_element else None,
            'first_deaths': first_deaths_element.get_text(strip=True) if first_deaths_element else None,
        }

        players.append(player_data)

    return players


def parse_maps(soup, *, fetch_images=True):
    maps = []

    map_sections = soup.find_all(class_="vm-stats-game")
    for map_section in map_sections:
        game_id = map_section.get("data-game-id")
        if not game_id or game_id == "all":
            continue

        game_header_element = map_section.find(class_="vm-stats-game-header")
        if game_header_element is None:
            continue
        team1_score_element = game_header_element.select_one(".team .score")
        team2_score_element = game_header_element.select_one(".team.mod-right .score")
        map_name_element = game_header_element.select_one(".map > div:first-child > span:first-child")

        map_data = {
            "map_name": map_name_element.get_text(" ", strip=True) if map_name_element else None,
            "game_id": game_id,
            "team1_score": team1_score_element.get_text(strip=True) if team1_score_element else None,
            "team2_score": team2_score_element.get_text(strip=True) if team2_score_element else None,
            "players": parse_player(map_section, fetch_images=fetch_images)
        }
        maps.append(map_data)

    return maps

def parse_match(match_url, *, fetch_images=True):
    response = safe_get(match_url)
    if response is None:
        print(f"Skipping match page due to failed request: {match_url}")
        return None

    soup = BeautifulSoup(response.text, "html.parser")

    match_id_match = re.search(r"/(\d+)/", match_url)
    match_id = (
        match_id_match.group(1)
        if match_id_match
        else None
    )

    match_notes = soup.find_all(class_="match-header-vs-note")

    match_status = match_notes[0].get_text(strip = True) if match_notes else None
    if match_status:
        match_status = match_status.lower()

    team1_element = soup.select_one(".match-header-link-name.mod-1 .wf-title-med, .match-header-link.mod-1 .wf-title-med")
    team2_element = soup.select_one(".match-header-link-name.mod-2 .wf-title-med, .match-header-link.mod-2 .wf-title-med")
    team1_link_element = soup.select_one(".match-header-link.mod-1")
    team2_link_element = soup.select_one(".match-header-link.mod-2")
    if not (match_id and match_status and team1_element and team2_element):
        print(f"  -> Missing match header for {match_url}")
        return None

    score_elements = soup.find_all("span", class_=re.compile(r"match-header-vs-score-(loser|winner)$"))

    date_element = soup.select_one(".moment-tz-convert")
    match_date = (date_element.get("data-utc-ts") or date_element.get_text(strip=True)) if date_element else None

    match = {
        "id": match_id,
        "url": match_url,
        "status": match_status,
        "date": match_date,
        "format": match_notes[1].get_text(strip = True) if len(match_notes) > 1 else None,
        "team1": team1_element.get_text(strip = True) if team1_element else None,
        "team2": team2_element.get_text(strip = True) if team2_element else None,
        "team1_url": normalize_url(team1_link_element.get("href") if team1_link_element else None),
        "team2_url": normalize_url(team2_link_element.get("href") if team2_link_element else None),
        "team1_logo_url": normalize_url(team1_link_element.find("img").get("src") if team1_link_element and team1_link_element.find("img") else None),
        "team2_logo_url": normalize_url(team2_link_element.find("img").get("src") if team2_link_element and team2_link_element.find("img") else None),
        "team1_score": score_elements[0].get_text(strip = True) if score_elements else None,
        "team2_score": score_elements[1].get_text(strip = True) if len(score_elements) > 1 else None,
        "maps": parse_maps(soup, fetch_images=fetch_images) if match_status == "final" else [],
    }

    return match


def write_snapshot(tournaments, filename):
    output_dir = os.path.join("data", "raw")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, filename)
    temporary_path = f"{output_path}.tmp"
    with open(temporary_path, "w", encoding="utf-8") as snapshot:
        json.dump(tournaments, snapshot, indent=4, ensure_ascii=False)
    os.replace(temporary_path, output_path)
    return output_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scrape VLR.gg tier-one VALORANT events.")
    parser.add_argument(
        "--since",
        default=None,
        help="Include matches on or after this UTC date (YYYY-MM-DD).",
    )
    parser.add_argument("--through-year", type=int, help="Last season to include.")
    parser.add_argument("--max-pages", type=int, default=29)
    parser.add_argument("--page-delay", type=float, default=1.0)
    parser.add_argument("--match-delay", type=float, default=2.0)
    parser.add_argument(
        "--backfill", action="store_true",
        help="Import historical events one at a time, starting at Reykjavík 2022.",
    )
    args = parser.parse_args()
    reykjavik_pilot = args.backfill and args.since is None
    if args.backfill:
        from src.db.import_vlr import has_complete_series_stats, import_snapshot, is_tier_one_event

    now = datetime.now(timezone.utc)
    start = args.since or ("2022-04-10" if args.backfill else f"{now.year}-01-01")
    timestamp = now.strftime("%Y%m%dT%H%M%SZ")
    try:
        since = datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        parser.error("--since must be a date in YYYY-MM-DD format")
    if args.max_pages < 1 or args.page_delay < 0 or args.match_delay < 0:
        parser.error("--max-pages must be positive and delays cannot be negative")

    if args.through_year is not None and args.through_year < since.year:
        parser.error("--through-year must be on or after the start season")

    tournaments = []
    seen_event_urls = set()

    for page in range(1, args.max_pages + 1):
        page_url = f"{BASE_URL}/events/?region=all&tier={TIER_QUERY_VALUE}&page={page}"
        print(f"Fetching page {page}: {page_url}")

        page_response = safe_get(page_url)
        if page_response is None:
            if args.backfill:
                raise SystemExit(f"Could not read VLR event listing page {page}.")
            break

        page_tournaments = parse_tournaments(page_response.text)
        if not page_tournaments:
            break

        matching_year = False
        for tournament in page_tournaments:
            if tournament["season"] >= since.year:
                matching_year = True
            if args.through_year is not None and tournament["season"] > args.through_year:
                continue
            if tournament["url"] in seen_event_urls:
                continue

            seen_event_urls.add(tournament["url"])
            end_date = tournament.get("end_date")
            if args.backfill:
                start_date = tournament.get("start_date")
                if tournament["season"] > now.year or (
                    start_date and datetime.fromisoformat(start_date).date() > now.date()
                ):
                    continue
                if not is_tier_one_event(tournament["title"]):
                    continue
            if (
                tournament["season"] >= since.year
                and (end_date is None or datetime.fromisoformat(end_date).date() >= since.date())
            ):
                tournaments.append(tournament)

        if not matching_year:
            break

        time.sleep(args.page_delay)

    if reykjavik_pilot:
        if not any(event["id"] == "926" for event in tournaments):
            raise SystemExit("The Tier 1 listing did not reach Masters Reykjavík 2022.")
        tournaments.sort(key=lambda event: (event["id"] != "926", event["season"]))
    if args.backfill and not tournaments:
        raise SystemExit("No Tier 1 events found for the requested seasons.")
    if args.backfill and not reykjavik_pilot:
        from src.db.database import connect

        with connect() as connection, connection.cursor() as cursor:
            cursor.execute("""
                WITH played_maps AS (
                    SELECT g.match_id, g.id, COUNT(ps.player_id) AS player_count
                    FROM games g LEFT JOIN player_stats ps ON ps.game_id = g.id
                    WHERE g.team1_score IS NOT NULL AND g.team2_score IS NOT NULL
                    GROUP BY g.match_id, g.id
                ), series AS (
                    SELECT match_id, COUNT(*) AS map_count, MIN(player_count) AS min_players
                    FROM played_maps GROUP BY match_id
                )
                SELECT m.id, m.tournament_id,
                       COALESCE(m.match_date IS NOT NULL AND m.team1_id IS NOT NULL
                         AND m.team2_id IS NOT NULL AND (
                           (lower(m.status) = 'final' AND series.map_count = m.team1_score + m.team2_score
                            AND series.min_players >= 10)
                           OR lower(m.status) LIKE 'forfeit%%'
                         ), FALSE)
                FROM matches m LEFT JOIN series ON series.match_id = m.id
                WHERE m.tournament_id = ANY(%s)
                """, ([event["id"] for event in tournaments],))
            saved = cursor.fetchall()
        existing_matches = {match_id for match_id, _, complete in saved if complete}
        known_events = {event_id for _, event_id, _ in saved}
        tournaments.sort(key=lambda event: (
            event["id"] in known_events, event["season"], event["start_date"] or "",
        ))
    else:
        existing_matches = set()
    incomplete_events = []
    for tournament in tournaments:
        print(f"Title: {tournament['title']}")
        print(f"Year: {tournament['season']}")
        print(f"URL: {tournament['url']}")
        print(f"Status: {tournament['status']}")

        matches_page_url = get_matches_page_url(tournament['url'])
        if matches_page_url is None:
            if reykjavik_pilot and tournament["id"] == "926":
                raise SystemExit("Could not find the Reykjavík matches page.")
            if args.backfill:
                incomplete_events.append(tournament["id"])
            continue

        time.sleep(args.page_delay)

        match_links = get_match_links(matches_page_url)
        collected = 0
        failed = 0
        incomplete_stats = []
        for match_number, match_link in enumerate(match_links, start=1):
            match_id = match_link.split("/")[3]
            if match_id in existing_matches:
                continue
            print(f"  Fetching match {match_number}/{len(match_links)} ({match_id})")
            time.sleep(args.match_delay)
            match_data = parse_match(match_link, fetch_images=not (args.backfill and args.through_year))
            if match_data is not None:
                match_date = parse_vlr_date(match_data.get("date"))
                if args.backfill and match_date is None:
                    print(f"  -> Missing match date for {match_link}")
                    failed += 1
                    continue
                if match_date is not None and match_date < since:
                    continue
                if args.backfill and match_date is not None and match_date > now:
                    continue
                tournament["matches"].append(match_data)
                collected += 1
                if args.backfill and match_data["status"] == "final" and not has_complete_series_stats(match_data):
                    incomplete_stats.append(match_id)
            else:
                failed += 1
        print(f"  Collected {collected} matches.")
        if args.backfill and incomplete_stats:
            print(f"  Final matches with incomplete map or player stats: {', '.join(incomplete_stats)}")
        if args.backfill and (failed or not match_links):
            incomplete_events.append(tournament["id"])
            print(f"  Incomplete listing or match details for event {tournament['id']}.")
        if reykjavik_pilot and tournament["id"] == "926" and collected != 24:
            raise SystemExit(f"Reykjavík pilot collected {collected} of 24 series.")
        if args.backfill and match_links:
            path = write_snapshot(
                [tournament], f"events_{timestamp}_{tournament['id']}.json"
            )
            import_snapshot(path)

    output_path = write_snapshot(tournaments, f"events_{timestamp}.json")

    print(f"Scraped data successfully saved to {output_path}")
    if incomplete_events:
        raise SystemExit(f"Backfill needs review for events: {', '.join(incomplete_events)}")
