import re
import time
import json
from bs4 import BeautifulSoup
from curl_cffi import requests
from curl_cffi.requests.exceptions import RequestException
from urllib.parse import urljoin

session = requests.Session(impersonate="chrome120")

def safe_get(url, max_retries=3):
    for attempt in range(max_retries):
        try:
            response = session.get(url, timeout=30)
            return response
            
        except RequestException as e:
            print(f"  -> Warning: Attempt {attempt + 1} failed for {url}. Error: {e}")
            if attempt < max_retries - 1:
                print("  -> Waiting 5 seconds before retrying...")
                time.sleep(5)
            else:
                print(f"  -> Giving up on {url} after {max_retries} attempts.")
                return None

def parse_tournaments(html):

    soup = BeautifulSoup(html, "html.parser")
    events = soup.find_all("a", class_="event-item", href=re.compile(r"^/event/\d+/"))

    tournaments = []

    for event in events:
        title_element = event.find(class_="event-item-title")
        event_title = title_element.get_text(" ", strip=True)

        if "2026" not in event_title:
            continue

        event_url = urljoin("https://www.vlr.gg", event.get("href", ""))

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
            "url": event_url,
            "status": event_status,
            "id": event_id,
            "matches": [],
        })

    return tournaments

def get_matches_page_url(tournament_url):
    response = safe_get(tournament_url)

    soup = BeautifulSoup(response.text, "html.parser")

    matches_link = soup.find("a", href=re.compile(r"^/event/matches/\d+/"))

    if matches_link is None:
        return None

    return urljoin(
        "https://www.vlr.gg",
        matches_link["href"]
    )

def get_match_links(matches_page_url):
    response = safe_get(matches_page_url)

    soup = BeautifulSoup(response.text, "html.parser")

    match_links = []
    for match in soup.find_all("a", href=re.compile(r"^/\d+/")):
        match_links.append(urljoin("https://www.vlr.gg", match["href"]))

    return match_links

def parse_player(map_section):
    players = []

    player_rows = map_section.select(".ovw-row:not(.mod-head)")

    for player_row in player_rows:
        name_element = player_row.select_one(".ovw-player-name")
        team_element = player_row.select_one(".ovw-player-tag")
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


def parse_maps(soup):
    maps = []
    players = []

    map_sections = soup.find_all(class_="vm-stats-game")
    for map_section in map_sections:
        game_id = map_section.get("data-game-id")
        if (game_id == "all"): continue

        game_header_element = map_section.find(class_="vm-stats-game-header")
        team1_score_element = game_header_element.select_one(".team .score")
        team2_score_element = game_header_element.select_one(".team.mod-right .score")
        map_name_element = game_header_element.select_one(".map > div:first-child > span:first-child")

        map_data = {
            "map_name": map_name_element.find(string=True, recursive=False).strip() if map_name_element else None,
            "game_id": game_id,
            "team1_score": team1_score_element.get_text(strip=True) if team1_score_element else None,
            "team2_score": team2_score_element.get_text(strip=True) if team2_score_element else None,
            "players": parse_player(map_section)
        }
        maps.append(map_data)

    return maps

def parse_match(match_url):
    response = safe_get(match_url)
    soup = BeautifulSoup(response.text, "html.parser")

    match_id_match = re.search(r"/(\d+)/", match_url)
    match_id = (
        match_id_match.group(1)
        if match_id_match
        else None
    )

    match_notes = soup.find_all(class_="match-header-vs-note")

    match_status = match_notes[0].get_text(strip = True) if match_notes else None
    if (match_status != "final"):
        return None

    team1_element = soup.select_one(".match-header-link-name.mod-1 .wf-title-med")
    team2_element = soup.select_one(".match-header-link-name.mod-2 .wf-title-med")

    score_elements = soup.find_all("span", class_=re.compile(r"match-header-vs-score-(loser|winner)$"))

    match = {
        "id": match_id,
        "url": match_url,
        "status": match_status,
        "format": match_notes[1].get_text(strip = True) if len(match_notes) > 1 else None,
        "team1": team1_element.get_text(strip = True) if team1_element else None,
        "team2": team2_element.get_text(strip = True) if team2_element else None,
        "team1_score": score_elements[0].get_text(strip = True) if score_elements else None,
        "team2_score": score_elements[1].get_text(strip = True) if len(score_elements) > 1 else None,
        "maps": parse_maps(soup),
    }

    return match

if __name__ == "__main__":
    import os

    base_url = "https://www.vlr.gg/events/?region=all&tier=60"
    base_response = safe_get(base_url)

    tournaments = parse_tournaments(base_response.text)

    for tournament in tournaments:
        print(f"Title: {tournament['title']}")
        print(f"URL: {tournament['url']}")
        print(f"Status: {tournament['status']}")

        matches_page_url = get_matches_page_url(tournament['url'])
        if matches_page_url == None:
            continue

        time.sleep(2)

        match_links = get_match_links(matches_page_url)
        for match_link in match_links:
            time.sleep(2)
            print(f"Match Link: {match_link}")
            match_data = parse_match(match_link)
            if match_data is not None:
                tournament["matches"].append(match_data)

    os.makedirs("data", exist_ok=True)
    with open("data/data.json", "w", encoding="utf-8") as f:
        json.dump(tournaments, f, indent=4, ensure_ascii=False)
            
    print("Scraped data successfully saved to data/data.json")