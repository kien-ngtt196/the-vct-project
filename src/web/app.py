import json
import logging
import mimetypes
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

import psycopg2

from src.analytics.power import (
    PLACEMENT_POINTS, TEAM_POWER_WEIGHTS, achievement_points,
    calculate_player_power, calculate_team_power, placement_rank,
)
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


def _player_search(cursor, query, limit):
    cursor.execute(
        """
        SELECT p.player_id, p.canonical_name, p.image_url, p.image_local_path,
               p.nationality, p.source_url,
               COALESCE(
               (
                   SELECT t.team_id
                   FROM roster_memberships rm
                   JOIN teams t ON t.team_id = rm.team_id
                   WHERE rm.player_id = p.player_id AND rm.status = 'current'
                   ORDER BY rm.updated_at DESC
                   LIMIT 1
               ),
               (
                   SELECT t.team_id
                   FROM match_players mp
                   JOIN teams t ON t.team_id = mp.team_id
                   JOIN matches m ON m.id = mp.match_id
                   JOIN tournaments tournament ON tournament.id = m.tournament_id
                   LEFT JOIN seasons event_season ON event_season.season_id = tournament.season_id
                   WHERE mp.player_id = p.player_id
                     AND m.match_date >= DATE '2026-01-01'
                     AND m.match_date < DATE '2027-01-01'
                     AND COALESCE(event_season.year, EXTRACT(YEAR FROM m.match_date)::INTEGER) = 2026
                   ORDER BY m.match_date DESC NULLS LAST
                   LIMIT 1
               )) AS last_team_id,
               COALESCE(
               (
                   SELECT t.canonical_name
                   FROM roster_memberships rm
                   JOIN teams t ON t.team_id = rm.team_id
                   WHERE rm.player_id = p.player_id AND rm.status = 'current'
                   ORDER BY rm.updated_at DESC
                   LIMIT 1
               ),
               (
                   SELECT t.canonical_name
                   FROM match_players mp
                   JOIN teams t ON t.team_id = mp.team_id
                   JOIN matches m ON m.id = mp.match_id
                   JOIN tournaments tournament ON tournament.id = m.tournament_id
                   LEFT JOIN seasons event_season ON event_season.season_id = tournament.season_id
                   WHERE mp.player_id = p.player_id
                     AND m.match_date >= DATE '2026-01-01'
                     AND m.match_date < DATE '2027-01-01'
                     AND COALESCE(event_season.year, EXTRACT(YEAR FROM m.match_date)::INTEGER) = 2026
                   ORDER BY m.match_date DESC NULLS LAST
                   LIMIT 1
               )) AS last_team
        FROM players p
        WHERE (p.canonical_name ILIKE %s
           OR EXISTS (
               SELECT 1 FROM player_aliases pa
               WHERE pa.player_id = p.player_id AND pa.alias_name ILIKE %s
           ))
          AND (
              EXISTS (
              SELECT 1 FROM match_players mp
              JOIN matches m ON m.id = mp.match_id
              JOIN tournaments tournament ON tournament.id = m.tournament_id
              LEFT JOIN seasons event_season ON event_season.season_id = tournament.season_id
              WHERE mp.player_id = p.player_id
                AND m.match_date >= DATE '2026-01-01'
                AND m.match_date < DATE '2027-01-01'
                AND COALESCE(event_season.year, EXTRACT(YEAR FROM m.match_date)::INTEGER) = 2026
              )
              OR EXISTS (
                  SELECT 1 FROM roster_memberships rm
                  WHERE rm.player_id = p.player_id AND rm.status = 'current'
              )
          )
        ORDER BY p.canonical_name
        LIMIT %s
        """,
        (f"%{query}%", f"%{query}%", limit),
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


def search_entities(query, entity_type="all", limit=20):
    if entity_type not in {"all", "players", "teams"}:
        raise ValueError("type must be all, players, or teams.")
    if not query.strip():
        return []
    with connect() as connection:
        with connection.cursor() as cursor:
            results = []
            if entity_type in {"all", "players"}:
                results.extend(_player_search(cursor, query.strip(), limit))
            if entity_type in {"all", "teams"}:
                results.extend(_team_search(cursor, query.strip(), limit))
    return results[:limit]


def player_details(player_id):
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
                       ps.first_kills, ps.agent
                FROM player_stats ps
                JOIN games g ON g.id = ps.game_id
                JOIN matches m ON m.id = g.match_id
                JOIN tournaments tournament ON tournament.id = m.tournament_id
                LEFT JOIN seasons event_season ON event_season.season_id = tournament.season_id
                LEFT JOIN teams t ON t.team_id = ps.team_id
                WHERE ps.player_id = %s
                  AND tournament.tier = 'tier1'
                  AND m.match_date >= DATE '2026-01-01'
                  AND m.match_date < DATE '2027-01-01'
                  AND COALESCE(event_season.year, EXTRACT(YEAR FROM m.match_date)::INTEGER) = 2026
                ORDER BY m.match_date DESC NULLS LAST, m.id DESC, g.id
                LIMIT 10
                """,
                (player_id,),
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
                       COALESCE(SUM(stats.first_kills), 0)
                FROM player_stats stats
                JOIN games game ON game.id = stats.game_id
                JOIN matches match ON match.id = game.match_id
                JOIN tournaments tournament ON tournament.id = match.tournament_id
                LEFT JOIN seasons event_season ON event_season.season_id = tournament.season_id
                WHERE stats.player_id = %s
                  AND tournament.tier = 'tier1'
                  AND match.match_date >= DATE '2026-01-01'
                  AND match.match_date < DATE '2027-01-01'
                  AND COALESCE(
                      event_season.year,
                      EXTRACT(YEAR FROM match.match_date)::INTEGER
                  ) = 2026
                """,
                (player_id,),
            )
            player_stats = cursor.fetchone()

            cursor.execute(
                """
                SELECT t.team_id, t.canonical_name, rm.start_date, rm.end_date,
                       rm.status, rm.source, rm.source_url, rm.notes
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
                }
                for row in cursor.fetchall()
            ]

            cursor.execute(
                """
                SELECT t.team_id, t.canonical_name, MIN(m.match_date), MAX(m.match_date),
                       COUNT(DISTINCT m.id)
                FROM match_players mp
                JOIN teams t ON t.team_id = mp.team_id
                JOIN matches m ON m.id = mp.match_id
                JOIN tournaments tournament ON tournament.id = m.tournament_id
                LEFT JOIN seasons event_season ON event_season.season_id = tournament.season_id
                WHERE mp.player_id = %s
                  AND tournament.tier = 'tier1'
                  AND m.match_date >= DATE '2026-01-01'
                  AND m.match_date < DATE '2027-01-01'
                  AND COALESCE(event_season.year, EXTRACT(YEAR FROM m.match_date)::INTEGER) = 2026
                GROUP BY t.team_id, t.canonical_name
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
                }
                for row in cursor.fetchall()
            ]

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
        (entry for entry in player_power_rankings() if entry["id"] == player_id),
        None,
    )

    return {
        "id": player[0],
        "name": player[1],
        "image_url": player[2],
        "image_local_path": player[3],
        "nationality": player[4],
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
                       opponent.canonical_name, tournament.title, tournament.url
                FROM matches m
                JOIN tournaments tournament ON tournament.id = m.tournament_id
                LEFT JOIN seasons event_season ON event_season.season_id = tournament.season_id
                LEFT JOIN teams opponent ON opponent.team_id =
                    CASE WHEN m.team1_id = %s THEN m.team2_id ELSE m.team1_id END
                WHERE tournament.tier = 'tier1'
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
                       ) AS matches_drawn
                FROM tournaments tournament
                JOIN matches match ON match.tournament_id = tournament.id
                LEFT JOIN seasons event_season ON event_season.season_id = tournament.season_id
                LEFT JOIN team_event_results result
                  ON result.tournament_id = tournament.id AND result.team_id = %s
                 AND result.prize IS NOT NULL
                WHERE tournament.tier = 'tier1'
                  AND (match.team1_id = %s OR match.team2_id = %s)
                  AND COALESCE(
                      event_season.year,
                      EXTRACT(YEAR FROM match.match_date)::INTEGER
                  ) = %s
                GROUP BY tournament.id, tournament.title, tournament.url,
                         tournament.prize_pool, result.placement_text, result.prize
                ORDER BY tournament.title
                """,
                (team_id, team_id, team_id, team_id, team_id, year),
            )
            tournaments = [
                {
                    "id": row[0],
                    "title": row[1],
                    "url": row[2],
                    "prize_pool": row[3],
                    "placement": row[4],
                    "prize": row[5],
                    "matches_played": row[6],
                    "matches_won": row[7],
                    "matches_drawn": row[8],
                }
                for row in cursor.fetchall()
            ]

    match_rows.sort(key=lambda row: str(row[1] or ""), reverse=True)
    recent_matches = []
    for row in match_rows[:10]:
        team1_score, team2_score = row[5], row[6]
        won = None
        if team1_score is not None and team2_score is not None:
            score = team1_score if row[3] == team_id else team2_score
            opponent_score = team2_score if row[3] == team_id else team1_score
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
        "current_roster": [
            {
                "id": row[0],
                "name": row[1],
                "image_url": row[2],
                "image_local_path": row[3],
                "role": row[4],
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
            }
            for row in observed_players
        ],
        "recent_matches": recent_matches,
    }


def season_achievements(cursor, year):
    cursor.execute(
        """
        WITH events AS (
            SELECT t.id, CASE
                WHEN t.title ILIKE 'Valorant Champions 20%%' THEN 'champions'
                WHEN t.title ILIKE '%%masters%%' THEN 'masters'
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
            UNION
            SELECT r.tournament_id, r.team_id
            FROM team_event_results r JOIN events e ON e.id = r.tournament_id
            WHERE r.prize IS NOT NULL
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
            GROUP BY m.tournament_id
            HAVING COUNT(*) = 1
        )
        SELECT e.id, e.kind, p.team_id, COALESCE(r.placement_text, CASE
            WHEN p.team_id = f.team1_id THEN CASE WHEN f.score1 > f.score2 THEN '1st' ELSE '2nd' END
            WHEN p.team_id = f.team2_id THEN CASE WHEN f.score2 > f.score1 THEN '1st' ELSE '2nd' END
        END)
        FROM events e LEFT JOIN participants p ON p.tournament_id = e.id
        LEFT JOIN team_event_results r
          ON r.tournament_id = e.id AND r.team_id = p.team_id AND r.prize IS NOT NULL
        LEFT JOIN regional_finals f ON f.tournament_id = e.id
        """,
        (year,),
    )
    rows = cursor.fetchall()
    international_events = {
        event_id: kind for event_id, kind, _, _ in rows if kind != "regional"
    }
    international_max = sum(PLACEMENT_POINTS[kind][0] for kind in international_events.values())
    results = {}
    for event_id, kind, team_id, placement in rows:
        if team_id is None or (kind == "regional" and placement_rank(placement) is None):
            continue
        results.setdefault(team_id, []).append({
            "event_id": event_id, "kind": kind, "placement": placement,
            "points": achievement_points(kind, placement),
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
                               WHEN tournament.title ILIKE '%%masters%%' THEN {MASTERS_EVENT_WEIGHT}
                               ELSE {REGIONAL_EVENT_WEIGHT}
                           END AS event_weight
                    FROM matches m
                    JOIN tournaments tournament ON tournament.id = m.tournament_id
                    LEFT JOIN seasons event_season ON event_season.season_id = tournament.season_id
                    WHERE tournament.tier = 'tier1'
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
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                WITH match_context AS (
                    SELECT match.id,
                           CASE
                               WHEN tournament.title ILIKE 'Valorant Champions 20%%' THEN 'champions'
                               WHEN tournament.title ILIKE '%%masters%%' THEN 'masters'
                               ELSE 'regional'
                           END AS event_kind,
                           match.url ~* '-(gf|[ulm]bf|ub[qs]f|[ulm]r[0-9]+|playoffs|grand-final)/?$' AS bracket_match
                    FROM matches match
                    JOIN tournaments tournament ON tournament.id = match.tournament_id
                    LEFT JOIN seasons event_season ON event_season.season_id = tournament.season_id
                    WHERE tournament.tier = 'tier1'
                      AND COALESCE(
                          event_season.year,
                          EXTRACT(YEAR FROM match.match_date)::INTEGER
                      ) = %s
                      AND match.match_date >= make_date(%s, 1, 1)
                      AND match.match_date < make_date(%s, 1, 1)
                      AND lower(COALESCE(match.status, '')) IN ('final', 'completed', 'complete')
                ),
                eligible_matches AS (
                    SELECT id, event_kind,
                           CASE event_kind
                               WHEN 'champions' THEN CASE WHEN bracket_match THEN {PLAYER_EVENT_WEIGHTS['champions'][1]} ELSE {PLAYER_EVENT_WEIGHTS['champions'][0]} END
                               WHEN 'masters' THEN CASE WHEN bracket_match THEN {PLAYER_EVENT_WEIGHTS['masters'][1]} ELSE {PLAYER_EVENT_WEIGHTS['masters'][0]} END
                               ELSE CASE WHEN bracket_match THEN {PLAYER_EVENT_WEIGHTS['regional'][1]} ELSE {PLAYER_EVENT_WEIGHTS['regional'][0]} END
                           END AS event_weight
                    FROM match_context
                ),
                player_totals AS (
                    SELECT stats.player_id,
                           COUNT(DISTINCT game.id) AS maps_played,
                           SUM(stats.rating * eligible.event_weight)
                               / NULLIF(
                                   SUM(eligible.event_weight)
                                       FILTER (WHERE stats.rating IS NOT NULL),
                                   0
                               ) AS rating,
                           SUM(stats.acs * eligible.event_weight)
                               / NULLIF(
                                   SUM(eligible.event_weight)
                                       FILTER (WHERE stats.acs IS NOT NULL),
                                   0
                               ) AS acs,
                           SUM(stats.kast_percentage * eligible.event_weight)
                               / NULLIF(
                                   SUM(eligible.event_weight)
                                       FILTER (WHERE stats.kast_percentage IS NOT NULL),
                                   0
                               ) AS kast,
                           SUM(stats.adr * eligible.event_weight)
                               / NULLIF(
                                   SUM(eligible.event_weight)
                                       FILTER (WHERE stats.adr IS NOT NULL),
                                   0
                               ) AS adr,
                           SUM(COALESCE(stats.kills, 0) * eligible.event_weight) AS kills,
                           SUM(COALESCE(stats.deaths, 0) * eligible.event_weight) AS deaths,
                           COUNT(DISTINCT game.id) FILTER (WHERE eligible.event_kind <> 'regional') AS international_maps,
                           AVG(stats.rating) FILTER (WHERE eligible.event_kind <> 'regional') AS international_rating
                    FROM player_stats stats
                    JOIN games game ON game.id = stats.game_id
                    JOIN eligible_matches eligible ON eligible.id = game.match_id
                    WHERE stats.player_id IS NOT NULL
                    GROUP BY stats.player_id
                    HAVING COUNT(DISTINCT game.id) >= 5
                )
                SELECT player.player_id, player.canonical_name, player.image_url,
                       player.image_local_path, player.nationality, player.source_url,
                       totals.maps_played, totals.rating, totals.acs, totals.kast,
                       totals.adr, totals.kills, totals.deaths,
                       COALESCE(roster_team.canonical_name, observed_team.canonical_name),
                       totals.international_maps, totals.international_rating
                FROM player_totals totals
                JOIN players player ON player.player_id = totals.player_id
                LEFT JOIN LATERAL (
                    SELECT team.canonical_name
                    FROM roster_memberships membership
                    JOIN teams team ON team.team_id = membership.team_id
                    WHERE membership.player_id = player.player_id
                      AND membership.status = 'current' AND %s = 2026
                    ORDER BY membership.updated_at DESC
                    LIMIT 1
                ) roster_team ON TRUE
                LEFT JOIN LATERAL (
                    SELECT team.canonical_name
                    FROM match_players appearance
                    JOIN teams team ON team.team_id = appearance.team_id
                    JOIN matches match ON match.id = appearance.match_id
                    JOIN tournaments tournament ON tournament.id = match.tournament_id
                    LEFT JOIN seasons event_season ON event_season.season_id = tournament.season_id
                    WHERE appearance.player_id = player.player_id
                      AND tournament.tier = 'tier1'
                      AND COALESCE(
                          event_season.year,
                          EXTRACT(YEAR FROM match.match_date)::INTEGER
                      ) = %s
                      AND match.match_date >= make_date(%s, 1, 1)
                      AND match.match_date < make_date(%s, 1, 1)
                    ORDER BY match.match_date DESC NULLS LAST
                    LIMIT 1
                ) observed_team ON TRUE
                """,
                (year, year, year + 1, year, year, year, year + 1),
            )
            players = [
                {
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
                    "team": row[13],
                }
                for row in cursor.fetchall()
            ]
    return calculate_player_power(players)


def events_for_season(year):
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT tournament.id, tournament.title, tournament.status,
                       tournament.url, tournament.region,
                       tournament.start_date, tournament.end_date,
                       (SELECT COUNT(*) FROM matches WHERE tournament_id = tournament.id)
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
                }
                for row in cursor.fetchall()
            ]


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


class VCTRequestHandler(BaseHTTPRequestHandler):
    server_version = "VCTStats/1.0"

    def _send(self, status, body, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' https://vlr.gg https://www.vlr.gg "
            "https://owcdn.net data:; "
            "style-src 'self' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; script-src 'self'; "
            "connect-src 'self'; object-src 'none'; base-uri 'none'",
        )
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, status, payload):
        body = json.dumps(payload, default=str).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    def _static_file(self, relative_path, base_directory=STATIC_DIR):
        path = (base_directory / relative_path).resolve()
        if not path.is_relative_to(base_directory.resolve()) or not path.is_file():
            self._send_json(404, {"error": "Not found."})
            return
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self._send(200, path.read_bytes(), f"{content_type}; charset=utf-8")

    def do_GET(self):
        request = urlsplit(self.path)
        path = unquote(request.path)
        query = parse_qs(request.query)

        try:
            if path == "/":
                self._static_file("index.html")
            elif path in {"/app.css", "/app.js", "/theme.js"} or path.startswith("/assets/"):
                self._static_file(path.lstrip("/"))
            elif path.startswith("/vct-images/"):
                image_path = path.removeprefix("/vct-images/")
                if Path(image_path).suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
                    self._send_json(404, {"error": "Not found."})
                else:
                    self._static_file(image_path, VCT_IMAGE_DIR)
            elif path == "/api/health":
                with connect() as connection:
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT 1")
                self._send_json(200, {"status": "ok", "database": "connected"})
            elif path == "/api/events":
                year = int(query.get("year", ["2026"])[0])
                if not 2022 <= year <= 2026:
                    raise ValueError("Choose a season from 2022 to 2026.")
                self._send_json(200, {"year": year, "events": events_for_season(year)})
            elif path == "/api/search":
                entity_type = query.get("type", ["all"])[0]
                limit = min(50, max(1, int(query.get("limit", ["20"])[0])))
                self._send_json(
                    200,
                    {
                        "results": search_entities(
                            query.get("q", [""])[0], entity_type, limit
                        )
                    },
                )
            elif path == "/api/power-rankings":
                year = int(query.get("year", ["2026"])[0])
                if not 2022 <= year <= 2026:
                    raise ValueError("Choose a season from 2022 to 2026.")
                self._send_json(
                    200,
                    {
                        "year": year,
                        "teams": team_power_rankings(year),
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
                if not 2022 <= year <= 2026:
                    raise ValueError("Choose a season from 2022 to 2026.")
                self._send_json(
                    200,
                    {
                        "year": year,
                        "players": player_power_rankings(year),
                        "formula": {
                            "rating": 0.35,
                            "acs": 0.25,
                            "kast": 0.2,
                            "adr": 0.1,
                            "kd_strength": 0.1,
                            "minimum_maps": 5,
                            "score_scaling": (
                                "The displayed score is the sample-adjusted player score out of 100."
                            ),
                            "event_weights": {
                                kind: {"base": weights[0], "bracket": weights[1]}
                                for kind, weights in PLAYER_EVENT_WEIGHTS.items()
                            },
                            "sample_prior_maps": 10,
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
                self._send_json(
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
                    details = player_details(int(player_match.group(1)))
                    self._send_json(
                        200 if details else 404,
                        details or {"error": "Player not found."},
                    )
                elif team_match:
                    year = int(query.get("year", ["2026"])[0])
                    if not 2022 <= year <= 2026:
                        raise ValueError("Choose a season from 2022 to 2026.")
                    details = team_details(int(team_match.group(1)), year)
                    self._send_json(
                        200 if details else 404,
                        details or {"error": "Team not found."},
                    )
                else:
                    self._send_json(404, {"error": "Not found."})
        except ValueError as error:
            self._send_json(400, {"error": str(error)})
        except (psycopg2.Error, RuntimeError) as error:
            LOG.exception("VCT API database request failed")
            self._send_json(503, {"error": str(error)})

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
