"""Historical roster and map inputs for the fictional Champions simulator."""

from collections import Counter, defaultdict
from pathlib import Path
import re
from urllib.parse import urlsplit

from src.analytics.roles import agent_catalog, agent_profile
from src.db.database import connect


REGIONS = ("Americas", "EMEA", "Pacific", "China")
MAP_NAMES = ("Abyss", "Ascent", "Bind", "Breeze", "Corrode", "Fracture", "Haven",
             "Icebox", "Lotus", "Pearl", "Split", "Summit", "Sunset")
STATIC = Path(__file__).resolve().parents[1] / "web" / "static"


def territory(title, region):
    title = title.lower()
    if region in REGIONS:
        return region
    if re.search(r"\bchina\b", title):
        return "China"
    if re.search(r"americas?|\b(?:br|na)\b|latam|brazil", title):
        return "Americas"
    if re.search(r"emea|europe|turkey|türkiye|\bcis\b", title):
        return "EMEA"
    if re.search(r"pacific|oceania|japan|korea|asia|thailand|vietnam|philippines|indonesia|taiwan|malaysia|singapore", title):
        return "Pacific"
    return None


def _media(local, url):
    sources = []
    if local and local.startswith("/assets/"):
        target = (STATIC / local.lstrip("/")).resolve()
        if target.is_relative_to(STATIC / "assets") and target.is_file():
            sources.append(local)
    if url:
        parsed = urlsplit(url)
        supported = parsed.hostname in {"vlr.gg", "www.vlr.gg", "owcdn.net"} or (
            parsed.hostname == "static.lolesports.com" and parsed.path.startswith("/players/")
        )
        if parsed.scheme == "https" and supported and not re.search(r"/(?:sil|vlr)\.png$", parsed.path, re.I):
            sources.append(url)
    return sources


def _skill(rating, acs, maps):
    rating = float(rating) if rating is not None else 1.0
    acs = float(acs) if acs is not None else 205.0
    reliability = maps / (maps + 15)
    return round(max(0.7, min(1.35, 1 + reliability * (0.7 * (rating - 1) + 0.3 * (acs / 205 - 1)))), 4)


def simulator_catalog(early_match_filter, season_power):
    with connect() as db, db.cursor() as cursor:
        cursor.execute(f"""
            WITH played AS MATERIALIZED (
                SELECT g.id AS game_id, s.year, t.title ~* '^Valorant Champions 20' AS champions
                FROM games g JOIN matches m ON m.id = g.match_id
                JOIN tournaments t ON t.id = m.tournament_id JOIN seasons s ON s.season_id = t.season_id
                WHERE t.tier = 'tier1' AND s.year BETWEEN 2021 AND 2026
                  AND lower(m.status) IN ('final', 'completed', 'complete')
                  AND g.team1_score IS NOT NULL AND g.team2_score IS NOT NULL
                  AND (s.year <> 2021 OR ({early_match_filter}))
            ),
            totals AS (
                SELECT played.year, stats.player_id, stats.team_id,
                       COUNT(DISTINCT stats.game_id) AS maps,
                       COUNT(DISTINCT stats.game_id) FILTER (WHERE champions) AS champs_maps,
                       AVG(stats.rating) AS rating, AVG(stats.acs) AS acs,
                       ARRAY_AGG(stats.agent) AS agents
                FROM played JOIN player_stats stats ON stats.game_id = played.game_id
                WHERE stats.player_id IS NOT NULL AND stats.team_id IS NOT NULL
                GROUP BY 1, 2, 3
                HAVING COUNT(DISTINCT stats.game_id) >= 10
                    OR COUNT(DISTINCT stats.game_id) FILTER (WHERE champions) >= 2
            )
            SELECT totals.*, p.canonical_name, p.image_url, p.image_local_path,
                   t.canonical_name, t.logo_url, t.logo_local_path
            FROM totals JOIN players p USING (player_id) JOIN teams t USING (team_id)
            ORDER BY year, maps DESC, team_id, player_id
        """)
        stats = cursor.fetchall()
        cursor.execute("""
            SELECT side.team_id, s.year, t.title, t.region, COUNT(*)
            FROM matches m JOIN tournaments t ON t.id=m.tournament_id
            JOIN seasons s ON s.season_id=t.season_id
            CROSS JOIN LATERAL (VALUES (m.team1_id), (m.team2_id)) AS side(team_id)
            WHERE t.tier='tier1' AND s.year BETWEEN 2021 AND 2026 AND side.team_id IS NOT NULL
              AND t.title !~* '(^Valorant Champions 20|lock//in)'
              AND (t.title !~* 'masters' OR (s.year=2021 AND t.title ~* 'stage 1: masters'))
            GROUP BY 1, 2, 3, 4
        """)
        team_regions = defaultdict(Counter)
        for team_id, year, title, region, matches in cursor:
            region = territory(title, region)
            if region:
                team_regions[team_id, year][region] += matches

        cursor.execute("""
            SELECT DISTINCT initcap(lower(split_part(trim(g.map_name), ' ', 1)))
            FROM games g JOIN matches m ON m.id=g.match_id
            JOIN tournaments t ON t.id=m.tournament_id
            WHERE t.title='Valorant Champions 2026'
              AND g.team1_score IS NOT NULL AND g.team2_score IS NOT NULL
        """)
        map_pool = sorted(row[0] for row in cursor if row[0] in MAP_NAMES)
        if len(map_pool) < 5:
            raise ValueError("The Champions 2026 map pool is missing from the database.")

        cursor.execute("""
            WITH lineups AS (
                SELECT initcap(lower(split_part(trim(g.map_name), ' ', 1))) AS map,
                       ARRAY_AGG(DISTINCT regexp_replace(lower(ps.agent), '[^a-z0-9]', '', 'g')
                                 ORDER BY regexp_replace(lower(ps.agent), '[^a-z0-9]', '', 'g')) AS agents
                FROM games g JOIN matches m ON m.id=g.match_id JOIN tournaments t ON t.id=m.tournament_id
                JOIN seasons s ON s.season_id=t.season_id JOIN player_stats ps ON ps.game_id=g.id
                WHERE t.tier='tier1' AND s.year BETWEEN 2021 AND 2026
                  AND initcap(lower(split_part(trim(g.map_name), ' ', 1))) = ANY(%s)
                  AND ps.team_id IS NOT NULL AND ps.agent IS NOT NULL
                  AND lower(m.status) IN ('final', 'completed', 'complete')
                  AND g.team1_score IS NOT NULL AND g.team2_score IS NOT NULL
                GROUP BY g.id, ps.team_id
                HAVING COUNT(DISTINCT ps.player_id)=5
            )
            SELECT map, agents, COUNT(*) FROM lineups
            WHERE cardinality(agents)=5 GROUP BY 1,2 ORDER BY 1,3 DESC,2
        """, (map_pool,))
        catalog = agent_catalog()
        comps = defaultdict(list)
        for map_name, agents, count in cursor:
            if len(comps[map_name]) < 6 and all(agent in catalog for agent in agents):
                comps[map_name].append({"agents": agents, "uses": count})

    versions = {}
    champ_rosters = defaultdict(list)
    for year, pid, team_id, maps, champs_maps, rating, acs, picks, name, image, local, team, logo, logo_local in stats:
        role = agent_profile(picks)["role"]
        preferences = Counter(re.sub(r"[^a-z0-9]", "", pick.lower()) for pick in picks if pick)
        power_score = season_power.get((year, pid))
        # Keep 70 power points at the engine's neutral 1.0 strength.
        skill = (round(1 + (power_score - 70) / 100, 4) if power_score is not None
                 else _skill(rating, acs, maps))
        bundled = f"/assets/players/{pid}_{Path(urlsplit(image or '').path).name}"
        player = {
            "id": pid, "year": year, "name": name, "image": _media(local or bundled, image),
            "team": team, "role": role, "skill": skill, "power_score": power_score,
            "agents": [agent for agent, _ in preferences.most_common() if agent in catalog][:6],
        }
        if role and maps >= 10 and player["image"]:
            versions.setdefault((year, pid), player)
        if champs_maps >= 2:
            champ_rosters[year, team_id].append((champs_maps, maps, player, _media(logo_local, logo)))

    draft = defaultdict(list)
    for player in versions.values():
        draft[player["year"], player["role"]].append(player)
    draft_pool = [
        player for candidates in draft.values()
        for player in sorted(candidates, key=lambda p: p["skill"], reverse=True)[:60]
    ]
    teams = []
    for (year, team_id), entries in champ_rosters.items():
        if len(entries) < 5:
            continue
        entries.sort(key=lambda row: (-row[0], -row[1], row[2]["id"]))
        region = team_regions.get((team_id, year))
        if not region:
            region = next((team_regions[team_id, later] for later in range(year + 1, 2027)
                           if (team_id, later) in team_regions), None)
        if not region:
            continue
        roster = [entry[2] for entry in entries[:5]]
        if not entries[0][3] or not all(player["image"] for player in roster):
            continue
        teams.append({
            "id": f"{team_id}-{year}", "org": team_id, "year": year, "name": roster[0]["team"],
            "region": region.most_common(1)[0][0], "logo": entries[0][3], "roster": roster,
        })
    if any(len({team["org"] for team in teams if team["region"] == region}) < 4 for region in REGIONS):
        raise ValueError("Four historical Champions teams with complete images per territory are required.")
    if any(len(comps[name]) == 0 for name in map_pool):
        raise ValueError("The simulator is missing historical agent compositions.")
    return {
        "regions": REGIONS, "players": draft_pool, "teams": teams,
        "maps": map_pool, "comps": dict(comps),
        "agents": {key: {field: entry[field] for field in ("name", "role", "image")}
                   for key, entry in catalog.items()},
    }
