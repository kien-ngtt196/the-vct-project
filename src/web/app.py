import json
import logging
import mimetypes
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

import psycopg2

from src.analytics.power import (
    PLACEMENT_POINTS, PLAYER_EVENT_FULL_CREDIT_MAPS, PLAYER_EVENT_WIN_POINTS, PLAYER_FINISHES_COUNT,
    PLAYER_INTERNATIONAL_PRIOR_MAPS, PLAYER_INTERNATIONAL_RATING_CEILING, PLAYER_METRIC_WEIGHTS,
    PLAYER_POWER_POINTS, PLAYER_SAMPLE_PRIOR_MAPS, PLAYER_VOLUME_CAP, TEAM_POWER_WEIGHTS, achievement_points,
    calculate_player_power, calculate_team_power, placement_rank,
)
from src.analytics.roles import agent_profile
from src.analytics.simulator import simulator_catalog
from src.db.database import connect


STATIC_DIR = Path(__file__).resolve().parent / "static"
VCT_IMAGE_DIR = Path(__file__).resolve().parents[2] / "vct_images"
PLAYER_ID_PATTERN = re.compile(r"^/api/players/(\d+)$")
TEAM_ID_PATTERN = re.compile(r"^/api/teams/(\d+)$")
CHAMPIONS_EVENT_WEIGHT = 3.0
MASTERS_EVENT_WEIGHT = 2.0
REGIONAL_EVENT_WEIGHT = 1.0
PLAYER_EVENT_WEIGHTS = {
    "champions": (2.5, 3.0),
    "masters": (1.75, 2.25),
    "regional": (1.0, 1.25),
}

LOG = logging.getLogger("vct.web")

# Three historical exhibitions have generic VLR URL slugs.
EXHIBITION_MATCH_IDS = ("180279", "321373", "450589")


def competitive_match(alias):
    ids = ", ".join(f"'{match_id}'" for match_id in EXHIBITION_MATCH_IDS)
    return (
        f"{alias}.id NOT IN ({ids}) "
        f"AND COALESCE({alias}.url, '') !~* '(show-?match|all-star-match|exhibition)'"
    )


def ranking_match(alias, tournament_title, year):
    condition = competitive_match(alias)
    if year == 2021:
        condition += (
            f" AND (COALESCE({alias}.series_name, '') !~* 'qualifier|^preliminary round$'"
            f" OR {alias}.series_name ~* 'last chance'"
            f" OR {tournament_title} ~* 'last chance qualifier')"
        )
    return condition


def masters_event(title, year):
    condition = f"{title} ILIKE '%%masters%%'"
    if year == 2021:
        condition += f" AND {title} !~* 'stage 1:[[:space:]]*masters'"
    return condition


def _player_search(cursor, query, limit, year):
    cursor.execute(
        """
        SELECT p.player_id, p.canonical_name, p.image_url, p.image_local_path,
               p.nationality, p.source_url,
               COALESCE(current_team.team_id, season_team.team_id),
               COALESCE(current_team.canonical_name, season_team.canonical_name)
        FROM players p
        LEFT JOIN LATERAL (
            SELECT t.team_id, t.canonical_name
            FROM roster_memberships rm
            JOIN teams t ON t.team_id = rm.team_id
            WHERE %s = 2026 AND rm.player_id = p.player_id AND rm.status = 'current'
            ORDER BY rm.updated_at DESC
            LIMIT 1
        ) current_team ON TRUE
        LEFT JOIN LATERAL (
            SELECT t.team_id, t.canonical_name
            FROM match_players mp
            JOIN teams t ON t.team_id = mp.team_id
            JOIN matches m ON m.id = mp.match_id
            JOIN tournaments tournament ON tournament.id = m.tournament_id
            LEFT JOIN seasons event_season ON event_season.season_id = tournament.season_id
            WHERE mp.player_id = p.player_id
              AND m.match_date >= make_date(%s, 1, 1)
              AND m.match_date < make_date(%s + 1, 1, 1)
              AND COALESCE(event_season.year, EXTRACT(YEAR FROM m.match_date)::INTEGER) = %s
            ORDER BY m.match_date DESC, m.id DESC
            LIMIT 1
        ) season_team ON TRUE
        WHERE (p.canonical_name ILIKE %s
           OR EXISTS (
               SELECT 1 FROM player_aliases pa
               WHERE pa.player_id = p.player_id AND pa.alias_name ILIKE %s
           ))
          AND (current_team.team_id IS NOT NULL OR season_team.team_id IS NOT NULL)
        ORDER BY p.canonical_name
        LIMIT %s
        """,
        (year, year, year, year, f"%{query}%", f"%{query}%", limit),
    )
    return [
        {
            "type": "player",
            "id": row[0],
            "name": row[1],
            "image_url": row[2],
            "image_local_path": row[3],
            "nationality": row[4],
            "source_url": row[5],
            "team_id": row[6],
            "team": row[7],
        }
        for row in cursor.fetchall()
    ]


def _team_search(cursor, query, limit):
    cursor.execute(
        """
        WITH exact_matches AS (
            SELECT t.team_id
            FROM teams t
            WHERE lower(t.canonical_name) = lower(%s)
               OR EXISTS (
                   SELECT 1 FROM team_aliases ta
                   WHERE ta.team_id = t.team_id
                     AND lower(ta.alias_name) = lower(%s)
               )
        )
        SELECT t.team_id, t.canonical_name, t.logo_url, t.logo_local_path,
               t.source_url, team_region.region
        FROM teams t
        LEFT JOIN LATERAL (
            SELECT tournament.region
            FROM matches region_match
            JOIN tournaments tournament ON tournament.id = region_match.tournament_id
            LEFT JOIN seasons event_season ON event_season.season_id = tournament.season_id
            WHERE tournament.tier = 'tier1'
              AND region_match.match_date >= DATE '2026-01-01'
              AND region_match.match_date < DATE '2027-01-01'
              AND COALESCE(
                  event_season.year,
                  EXTRACT(YEAR FROM region_match.match_date)::INTEGER
              ) = 2026
              AND (region_match.team1_id = t.team_id OR region_match.team2_id = t.team_id)
              AND tournament.region IS NOT NULL
              AND (
                  tournament.region ILIKE '%%america%%'
                  OR tournament.region ILIKE '%%emea%%'
                  OR tournament.region ILIKE '%%europe%%'
                  OR tournament.region ILIKE '%%africa%%'
                  OR tournament.region ILIKE '%%middle east%%'
                  OR tournament.region ILIKE '%%pacific%%'
                  OR tournament.region ILIKE '%%asia%%'
                  OR tournament.region ILIKE '%%china%%'
              )
            GROUP BY tournament.region
            ORDER BY COUNT(*) DESC, tournament.region
            LIMIT 1
        ) team_region ON TRUE
        WHERE (
            t.team_id IN (SELECT team_id FROM exact_matches)
            OR (
                NOT EXISTS (SELECT 1 FROM exact_matches)
                AND (
                    t.canonical_name ILIKE %s
                    OR EXISTS (
                        SELECT 1 FROM team_aliases ta
                        WHERE ta.team_id = t.team_id AND ta.alias_name ILIKE %s
                    )
                )
            )
        )
          AND EXISTS (
              SELECT 1 FROM matches m
              JOIN tournaments tournament ON tournament.id = m.tournament_id
              LEFT JOIN seasons event_season ON event_season.season_id = tournament.season_id
              WHERE tournament.tier = 'tier1'
                AND m.match_date >= DATE '2026-01-01'
                AND m.match_date < DATE '2027-01-01'
                AND COALESCE(event_season.year, EXTRACT(YEAR FROM m.match_date)::INTEGER) = 2026
                AND (m.team1_id = t.team_id OR m.team2_id = t.team_id)
          )
        ORDER BY t.canonical_name
        LIMIT %s
        """,
        (query, query, f"%{query}%", f"%{query}%", limit),
    )
    return [
        {
            "type": "team",
            "id": row[0],
            "name": row[1],
            "image_url": row[2],
            "image_local_path": row[3],
            "source_url": row[4],
            "region": row[5],
        }
        for row in cursor.fetchall()
    ]


def search_entities(query, entity_type="all", limit=20, year=2026):
    if not 2021 <= year <= 2026:
        raise ValueError("Choose a season from 2021 to 2026.")
    if entity_type not in {"all", "players", "teams"}:
        raise ValueError("type must be all, players, or teams.")
    if not query.strip():
        return []
    with connect() as connection:
        with connection.cursor() as cursor:
            results = []
            if entity_type in {"all", "players"}:
                results.extend(_player_search(cursor, query.strip(), limit, year))
            if entity_type in {"all", "teams"}:
                results.extend(_team_search(cursor, query.strip(), limit))
    return results[:limit]


def tournament_honors(cursor, *, team_id=None, player_id=None):
    placements = ["1", "1st"]
    if player_id is not None:
        placements.extend(("2", "2nd", "3", "3rd"))
    cursor.execute(
        """
        SELECT t.id, t.title, t.url, t.logo_url, s.year, r.prize,
               r.placement_text, team.canonical_name, t.region,
               t.end_date, team.logo_url, team.logo_local_path
        FROM team_event_results r
        JOIN teams team ON team.team_id = r.team_id
        JOIN tournaments t ON t.id = r.tournament_id
        JOIN seasons s USING (season_id)
        WHERE t.tier = 'tier1' AND lower(trim(r.placement_text)) = ANY(%s)
          AND r.prize IS NOT NULL
          AND (
              r.team_id = %s OR EXISTS (
                  SELECT 1 FROM match_players mp JOIN matches m ON m.id = mp.match_id
                  WHERE m.tournament_id = r.tournament_id AND mp.team_id = r.team_id
                    AND mp.player_id = %s AND lower(m.status) IN ('final', 'completed', 'complete')
              )
          )
        ORDER BY s.year DESC, t.end_date DESC NULLS LAST, t.title
        """,
        (placements, team_id, player_id),
    )
    return [
        dict(id=row[0], title=row[1], url=row[2], logo_url=row[3], year=row[4], prize=row[5],
             rank=placement_rank(row[6]), team=row[7], region=row[8], end_date=row[9],
             team_logo_url=row[10], team_logo_local_path=row[11])
        for row in cursor.fetchall()
    ]


def player_details(player_id, year=2026):
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT player_id, canonical_name, image_url, image_local_path,
                       nationality, source_url
                FROM players
                WHERE player_id = %s
                """,
                (player_id,),
            )
            player = cursor.fetchone()
            if player is None:
                return None

            cursor.execute(
                """
                SELECT m.id, m.match_date, t.canonical_name, g.map_name,
                       ps.rating, ps.acs, ps.kast_percentage, ps.adr,
                       ps.kills, ps.deaths, ps.assists, ps.headshot_percentage,
                       ps.first_kills, ps.agent, m.url, tournament.title,
                       opponent.canonical_name, opponent.logo_url, opponent.logo_local_path,
                       CASE WHEN ps.team_id = m.team1_id THEN g.team1_score
                            WHEN ps.team_id = m.team2_id THEN g.team2_score END,
                       CASE WHEN ps.team_id = m.team1_id THEN g.team2_score
                            WHEN ps.team_id = m.team2_id THEN g.team1_score END,
                       t.logo_url, t.logo_local_path, tournament.logo_url
                FROM player_stats ps
                JOIN games g ON g.id = ps.game_id
                JOIN matches m ON m.id = g.match_id
                JOIN tournaments tournament ON tournament.id = m.tournament_id
                LEFT JOIN seasons event_season ON event_season.season_id = tournament.season_id
                LEFT JOIN teams t ON t.team_id = ps.team_id
                LEFT JOIN teams opponent ON opponent.team_id =
                    CASE WHEN ps.team_id = m.team1_id THEN m.team2_id
                         WHEN ps.team_id = m.team2_id THEN m.team1_id END
                WHERE ps.player_id = %s
                  AND tournament.tier = 'tier1'
                  AND COALESCE(event_season.year, EXTRACT(YEAR FROM m.match_date)::INTEGER) = %s
                ORDER BY m.match_date DESC NULLS LAST, m.id DESC, g.id
                LIMIT 10
                """,
                (player_id, year),
            )
            recent_maps = [
                {
                    "match_id": row[0],
                    "date": row[1],
                    "team": row[2],
                    "map": row[3],
                    "rating": row[4],
                    "acs": row[5],
                    "kast": row[6],
                    "adr": row[7],
                    "kills": row[8],
                    "deaths": row[9],
                    "assists": row[10],
                    "headshot_percentage": row[11],
                    "first_kills": row[12],
                    "agent": row[13],
                    "agent_portrait": next(iter(agent_profile([row[13]])["top_agents"]), None),
                    "match_url": row[14],
                    "event": row[15],
                    "opponent": row[16],
                    "opponent_logo_url": row[17],
                    "opponent_logo_local_path": row[18],
                    "team_score": row[19],
                    "opponent_score": row[20],
                    "team_logo_url": row[21],
                    "team_logo_local_path": row[22],
                    "event_logo_url": row[23],
                }
                for row in cursor.fetchall()
            ]

            cursor.execute(
                """
                SELECT COUNT(DISTINCT game.id),
                       COALESCE(SUM(stats.kills), 0),
                       COALESCE(SUM(stats.deaths), 0),
                       COALESCE(SUM(stats.assists), 0),
                       AVG(stats.rating),
                       AVG(stats.acs),
                       AVG(stats.kast_percentage),
                       AVG(stats.adr),
                       AVG(stats.headshot_percentage),
                       COALESCE(SUM(stats.first_kills), 0),
                       ARRAY_AGG(stats.agent) FILTER (
                           WHERE lower(match.status) IN ('final', 'completed', 'complete')
                       )
                FROM player_stats stats
                JOIN games game ON game.id = stats.game_id
                JOIN matches match ON match.id = game.match_id
                JOIN tournaments tournament ON tournament.id = match.tournament_id
                LEFT JOIN seasons event_season ON event_season.season_id = tournament.season_id
                WHERE stats.player_id = %s
                  AND tournament.tier = 'tier1'
                  AND COALESCE(
                      event_season.year,
                      EXTRACT(YEAR FROM match.match_date)::INTEGER
                  ) = %s
                """,
                (player_id, year),
            )
            player_stats = cursor.fetchone()

            cursor.execute(
                """
                SELECT t.team_id, t.canonical_name, rm.start_date, rm.end_date,
                       rm.status, rm.source, rm.source_url, rm.notes,
                       t.logo_url, t.logo_local_path
                FROM roster_memberships rm
                JOIN teams t ON t.team_id = rm.team_id
                WHERE rm.player_id = %s
                ORDER BY rm.start_date DESC NULLS LAST, rm.updated_at DESC
                LIMIT 10
                """,
                (player_id,),
            )
            roster_history = [
                {
                    "team_id": row[0],
                    "team": row[1],
                    "start_date": row[2],
                    "end_date": row[3],
                    "status": row[4],
                    "source": row[5],
                    "source_url": row[6],
                    "notes": row[7],
                    "image_url": row[8],
                    "image_local_path": row[9],
                }
                for row in cursor.fetchall()
            ]

            cursor.execute(
                """
                SELECT t.team_id, t.canonical_name, MIN(m.match_date), MAX(m.match_date),
                       COUNT(DISTINCT m.id), t.logo_url, t.logo_local_path,
                       ARRAY_AGG(DISTINCT EXTRACT(YEAR FROM m.match_date)::int
                                 ORDER BY EXTRACT(YEAR FROM m.match_date)::int)
                FROM match_players mp
                JOIN teams t ON t.team_id = mp.team_id
                JOIN matches m ON m.id = mp.match_id
                JOIN tournaments tournament ON tournament.id = m.tournament_id
                WHERE mp.player_id = %s
                  AND tournament.tier = 'tier1'
                  AND m.match_date IS NOT NULL
                GROUP BY t.team_id, t.canonical_name, t.logo_url, t.logo_local_path
                ORDER BY MAX(m.match_date) DESC NULLS LAST
                """,
                (player_id,),
            )
            observed_team_history = [
                {
                    "team_id": row[0],
                    "team": row[1],
                    "first_match": row[2],
                    "last_match": row[3],
                    "matches": row[4],
                    "image_url": row[5],
                    "image_local_path": row[6],
                    "years": row[7],
                }
                for row in cursor.fetchall()
            ]
            achievements = tournament_honors(cursor, player_id=player_id)

    current_rosters = [
        entry for entry in roster_history if entry["status"] == "current"
    ]
    current_team = current_rosters[0]["team"] if len(current_rosters) == 1 else None
    current_status = (
        "Current roster listing from VLR"
        if current_team
        else "Multiple current roster listings"
        if current_rosters
        else "No current roster source; showing match appearances"
    )
    global_power = next(
        (entry for entry in player_power_rankings(year) if entry["id"] == player_id),
        None,
    )

    return {
        "id": player[0],
        "name": player[1],
        "image_url": player[2],
        "image_local_path": player[3],
        "nationality": player[4],
        "year": year,
        **agent_profile(player_stats[10]),
        "achievements": achievements,
        "trophies": [event for event in achievements if event["rank"] == 1],
        "source_url": player[5],
        "stats": {
            "maps_played": player_stats[0],
            "kills": player_stats[1],
            "deaths": player_stats[2],
            "assists": player_stats[3],
            "rating": player_stats[4],
            "acs": player_stats[5],
            "kast": player_stats[6],
            "adr": player_stats[7],
            "headshot_percentage": player_stats[8],
            "first_kills": player_stats[9],
        },
        "global_power": global_power,
        "current_team": current_team,
        "current_team_logo_url": current_rosters[0]["image_url"] if current_team else None,
        "current_team_logo_local_path": current_rosters[0]["image_local_path"] if current_team else None,
        "current_status": current_status,
        "recent_maps": recent_maps,
        "roster_history": roster_history,
        "observed_team_history": observed_team_history,
    }


def team_details(team_id, year=2026):
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT team_id, canonical_name, logo_url, logo_local_path, source_url
                FROM teams WHERE team_id = %s
                """,
                (team_id,),
            )
            team = cursor.fetchone()
            if team is None:
                return None

            cursor.execute(
                """
                SELECT DISTINCT ON (m.id)
                       m.id, m.match_date, m.status, m.team1_id, m.team2_id,
                       m.team1_score, m.team2_score,
                       opponent.canonical_name, tournament.title, tournament.url,
                       opponent.logo_url, opponent.logo_local_path, tournament.logo_url, m.url,
                       ARRAY(SELECT g.map_name FROM games g WHERE g.match_id = m.id
                             AND g.map_name IS NOT NULL
                             AND g.team1_score IS NOT NULL AND g.team2_score IS NOT NULL
                             ORDER BY g.id)
                FROM matches m
                JOIN tournaments tournament ON tournament.id = m.tournament_id
                LEFT JOIN seasons event_season ON event_season.season_id = tournament.season_id
                LEFT JOIN teams opponent ON opponent.team_id =
                    CASE WHEN m.team1_id = %s THEN m.team2_id ELSE m.team1_id END
                WHERE tournament.tier = 'tier1'
                  AND lower(m.status) IN ('final', 'completed', 'complete')
                  AND COALESCE(event_season.year, EXTRACT(YEAR FROM m.match_date)::INTEGER) = %s
                  AND (m.team1_id = %s OR m.team2_id = %s)
                ORDER BY m.id, m.match_date DESC NULLS LAST
                """,
                (team_id, year, team_id, team_id),
            )
            match_rows = cursor.fetchall()

            cursor.execute(
                """
                SELECT DISTINCT ON (mp.player_id)
                       mp.player_id, p.canonical_name, p.image_url,
                       p.image_local_path, mp.first_seen_at
                FROM match_players mp
                JOIN players p ON p.player_id = mp.player_id
                JOIN matches m ON m.id = mp.match_id
                JOIN tournaments tournament ON tournament.id = m.tournament_id
                LEFT JOIN seasons event_season ON event_season.season_id = tournament.season_id
                WHERE mp.team_id = %s
                  AND tournament.tier = 'tier1'
                  AND COALESCE(event_season.year, EXTRACT(YEAR FROM m.match_date)::INTEGER) = %s
                ORDER BY mp.player_id, m.match_date DESC NULLS LAST
                """,
                (team_id, year),
            )
            observed_players = cursor.fetchall()

            cursor.execute(
                """
                SELECT stats.player_id, ARRAY_AGG(stats.agent)
                FROM player_stats stats
                JOIN games game ON game.id = stats.game_id
                JOIN matches match ON match.id = game.match_id
                JOIN tournaments event ON event.id = match.tournament_id
                LEFT JOIN seasons event_season ON event_season.season_id = event.season_id
                WHERE stats.team_id = %s AND event.tier = 'tier1'
                  AND stats.agent IS NOT NULL
                  AND COALESCE(event_season.year, EXTRACT(YEAR FROM match.match_date)::INTEGER) = %s
                GROUP BY stats.player_id
                """,
                (team_id, year),
            )
            observed_roles = {
                player_id: agent_profile(agents)["role"] for player_id, agents in cursor.fetchall()
            }

            cursor.execute(
                """
                SELECT DISTINCT ON (rm.player_id)
                       rm.player_id, player.canonical_name, player.image_url,
                       player.image_local_path, rm.notes, rm.source_url
                FROM roster_memberships rm
                JOIN players player ON player.player_id = rm.player_id
                WHERE rm.team_id = %s AND rm.status = 'current'
                ORDER BY rm.player_id, rm.updated_at DESC
                """,
                (team_id,),
            )
            current_roster = cursor.fetchall()

            cursor.execute(
                """
                SELECT tournament.id, tournament.title, tournament.url,
                       tournament.prize_pool, result.placement_text, result.prize,
                       COUNT(DISTINCT match.id) AS matches_played,
                       COUNT(DISTINCT match.id) FILTER (
                           WHERE (match.team1_id = %s AND match.team1_score > match.team2_score)
                              OR (match.team2_id = %s AND match.team2_score > match.team1_score)
                       ) AS matches_won,
                       COUNT(DISTINCT match.id) FILTER (
                           WHERE (match.team1_score = match.team2_score)
                       ) AS matches_drawn,
                       tournament.end_date, tournament.logo_url, tournament.region
                FROM tournaments tournament
                JOIN matches match ON match.tournament_id = tournament.id
                LEFT JOIN seasons event_season ON event_season.season_id = tournament.season_id
                LEFT JOIN team_event_results result
                  ON result.tournament_id = tournament.id AND result.team_id = %s
                WHERE tournament.tier = 'tier1'
                  AND (match.team1_id = %s OR match.team2_id = %s)
                  AND COALESCE(
                      event_season.year,
                      EXTRACT(YEAR FROM match.match_date)::INTEGER
                  ) = %s
                GROUP BY tournament.id, tournament.title, tournament.url,
                         tournament.prize_pool, result.placement_text, result.prize
                ORDER BY tournament.end_date DESC NULLS LAST, tournament.title
                """,
                (team_id, team_id, team_id, team_id, team_id, year),
            )
            tournaments = [
                {
                    "id": row[0],
                    "title": row[1],
                    "url": row[2],
                    "prize_pool": row[3],
                    "placement": row[4] if placement_rank(row[4]) is not None else None,
                    "prize": row[5],
                    "matches_played": row[6],
                    "matches_won": row[7],
                    "matches_drawn": row[8],
                    "end_date": row[9],
                    "logo_url": row[10],
                    "region": row[11],
                }
                for row in cursor.fetchall()
            ]
            trophies = tournament_honors(cursor, team_id=team_id)

    match_rows.sort(key=lambda row: str(row[1] or ""), reverse=True)
    recent_matches = []
    for row in match_rows[:10]:
        team1_score, team2_score = row[5], row[6]
        score, opponent_score = (team1_score, team2_score) if row[3] == team_id else (team2_score, team1_score)
        won = None
        if score is not None and opponent_score is not None:
            won = score > opponent_score
        recent_matches.append(
            {
                "id": row[0],
                "date": row[1],
                "status": row[2],
                "opponent": row[7],
                "team1_score": team1_score,
                "team2_score": team2_score,
                "won": won,
                "event": row[8],
                "event_url": row[9],
                "opponent_logo_url": row[10],
                "opponent_logo_local_path": row[11],
                "event_logo_url": row[12],
                "match_url": row[13],
                "team_score": score,
                "opponent_score": opponent_score,
                "maps": row[14],
            }
        )

    ranked_team = None
    if year == 2026:
        ranked_team = next(
            (team for team in team_power_rankings() if team["id"] == team_id),
            None,
        )
    return {
        "id": team[0],
        "name": team[1],
        "image_url": team[2],
        "image_local_path": team[3],
        "source_url": team[4],
        "region": ranked_team.get("region") if ranked_team else None,
        "stats": ranked_team,
        "year": year,
        "tournaments": tournaments,
        "trophies": trophies,
        "current_roster": [
            {
                "id": row[0],
                "name": row[1],
                "image_url": row[2],
                "image_local_path": row[3],
                "role": observed_roles.get(row[0]) if not row[4] or row[4].lower() == "player" else row[4],
                "source_url": row[5],
            }
            for row in current_roster
        ],
        "observed_players": [
            {
                "id": row[0],
                "name": row[1],
                "image_url": row[2],
                "image_local_path": row[3],
                "last_seen": row[4],
                "role": observed_roles.get(row[0]),
            }
            for row in observed_players
        ],
        "recent_matches": recent_matches,
    }


def season_achievements(cursor, year):
    cursor.execute(
        f"""
        WITH events AS (
            SELECT t.id, t.title, t.logo_url, t.region, t.status, CASE
                WHEN t.title ILIKE 'Valorant Champions 20%%' THEN 'champions'
                WHEN {masters_event("t.title", year)} THEN 'masters'
                ELSE 'regional'
            END AS kind
            FROM tournaments t JOIN seasons s USING (season_id)
            WHERE t.tier = 'tier1' AND s.year = %s
        ),
        participants AS (
            SELECT m.tournament_id, team.id AS team_id
            FROM matches m JOIN events e ON e.id = m.tournament_id
            CROSS JOIN LATERAL (VALUES (m.team1_id), (m.team2_id)) team(id)
            WHERE team.id IS NOT NULL
              AND lower(m.status) IN ('final', 'completed', 'complete')
              AND {ranking_match('m', 'e.title', year)}
            UNION
            SELECT r.tournament_id, r.team_id
            FROM team_event_results r JOIN events e ON e.id = r.tournament_id
            JOIN teams t ON t.team_id = r.team_id
            WHERE (r.prize IS NOT NULL OR r.placement_text IS NOT NULL)
              -- FPX received compensation after withdrawing from Reykjavík.
              AND NOT (r.tournament_id = '926' AND t.canonical_name = 'funplus phoenix')
        ),
        regional_finals AS (
            SELECT m.tournament_id, MAX(m.team1_id) AS team1_id,
                   MAX(m.team2_id) AS team2_id, MAX(m.team1_score) AS score1,
                   MAX(m.team2_score) AS score2
            FROM matches m JOIN events e ON e.id = m.tournament_id
            WHERE e.kind = 'regional' AND m.url ~* '-(gf|grand-final)/?$'
              AND lower(m.status) IN ('final', 'completed', 'complete')
              AND m.team1_id IS NOT NULL AND m.team2_id IS NOT NULL
              AND m.team1_score <> m.team2_score
              AND {ranking_match('m', 'e.title', year) if year == 2021 else 'TRUE'}
            GROUP BY m.tournament_id
            HAVING COUNT(*) = 1
        )
        SELECT e.id, e.kind, p.team_id, COALESCE(r.placement_text, CASE
            WHEN p.team_id = f.team1_id THEN CASE WHEN f.score1 > f.score2 THEN '1st' ELSE '2nd' END
            WHEN p.team_id = f.team2_id THEN CASE WHEN f.score2 > f.score1 THEN '1st' ELSE '2nd' END
        END), e.title, e.logo_url, e.region, e.status
        FROM events e LEFT JOIN participants p ON p.tournament_id = e.id
        LEFT JOIN team_event_results r
          ON r.tournament_id = e.id AND r.team_id = p.team_id
        LEFT JOIN regional_finals f ON f.tournament_id = e.id
        """,
        (year,),
    )
    rows = cursor.fetchall()
    international_events = {
        event_id: kind for event_id, kind, *_ in rows if kind != "regional"
    }
    international_max = sum(PLACEMENT_POINTS[kind][0] for kind in international_events.values())
    completed_fields = {}
    for event_id, kind, team_id, placement, title, _, _, status in rows:
        if (kind != "regional" or "lock//in" in title.lower()) and status == "completed" and team_id is not None:
            completed_fields.setdefault(event_id, {})[team_id] = placement_rank(placement)
    placement_bands = {}
    for event_id, field in completed_fields.items():
        ranked = sorted(rank for rank in field.values() if rank is not None)
        # Infer the unplaced band only when the published standings fill every slot
        # through the last verified finish, including tied finishes.
        if not ranked or len(ranked) == len(field) or any(
            rank != ranked.count(rank) + sum(other < rank for other in ranked)
            for rank in set(ranked)
        ):
            continue
        kind = international_events.get(event_id)
        expected_size = 16 if kind == "champions" else {"1188": 32, "1921": 8, "2281": 8}.get(event_id, 12)
        if len(field) == expected_size:
            placement_bands[event_id] = [len(ranked) + 1, expected_size]
    results = {}
    for event_id, kind, team_id, placement, title, logo_url, region, _ in rows:
        if team_id is None or (
            kind == "regional" and placement_rank(placement) is None
            and "lock//in" not in title.lower()
        ):
            continue
        results.setdefault(team_id, []).append({
            "event_id": event_id, "kind": kind, "placement": placement,
            "points": achievement_points(kind, placement),
            "title": title, "logo_url": logo_url, "region": region,
            "placement_band": placement_bands.get(event_id) if placement_rank(placement) is None else None,
        })
    return {
        team_id: {
            "international_achievement": (
                sum(row["points"] for row in events if row["kind"] != "regional")
                / international_max if international_max else 0
            ),
            "regional_achievement": sum(sorted(
                (row["points"] for row in events if row["kind"] == "regional"),
                reverse=True,
            )[:3]) / 30,
            "achievement_events": sorted(events, key=lambda row: row["event_id"]),
        }
        for team_id, events in results.items()
    }


def team_power_rankings(year=2026):
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                WITH eligible_matches AS (
                    SELECT m.id, m.team1_id, m.team2_id,
                           m.team1_score, m.team2_score, m.match_date,
                           tournament.region,
                           CASE
                               WHEN tournament.title ILIKE 'Valorant Champions 20%%' THEN {CHAMPIONS_EVENT_WEIGHT}
                               WHEN {masters_event("tournament.title", year)} THEN {MASTERS_EVENT_WEIGHT}
                               ELSE {REGIONAL_EVENT_WEIGHT}
                           END AS event_weight
                    FROM matches m
                    JOIN tournaments tournament ON tournament.id = m.tournament_id
                    LEFT JOIN seasons event_season ON event_season.season_id = tournament.season_id
                    WHERE tournament.tier = 'tier1'
                      AND {ranking_match('m', 'tournament.title', year)}
                      AND COALESCE(event_season.year, EXTRACT(YEAR FROM m.match_date)::INTEGER) = %s
                      AND m.match_date >= make_date(%s, 1, 1)
                      AND m.match_date < make_date(%s, 1, 1)
                      AND lower(COALESCE(m.status, '')) IN ('final', 'completed', 'complete')
                      AND m.team1_id IS NOT NULL
                      AND m.team2_id IS NOT NULL
                      AND m.team1_score IS NOT NULL
                      AND m.team2_score IS NOT NULL
                ),
                team_region_candidates AS (
                    SELECT team1_id AS team_id, region
                    FROM eligible_matches
                    WHERE region IS NOT NULL
                      AND (
                          region ILIKE '%%america%%'
                          OR region IN ('Brazil', 'LATAM')
                          OR region ILIKE '%%emea%%'
                          OR region ILIKE '%%europe%%'
                          OR region ILIKE '%%africa%%'
                          OR region ILIKE '%%middle east%%'
                          OR region ILIKE '%%pacific%%'
                          OR region ILIKE '%%asia%%'
                          OR region ILIKE '%%china%%'
                      )
                    UNION ALL
                    SELECT team2_id AS team_id, region
                    FROM eligible_matches
                    WHERE region IS NOT NULL
                      AND (
                          region ILIKE '%%america%%'
                          OR region IN ('Brazil', 'LATAM')
                          OR region ILIKE '%%emea%%'
                          OR region ILIKE '%%europe%%'
                          OR region ILIKE '%%africa%%'
                          OR region ILIKE '%%middle east%%'
                          OR region ILIKE '%%pacific%%'
                          OR region ILIKE '%%asia%%'
                          OR region ILIKE '%%china%%'
                      )
                ),
                team_regions AS (
                    SELECT team_id, region
                    FROM (
                        SELECT team_id, region,
                               ROW_NUMBER() OVER (
                                   PARTITION BY team_id
                                   ORDER BY COUNT(*) DESC, region
                               ) AS region_rank
                        FROM team_region_candidates
                        GROUP BY team_id, region
                    ) ranked_regions
                    WHERE region_rank = 1
                ),
                team_match_rows AS (
                    SELECT id AS match_id, match_date, event_weight,
                           team1_id AS team_id, team2_id AS opponent_id,
                           CASE WHEN team1_score = team2_score THEN 0.5
                                WHEN team1_score > team2_score THEN 1.0
                                ELSE 0.0 END AS result
                    FROM eligible_matches
                    UNION ALL
                    SELECT id AS match_id, match_date, event_weight,
                           team2_id AS team_id, team1_id AS opponent_id,
                           CASE WHEN team1_score = team2_score THEN 0.5
                                WHEN team2_score > team1_score THEN 1.0
                                ELSE 0.0 END AS result
                    FROM eligible_matches
                ),
                match_totals AS (
                    SELECT team_id, COUNT(*) AS matches_played,
                           SUM(event_weight) AS weighted_matches_played,
                           COUNT(*) FILTER (WHERE result = 1.0) AS matches_won,
                           COUNT(*) FILTER (WHERE result = 0.5) AS matches_drawn,
                           SUM(result * event_weight) AS weighted_match_points,
                           SUM(result * event_weight) / SUM(event_weight) AS match_win_rate
                    FROM team_match_rows
                    GROUP BY team_id
                ),
                recent_match_rows AS (
                    SELECT team_id, result, event_weight,
                           ROW_NUMBER() OVER (
                               PARTITION BY team_id
                               ORDER BY match_date DESC, match_id DESC
                           ) AS recency_rank
                    FROM team_match_rows
                ),
                recent_totals AS (
                    SELECT team_id,
                           SUM(result * (6 - recency_rank) * event_weight)
                               / SUM((6 - recency_rank) * event_weight)
                               AS recent_performance_rate
                    FROM recent_match_rows
                    WHERE recency_rank <= 5
                    GROUP BY team_id
                ),
                opponent_totals AS (
                    SELECT results.team_id,
                           SUM(COALESCE(opponents.match_win_rate, 0.5) * results.event_weight)
                               / SUM(results.event_weight)
                               AS opponent_strength_rate
                    FROM team_match_rows results
                    LEFT JOIN match_totals opponents
                      ON opponents.team_id = results.opponent_id
                    GROUP BY results.team_id
                ),
                team_map_rows AS (
                    SELECT m.team1_id AS team_id,
                           CASE WHEN g.team1_score = g.team2_score THEN 0.5
                                WHEN g.team1_score > g.team2_score THEN 1.0
                                ELSE 0.0 END AS result,
                           g.team1_score AS rounds_for,
                           g.team2_score AS rounds_against,
                           m.event_weight
                    FROM eligible_matches m
                    JOIN games g ON g.match_id = m.id
                    WHERE g.team1_score IS NOT NULL AND g.team2_score IS NOT NULL
                    UNION ALL
                    SELECT m.team2_id AS team_id,
                           CASE WHEN g.team1_score = g.team2_score THEN 0.5
                                WHEN g.team2_score > g.team1_score THEN 1.0
                                ELSE 0.0 END AS result,
                           g.team2_score AS rounds_for,
                           g.team1_score AS rounds_against,
                           m.event_weight
                    FROM eligible_matches m
                    JOIN games g ON g.match_id = m.id
                    WHERE g.team1_score IS NOT NULL AND g.team2_score IS NOT NULL
                ),
                map_totals AS (
                    SELECT team_id, COUNT(*) AS maps_played,
                           SUM(event_weight) AS weighted_maps_played,
                           COUNT(*) FILTER (WHERE result = 1.0) AS maps_won,
                           COUNT(*) FILTER (WHERE result = 0.5) AS maps_drawn,
                           SUM(result * event_weight) AS weighted_map_points,
                           SUM(rounds_for) AS rounds_for,
                           SUM(rounds_against) AS rounds_against,
                           SUM(rounds_for * event_weight) AS weighted_rounds_for,
                           SUM(rounds_against * event_weight) AS weighted_rounds_against
                    FROM team_map_rows
                    GROUP BY team_id
                ),
                execution_totals AS (
                    SELECT stats.team_id,
                           SUM(stats.kills) AS kills,
                           SUM(stats.deaths) AS deaths,
                           SUM(stats.kills * eligible.event_weight) AS weighted_kills,
                           SUM(stats.deaths * eligible.event_weight) AS weighted_deaths
                    FROM player_stats stats
                    JOIN games game ON game.id = stats.game_id
                    JOIN eligible_matches eligible ON eligible.id = game.match_id
                    WHERE stats.team_id IS NOT NULL
                    GROUP BY stats.team_id
                )
                SELECT team.team_id, team.canonical_name, team.logo_url,
                       team.logo_local_path, team.source_url,
                       match_totals.matches_played, match_totals.matches_won,
                       match_totals.matches_drawn,
                       COALESCE(map_totals.maps_played, 0),
                       COALESCE(map_totals.maps_won, 0),
                       COALESCE(map_totals.maps_drawn, 0),
                       COALESCE(map_totals.rounds_for, 0),
                       COALESCE(map_totals.rounds_against, 0),
                       match_totals.weighted_matches_played,
                       match_totals.weighted_match_points,
                       COALESCE(map_totals.weighted_maps_played, 0),
                       COALESCE(map_totals.weighted_map_points, 0),
                       COALESCE(map_totals.weighted_rounds_for, 0),
                       COALESCE(map_totals.weighted_rounds_against, 0),
                       COALESCE(recent_totals.recent_performance_rate, 0.5),
                       COALESCE(opponent_totals.opponent_strength_rate, 0.5),
                       COALESCE(execution_totals.kills, 0),
                       COALESCE(execution_totals.deaths, 0),
                       COALESCE(execution_totals.weighted_kills, 0),
                       COALESCE(execution_totals.weighted_deaths, 0),
                       team_regions.region
                FROM match_totals
                JOIN teams team ON team.team_id = match_totals.team_id
                LEFT JOIN team_regions ON team_regions.team_id = team.team_id
                LEFT JOIN map_totals ON map_totals.team_id = team.team_id
                LEFT JOIN recent_totals ON recent_totals.team_id = team.team_id
                LEFT JOIN opponent_totals ON opponent_totals.team_id = team.team_id
                LEFT JOIN execution_totals ON execution_totals.team_id = team.team_id
                """,
                (year, year, year + 1),
            )
            teams = [
                {
                    "id": row[0],
                    "name": row[1],
                    "image_url": row[2],
                    "image_local_path": row[3],
                    "source_url": row[4],
                    "matches_played": row[5],
                    "matches_won": row[6],
                    "matches_drawn": row[7],
                    "maps_played": row[8],
                    "maps_won": row[9],
                    "maps_drawn": row[10],
                    "rounds_for": row[11],
                    "rounds_against": row[12],
                    "weighted_matches_played": row[13],
                    "weighted_match_points": row[14],
                    "weighted_maps_played": row[15],
                    "weighted_map_points": row[16],
                    "weighted_rounds_for": row[17],
                    "weighted_rounds_against": row[18],
                    "recent_performance_rate": row[19],
                    "opponent_strength_rate": row[20],
                    "kills": row[21],
                    "deaths": row[22],
                    "weighted_kills": row[23],
                    "weighted_deaths": row[24],
                    "region": row[25],
                }
                for row in cursor.fetchall()
            ]
            achievements = season_achievements(cursor, year)
            for team in teams:
                team.update(achievements.get(team["id"], {}))
    return calculate_team_power(teams)


def player_power_rankings(year=2026):
    return player_power_by_season((year,))[year]


def player_power_by_season(years):
    match_year = "COALESCE(event_season.year, EXTRACT(YEAR FROM match.match_date)::INTEGER)"
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                WITH season_matches AS MATERIALIZED (
                    SELECT match.id, match.match_date, tournament.id AS event_id, {match_year} AS year,
                           CASE WHEN {match_year} = 2021
                                THEN ({ranking_match('match', 'tournament.title', 2021)})
                                ELSE ({ranking_match('match', 'tournament.title', 2026)}) END AS is_ranked,
                           lower(match.status) IN ('final', 'completed', 'complete') AS is_finished,
                           CASE
                               WHEN tournament.title ILIKE 'Valorant Champions 20%%' THEN 'champions'
                               WHEN CASE WHEN {match_year} = 2021 THEN ({masters_event("tournament.title", 2021)})
                                    ELSE ({masters_event("tournament.title", 2026)}) END THEN 'masters'
                               ELSE 'regional'
                           END AS event_kind,
                           match.url ~* '-(gf|[ulm]bf|ub[qs]f|[ulm]r[0-9]+|playoffs|grand-final)/?$' AS bracket_match
                    FROM matches match
                    JOIN tournaments tournament ON tournament.id = match.tournament_id
                    LEFT JOIN seasons event_season ON event_season.season_id = tournament.season_id
                    WHERE tournament.tier = 'tier1'
                      AND {match_year} = ANY(%s)
                      AND match.match_date >= make_date(%s, 1, 1)
                      AND match.match_date < make_date(%s, 1, 1)
                      AND EXTRACT(YEAR FROM match.match_date)::INTEGER = {match_year}
                ),
                eligible_matches AS (
                    SELECT id, event_id, event_kind, year,
                           CASE event_kind
                               WHEN 'champions' THEN CASE WHEN bracket_match THEN {PLAYER_EVENT_WEIGHTS['champions'][1]} ELSE {PLAYER_EVENT_WEIGHTS['champions'][0]} END
                               WHEN 'masters' THEN CASE WHEN bracket_match THEN {PLAYER_EVENT_WEIGHTS['masters'][1]} ELSE {PLAYER_EVENT_WEIGHTS['masters'][0]} END
                               ELSE CASE WHEN bracket_match THEN {PLAYER_EVENT_WEIGHTS['regional'][1]} ELSE {PLAYER_EVENT_WEIGHTS['regional'][0]} END
                           END AS event_weight
                    FROM season_matches
                    WHERE is_ranked AND is_finished
                ),
                player_maps AS MATERIALIZED (
                    SELECT stats.player_id, stats.team_id, game.id AS map_id,
                           eligible.event_id, eligible.event_kind, eligible.event_weight, eligible.year,
                           stats.rating, stats.acs, stats.kast_percentage, stats.adr,
                           stats.kills, stats.deaths, stats.headshot_percentage, stats.agent
                    FROM eligible_matches eligible
                    JOIN games game ON game.match_id = eligible.id
                    JOIN player_stats stats ON stats.game_id = game.id
                    WHERE stats.player_id IS NOT NULL
                ),
                event_maps AS (
                    SELECT year, player_id, team_id, event_id, COUNT(DISTINCT map_id) AS maps
                    FROM player_maps
                    WHERE team_id IS NOT NULL
                    GROUP BY year, player_id, team_id, event_id
                ),
                event_appearances AS (
                    SELECT year, player_id, JSON_AGG(JSON_BUILD_ARRAY(team_id, event_id, maps)) AS events
                    FROM event_maps
                    GROUP BY year, player_id
                ),
                player_totals AS (
                    SELECT stats.year, stats.player_id,
                           COUNT(DISTINCT map_id) AS maps_played,
                           SUM(stats.rating * stats.event_weight)
                               / NULLIF(
                                   SUM(stats.event_weight)
                                       FILTER (WHERE stats.rating IS NOT NULL),
                                   0
                               ) AS rating,
                           SUM(stats.acs * stats.event_weight)
                               / NULLIF(
                                   SUM(stats.event_weight)
                                       FILTER (WHERE stats.acs IS NOT NULL),
                                   0
                               ) AS acs,
                           SUM(stats.kast_percentage * stats.event_weight)
                               / NULLIF(
                                   SUM(stats.event_weight)
                                       FILTER (WHERE stats.kast_percentage IS NOT NULL),
                                   0
                               ) AS kast,
                           SUM(stats.adr * stats.event_weight)
                               / NULLIF(
                                   SUM(stats.event_weight)
                                       FILTER (WHERE stats.adr IS NOT NULL),
                                   0
                               ) AS adr,
                           SUM(COALESCE(stats.kills, 0) * stats.event_weight) AS kills,
                           SUM(COALESCE(stats.deaths, 0) * stats.event_weight) AS deaths,
                           COUNT(DISTINCT map_id) FILTER (WHERE event_kind <> 'regional') AS international_maps,
                           AVG(stats.rating) FILTER (WHERE event_kind <> 'regional') AS international_rating,
                           COUNT(DISTINCT map_id) FILTER (
                               WHERE event_kind <> 'regional' AND stats.rating IS NOT NULL
                           ) AS international_rated_maps,
                           SUM(stats.rating * stats.event_weight) FILTER (WHERE event_kind <> 'regional')
                               / NULLIF(SUM(stats.event_weight) FILTER (
                                   WHERE event_kind <> 'regional' AND stats.rating IS NOT NULL
                               ), 0) AS weighted_international_rating,
                           AVG(stats.headshot_percentage) AS headshot_percentage,
                           SUM(stats.kills) AS raw_kills, SUM(stats.deaths) AS raw_deaths,
                           ARRAY_AGG(stats.agent) AS agent_picks
                    FROM player_maps stats
                    GROUP BY stats.year, stats.player_id
                    HAVING COUNT(DISTINCT map_id) >= 5
                ),
                observed_teams AS (
                    SELECT DISTINCT ON (match.year, appearance.player_id)
                           match.year, appearance.player_id, appearance.team_id
                    FROM season_matches match
                    JOIN match_players appearance ON appearance.match_id = match.id
                    WHERE appearance.team_id IS NOT NULL
                      AND (match.year <> 2021 OR match.is_ranked)
                    ORDER BY match.year, appearance.player_id, match.match_date DESC NULLS LAST
                )
                SELECT player.player_id, player.canonical_name, player.image_url,
                       player.image_local_path, player.nationality, player.source_url,
                       totals.maps_played, totals.rating, totals.acs, totals.kast,
                       totals.adr, totals.kills, totals.deaths,
                       COALESCE(roster_team.canonical_name, observed_team.canonical_name),
                       totals.international_maps, totals.international_rating,
                       totals.headshot_percentage, totals.raw_kills, totals.raw_deaths, totals.agent_picks,
                       CASE WHEN roster_team.canonical_name IS NOT NULL THEN roster_team.logo_url
                            ELSE observed_team.logo_url END,
                       CASE WHEN roster_team.canonical_name IS NOT NULL THEN roster_team.logo_local_path
                            ELSE observed_team.logo_local_path END,
                       COALESCE(roster_team.team_id, observed_team.team_id),
                       totals.international_rated_maps, totals.weighted_international_rating, appearances.events,
                       totals.year
                FROM player_totals totals
                JOIN players player ON player.player_id = totals.player_id
                LEFT JOIN event_appearances appearances
                  ON appearances.player_id = totals.player_id AND appearances.year = totals.year
                LEFT JOIN LATERAL (
                    SELECT team.canonical_name, team.logo_url, team.logo_local_path, team.team_id
                    FROM roster_memberships membership
                    JOIN teams team ON team.team_id = membership.team_id
                    WHERE membership.player_id = player.player_id
                      AND membership.status = 'current' AND totals.year = 2026
                    ORDER BY membership.updated_at DESC
                    LIMIT 1
                ) roster_team ON TRUE
                LEFT JOIN observed_teams observed
                  ON observed.player_id = player.player_id AND observed.year = totals.year
                LEFT JOIN teams observed_team ON observed_team.team_id = observed.team_id
                """,
                (list(years), min(years), max(years) + 1),
            )
            rows = cursor.fetchall()
            placements = {
                (team_id, event["event_id"]): event
                for year in years
                for team_id, achievement in season_achievements(cursor, year).items()
                for event in achievement["achievement_events"]
                if (placement_rank(event["placement"]) or 0) > 0
            }
            players = {year: [] for year in years}
            for row in rows:
                players[row[26]].append({
                    "id": row[0],
                    "name": row[1],
                    "image_url": row[2],
                    "image_local_path": row[3],
                    "nationality": row[4],
                    "source_url": row[5],
                    "maps_played": row[6],
                    "rating": row[7],
                    "acs": row[8],
                    "kast": row[9],
                    "adr": row[10],
                    "kills": row[11],
                    "deaths": row[12],
                    "international_maps": row[14],
                    "international_rating": row[15],
                    "headshot_percentage": row[16],
                    "kd": float(row[17] / row[18]) if row[17] is not None and row[18] else None,
                    **agent_profile(row[19]),
                    "team": row[13],
                    "team_logo_url": row[20],
                    "team_logo_local_path": row[21],
                    "team_id": row[22],
                    "international_rated_maps": row[23],
                    "weighted_international_rating": row[24],
                    "tournament_finishes": [
                        {
                            "event_id": event_id, "kind": finish["kind"], "title": finish["title"],
                            "placement": finish["placement"], "points": finish["points"], "maps": maps,
                        }
                        for team_id, event_id, maps in (row[25] or [])
                        if (finish := placements.get((team_id, event_id))) is not None
                    ],
                })
    return {year: calculate_player_power(entries) for year, entries in players.items()}


def events_for_season(year):
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT tournament.id, tournament.title, tournament.status,
                       tournament.url, tournament.region,
                       tournament.start_date, tournament.end_date,
                       (SELECT COUNT(*) FROM matches WHERE tournament_id = tournament.id),
                       tournament.logo_url
                FROM tournaments tournament
                LEFT JOIN seasons season ON season.season_id = tournament.season_id
                WHERE tournament.tier = 'tier1' AND season.year = %s
                ORDER BY tournament.start_date NULLS LAST, tournament.title
                """,
                (year,),
            )
            return [
                {
                    "id": row[0],
                    "title": row[1],
                    "status": row[2],
                    "url": row[3],
                    "region": row[4],
                    "start_date": row[5],
                    "end_date": row[6],
                    "matches_imported": row[7],
                    "logo_url": row[8],
                }
                for row in cursor.fetchall()
            ]


def regional_strength(teams, international_events):
    region_aliases = {
        "Americas": "americas", "North America": "americas", "South America": "americas",
        "Brazil": "americas", "LATAM": "americas", "EMEA": "emea", "Europe": "emea",
        "Pacific": "pacific", "Asia-Pacific": "pacific", "China": "china",
    }
    affiliations = {team["id"]: region_aliases.get(team["region"]) for team in teams}
    totals = {}
    with connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT team1_id, team2_id, team1_score, team2_score, tournament_id
            FROM matches m
            WHERE tournament_id = ANY(%s)
              AND {competitive_match('m')}
              AND lower(status) IN ('final', 'completed', 'complete')
              AND team1_score IS NOT NULL AND team2_score IS NOT NULL
            """,
            ([event["id"] for event in international_events],),
        )
        champions = {event["id"] for event in international_events
                     if event["title"].lower().startswith("valorant champions 20")}
        for team1, team2, score1, score2, event_id in cursor.fetchall():
            first, second = affiliations.get(team1), affiliations.get(team2)
            if not first or not second or first == second:
                continue
            weight = CHAMPIONS_EVENT_WEIGHT if event_id in champions else MASTERS_EVENT_WEIGHT
            result = 0.5 if score1 == score2 else float(score1 > score2)
            for region, points in ((first, result), (second, 1 - result)):
                total = totals.setdefault(region, {"points": 0, "weight": 0, "matches": 0})
                total["points"] += weight * points
                total["weight"] += weight
                total["matches"] += 1
    return {
        region: {"score": round(100 * total["points"] / total["weight"], 1), "matches": total["matches"]}
        for region, total in totals.items()
    }


def upcoming_matches(year):
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT m.id, m.match_date, m.status, first_team.canonical_name,
                       second_team.canonical_name, tournament.title
                FROM matches m
                JOIN tournaments tournament ON tournament.id = m.tournament_id
                LEFT JOIN seasons season ON season.season_id = tournament.season_id
                LEFT JOIN teams first_team ON first_team.team_id = m.team1_id
                LEFT JOIN teams second_team ON second_team.team_id = m.team2_id
                WHERE tournament.tier = 'tier1'
                  AND season.year = %s
                  AND lower(COALESCE(m.status, '')) NOT IN ('final', 'completed', 'complete')
                ORDER BY m.match_date NULLS LAST, m.id
                LIMIT 100
                """,
                (year,),
            )
            return [
                {
                    "id": row[0],
                    "date": row[1],
                    "status": row[2],
                    "team1": row[3],
                    "team2": row[4],
                    "event": row[5],
                }
                for row in cursor.fetchall()
            ]


RESPONSE_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Content-Security-Policy": (
        "default-src 'self'; img-src 'self' https://vlr.gg https://www.vlr.gg "
        "https://owcdn.net data:; style-src 'self' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; script-src 'self'; "
        "connect-src 'self'; media-src 'self' https://cmsassets.rgpub.io; "
        "object-src 'none'; base-uri 'none'"
    ),
}


def json_response(status, payload):
    return status, json.dumps(payload, default=str).encode("utf-8"), "application/json; charset=utf-8"


def static_response(relative_path, base_directory=STATIC_DIR):
    path = (base_directory / relative_path).resolve()
    if not path.is_relative_to(base_directory.resolve()) or not path.is_file():
        return json_response(404, {"error": "Not found."})
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return 200, path.read_bytes(), content_type


def get_response(path, query):
    try:
        if path == "/":
            return static_response("index.html")
        elif path in {"/app.css", "/app.js", "/simulator.css", "/simulator-engine.js", "/simulator.js",
                      "/favicon.svg", "/champions-mark.svg"} or path.startswith("/assets/"):
            return static_response(path.lstrip("/"))
        elif path.startswith("/vct-images/"):
            image_path = path.removeprefix("/vct-images/")
            if Path(image_path).suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
                return json_response(404, {"error": "Not found."})
            else:
                return static_response(image_path, VCT_IMAGE_DIR)
        elif path == "/api/health":
            with connect() as connection:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT 1")
            return json_response(200, {"status": "ok", "database": "connected"})
        elif path == "/api/simulator":
            power = {
                (year, player["id"]): player["power_score"]
                for year, players in player_power_by_season(range(2021, 2027)).items()
                for player in players
            }
            return json_response(200, simulator_catalog(ranking_match("m", "t.title", 2021), power))
        elif path == "/api/events":
            year = int(query.get("year", ["2026"])[0])
            if not 2021 <= year <= 2026:
                raise ValueError("Choose a season from 2021 to 2026.")
            return json_response(200, {"year": year, "events": events_for_season(year)})
        elif path == "/api/search":
            entity_type = query.get("type", ["all"])[0]
            limit = min(50, max(1, int(query.get("limit", ["20"])[0])))
            return json_response(
                200,
                {
                    "results": search_entities(
                        query.get("q", [""])[0], entity_type, limit,
                        int(query.get("year", ["2026"])[0]),
                    )
                },
            )
        elif path == "/api/power-rankings":
            year = int(query.get("year", ["2026"])[0])
            if not 2021 <= year <= 2026:
                raise ValueError("Choose a season from 2021 to 2026.")
            teams = team_power_rankings(year)
            international_events = [
                event for event in events_for_season(year)
                if (
                    ("masters" in event["title"].lower()
                     and (year != 2021 or not re.search(r"stage 1:\s*masters", event["title"], re.I)))
                    or "lock//in" in event["title"].lower()
                    or event["title"].lower().startswith("valorant champions 20")
                )
            ]
            return json_response(
                200,
                {
                    "year": year,
                    "teams": teams,
                    "international_events": international_events,
                    "regional_strength": regional_strength(teams, international_events),
                    "formula": {
                        **TEAM_POWER_WEIGHTS,
                        "placement_points": PLACEMENT_POINTS,
                        "recent_matches": 5,
                        "regional_strength_included": False,
                        "execution_weights": {
                            "map_win_rate": 0.4,
                            "round_strength": 0.4,
                            "kd_strength": 0.2,
                        },
                        "event_weights": {
                            "champions": CHAMPIONS_EVENT_WEIGHT,
                            "masters": MASTERS_EVENT_WEIGHT,
                            "regional": REGIONAL_EVENT_WEIGHT,
                        },
                        "score_scaling": (
                            "The displayed score is the sum of earned component points out of 100."
                        ),
                        "event_classification": (
                            "Tournament title containing Champions or Masters; "
                            "otherwise regional."
                        ),
                    },
                },
            )
        elif path == "/api/player-power-rankings":
            year = int(query.get("year", ["2026"])[0])
            if not 2021 <= year <= 2026:
                raise ValueError("Choose a season from 2021 to 2026.")
            return json_response(
                200,
                {
                    "year": year,
                    "players": player_power_rankings(year),
                    "formula": {
                        **{metric: weight for metric, (weight, _) in PLAYER_METRIC_WEIGHTS.items()},
                        "component_points": PLAYER_POWER_POINTS,
                        "minimum_maps": 5,
                        "score_scaling": "Players earn up to 100 points across four components.",
                        "event_weights": {
                            kind: {"base": weights[0], "bracket": weights[1]}
                            for kind, weights in PLAYER_EVENT_WEIGHTS.items()
                        },
                        "sample_prior_maps": PLAYER_SAMPLE_PRIOR_MAPS,
                        "season_maps_full_credit": PLAYER_VOLUME_CAP,
                        "international_prior_maps": PLAYER_INTERNATIONAL_PRIOR_MAPS,
                        "international_rating_ceiling": PLAYER_INTERNATIONAL_RATING_CEILING,
                        "event_win_points": PLAYER_EVENT_WIN_POINTS,
                        "event_full_credit_maps": PLAYER_EVENT_FULL_CREDIT_MAPS,
                        "counted_event_finishes": PLAYER_FINISHES_COUNT,
                    },
                },
            )
        elif path == "/api/2027":
            events = events_for_season(2027)
            matches = upcoming_matches(2027)
            if not events and not matches:
                message = (
                    "No 2027 tier-one event or fixture records are in the current dataset."
                )
            elif events and not matches:
                message = (
                    "VLR lists the event below, but no fixtures are recorded yet."
                )
            else:
                message = "Showing only 2027 events and fixtures listed in the imported source data."
            return json_response(
                200,
                {
                    "year": 2027,
                    "events": events,
                    "matches": matches,
                    "message": message,
                },
            )
        else:
            player_match = PLAYER_ID_PATTERN.fullmatch(path)
            team_match = TEAM_ID_PATTERN.fullmatch(path)
            if player_match:
                year = int(query.get("year", ["2026"])[0])
                if not 2021 <= year <= 2026:
                    raise ValueError("Choose a season from 2021 to 2026.")
                details = player_details(int(player_match.group(1)), year)
                return json_response(
                    200 if details else 404,
                    details or {"error": "Player not found."},
                )
            elif team_match:
                year = int(query.get("year", ["2026"])[0])
                if not 2021 <= year <= 2026:
                    raise ValueError("Choose a season from 2021 to 2026.")
                details = team_details(int(team_match.group(1)), year)
                return json_response(
                    200 if details else 404,
                    details or {"error": "Team not found."},
                )
            else:
                return json_response(404, {"error": "Not found."})
    except ValueError as error:
        return json_response(400, {"error": str(error)})
    except (psycopg2.Error, RuntimeError):
        LOG.exception("VCT API database request failed")
        return json_response(503, {"error": "Database unavailable."})



class VCTRequestHandler(BaseHTTPRequestHandler):
    server_version = "VCTStats/1.0"

    def do_GET(self):
        request = urlsplit(self.path)
        status, body, content_type = get_response(unquote(request.path), parse_qs(request.query))
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for name, value in RESPONSE_HEADERS.items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format_string, *args):
        LOG.info("%s - %s", self.address_string(), format_string % args)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Run the local VCT stats web app.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    server = ThreadingHTTPServer((args.host, args.port), VCTRequestHandler)
    print(f"VCT stats app listening at http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping VCT stats app.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
