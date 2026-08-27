import re
from bs4 import BeautifulSoup
import requests
from urllib.parse import urljoin

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
            "tournament_id": event_id,
        })

    return tournaments

def get_matches_page_url(tournament_url):
    response = requests.get(tournament_url, timeout=30)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    matches_link = soup.find("a", href=re.compile(r"^/event/matches/\d+/"))

    if matches_link is None:
        return None

    return urljoin(
        "https://www.vlr.gg",
        matches_link["href"]
    )

def get_match_links(matches_page_url):
    response = requests.get(matches_page_url, timeout=30)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    match_links = []
    for match in soup.find_all("a", href=re.compile(r"^/\d+/")):
        match_links.append(urljoin("https://www.vlr.gg", match["href"]))

    return match_links

def parse_maps(soup):
    maps = []

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
        }
        maps.append(map_data)

    return maps

def parse_match(match_url):
    response = requests.get(match_url, timeout = 30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    match_id_match = re.search(r"/(\d+)/", match_url)
    match_id = (
        match_id_match.group(1)
        if match_id_match
        else None
    )

    match_notes = soup.find_all(class_="match-header-vs-note")

    team1_element = soup.select_one(".match-header-link-name.mod-1 .wf-title-med")
    team2_element = soup.select_one(".match-header-link-name.mod-2 .wf-title-med")

    score_elements = soup.find_all("span", class_=re.compile(r"match-header-vs-score-(loser|winner)$"))

    match = {
        "id": match_id,
        "url": match_url,
        "status": match_notes[0].get_text(strip = True) if match_notes else None,
        "format": match_notes[1].get_text(strip = True) if len(match_notes) > 1 else None,
        "team1": team1_element.get_text(strip = True) if team1_element else None,
        "team2": team2_element.get_text(strip = True) if team2_element else None,
        "team1_score": score_elements[0].get_text(strip = True) if score_elements else None,
        "team2_score": score_elements[1].get_text(strip = True) if len(score_elements) > 1 else None,
        "maps": parse_maps(soup),
    }

    return match

base_url = "https://www.vlr.gg/events/?region=all&tier=60"
base_response = requests.get(base_url, timeout = 30)
base_response.raise_for_status()

tournaments = parse_tournaments(base_response.text)

# for tournament in tournaments:
#     print(f"Title: {tournament['title']}")
#     print(f"URL: {tournament['url']}")
#     print(f"Status: {tournament['status']}")
#     print(f"Tournament ID: {tournament['tournament_id']}")

#     matches_page_url = get_matches_page_url(tournament['url'])
#     print(f"Matches Page URL: {matches_page_url}")

#     if matches_page_url == None:
#         continue

#     match_links = get_match_links(matches_page_url)

#     print("-" * 40)    

tmp = parse_match("https://www.vlr.gg/742476/paper-rex-vs-nongshim-redforce-vct-2026-pacific-stage-2-ur1")
for key, value in tmp.items():
    print(f"{key}: {value}")
# tmp = parse_match("https://www.vlr.gg/742477/global-esports-vs-kiwoom-drx-vct-2026-pacific-stage-2-ur1")
# print(tmp)
