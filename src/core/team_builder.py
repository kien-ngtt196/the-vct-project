import csv
import math
import os
from collections import defaultdict

import psycopg2

DATABASE_CONFIG = {
    "dbname": "vct_db",
    "user": "postgres",
    "password": "kotoha19062007",
    "host": "localhost",
    "port": "5432",
}


def normalize_team_name(team_name):
    if team_name is None:
        return ""
    text = str(team_name).strip().lower()
    text = text.replace("&", "and")
    text = "".join(ch for ch in text if ch.isalnum() or ch.isspace())
    return " ".join(text.split())


def normalize_map_name(map_name):
    if map_name is None:
        return ""
    text = str(map_name).strip().lower()
    text = text.replace("-", " ")
    return " ".join(text.split())


def build_player_features():
    teams = build_team_structure()
    features = []
    for team in teams:
        for player in team["players"]:
            features.append({
                "player_name": player["player_name"],
                "team": team["team_name"],
                "team_key": team["team_key"],
                "recent_form": player.get("recent_form", 0.0),
                "consistency": player.get("consistency", 0.0),
                "composite_rating": player.get("composite_rating", 0.0),
                "last_match_date": player.get("last_match_date"),
            })
    return features


def build_team_snapshot():
    teams = build_team_structure()
    by_team = defaultdict(list)

    for team in teams:
        for player in team["players"]:
            by_team[team["team_name"]].append(player)

    team_snapshot = {}

    for team_name, items in by_team.items():
        team_snapshot[team_name] = {
            "team_key": normalize_team_name(team_name),
            "avg_recent_form": sum(p.get("recent_form", 0.0) for p in items) / len(items),
            "avg_consistency": sum(p.get("consistency", 0.0) for p in items) / len(items),
            "avg_composite_rating": sum(p.get("composite_rating", 0.0) for p in items) / len(items),
            "player_count": len(items),
        }

    return team_snapshot


def team_strength_score(team_name):
    snapshot = build_team_snapshot().get(team_name)
    if not snapshot:
        return None

    # simple weighted team score
    score = (
        0.45 * snapshot["avg_recent_form"] +
        0.35 * snapshot["avg_composite_rating"] +
        0.20 * max(0.0, 100.0 - snapshot["avg_consistency"]) / 100.0
    )

    return {
        "team": team_name,
        "score": score,
        "avg_recent_form": snapshot["avg_recent_form"],
        "avg_consistency": snapshot["avg_consistency"],
        "avg_composite_rating": snapshot["avg_composite_rating"],
    }


def fetch_match_history():
    conn = psycopg2.connect(**DATABASE_CONFIG)
    cur = conn.cursor()

    query = """
        SELECT
            t1.canonical_name,
            t2.canonical_name,
            g.team1_score,
            g.team2_score,
            mps.canonical_name,
            m.match_date
        FROM matches m
        JOIN games g ON g.match_id = m.id
        JOIN teams t1 ON t1.team_id = m.team1_id
        JOIN teams t2 ON t2.team_id = m.team2_id
        JOIN maps mps ON mps.map_id = g.map_id
        WHERE m.match_date IS NOT NULL
        ORDER BY m.match_date ASC
    """

    cur.execute(query)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


DEFAULT_MAP_STRENGTH = 0.5


def compute_map_strength():
    teams = build_team_structure()
    result = defaultdict(dict)

    for team in teams:
        team_key = normalize_team_name(team["team_name"])
        for map_name, map_info in team.get("map_stats", {}).items():
            result[team_key][map_name] = map_info.get("win_rate", 0.0)

    return result


def map_strength_for_team(team_name, map_name=None, default=DEFAULT_MAP_STRENGTH):
    normalized_team = normalize_team_name(team_name)
    map_strength = compute_map_strength()
    exact_match = map_strength.get(normalized_team, {})

    if map_name is None:
        return exact_match
    return exact_match.get(normalize_map_name(map_name), default)


def expected_score(rating_a, rating_b):
    return 1.0 / (1.0 + 10 ** ((rating_b - rating_a) / 400.0))


def update_elo(current_rating, opponent_rating, result, k=32):
    expected = expected_score(current_rating, opponent_rating)
    return current_rating + k * (result - expected)


def team_match_prediction(team_a, team_b, map_name=None):
    team_a_score = team_strength_score(team_a)
    team_b_score = team_strength_score(team_b)

    if team_a_score is None or team_b_score is None:
        return {
            "team_a": team_a,
            "team_b": team_b,
            "winner": "unknown",
            "confidence": 0.5,
            "reason": "not enough player data"
        }

    map_strength = compute_map_strength()
    map_a = map_strength_for_team(team_a, map_name)
    map_b = map_strength_for_team(team_b, map_name)

    raw_a = team_a_score["score"] + map_a * 50
    raw_b = team_b_score["score"] + map_b * 50

    diff = raw_a - raw_b
    prob_a = 1 / (1 + math.exp(-diff / 25.0))

    winner = team_a if prob_a >= 0.5 else team_b
    confidence = max(prob_a, 1 - prob_a)

    return {
        "team_a": team_a,
        "team_b": team_b,
        "winner": winner,
        "team_a_win_probability": round(prob_a, 3),
        "team_b_win_probability": round(1 - prob_a, 3),
        "confidence": round(confidence, 3),
        "team_a_score": round(raw_a, 3),
        "team_b_score": round(raw_b, 3),
        "map_strength": {
            team_a: round(map_a, 3),
            team_b: round(map_b, 3),
        }
    }


def mean_or_default(values):
    values = [v for v in values if v is not None]
    if not values:
        return 0.0
    return sum(values) / len(values)


def fetch_team_structure_rows():
    conn = psycopg2.connect(**DATABASE_CONFIG)
    cur = conn.cursor()
    cur.execute("""
        SELECT
            t.canonical_name AS team_name,
            t.team_id,
            pl.canonical_name AS player_name,
            ps.nationality,
            ps.acs,
            ps.rating,
            ps.kast_percentage,
            ps.adr,
            ps.kills,
            ps.deaths,
            ps.assists,
            ps.kd_diff,
            ps.headshot_percentage,
            ps.first_kills,
            ps.first_deaths,
            g.id AS game_id,
            g.map_name,
            m.match_date,
            m.id AS match_id,
            team1.canonical_name AS opponent_name,
            CASE
                WHEN t.team_id = m.team1_id THEN g.team1_score
                ELSE g.team2_score
            END AS team_score,
            CASE
                WHEN t.team_id = m.team1_id THEN g.team2_score
                ELSE g.team1_score
            END AS opponent_score,
            CASE
                WHEN t.team_id = m.team1_id THEN team2.canonical_name
                ELSE team1.canonical_name
            END AS opponent_team_name
        FROM player_stats ps
        JOIN players pl ON pl.player_id = ps.player_id
        JOIN teams t ON t.team_id = ps.team_id
        JOIN games g ON ps.game_id = g.id
        JOIN matches m ON g.match_id = m.id
        JOIN teams team1 ON team1.team_id = m.team1_id
        JOIN teams team2 ON team2.team_id = m.team2_id
        WHERE m.match_date IS NOT NULL
        ORDER BY t.canonical_name, pl.canonical_name, m.match_date ASC
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    normalized_rows = []
    for (
        team_name,
        team_id,
        player_name,
        nationality,
        acs,
        rating,
        kast,
        adr,
        kills,
        deaths,
        assists,
        kd_diff,
        headshot_percent,
        first_kills,
        first_deaths,
        game_id,
        raw_map_name,
        match_date,
        match_id,
        opponent_name,
        team_score,
        opponent_score,
        opponent_team_name,
    ) in rows:
        normalized_rows.append({
            "team_name": team_name,
            "team_key": normalize_team_name(team_name),
            "team_id": team_id,
            "player_name": player_name,
            "player_nationality": nationality,
            "acs": acs,
            "rating": rating,
            "kast": kast,
            "adr": adr,
            "kills": kills,
            "deaths": deaths,
            "assists": assists,
            "kd_diff": kd_diff,
            "headshot_percent": headshot_percent,
            "first_kills": first_kills,
            "first_deaths": first_deaths,
            "game_id": game_id,
            "map_name": raw_map_name,
            "match_date": match_date,
            "match_id": match_id,
            "opponent_name": opponent_name,
            "team_score": team_score,
            "opponent_score": opponent_score,
            "opponent_team_name": opponent_team_name,
        })

    return normalized_rows


def build_team_structure():
    rows = fetch_team_structure_rows()
    if not rows:
        return []

    team_map = defaultdict(lambda: {
        "team_name": "",
        "team_key": "",
        "players": {},
        "match_history": [],
        "map_record": defaultdict(lambda: {"wins": 0, "total": 0}),
    })

    for row in rows:
        team_key = row["team_key"]
        team_entry = team_map[team_key]
        team_entry["team_name"] = row["team_name"]
        team_entry["team_key"] = team_key

        player_key = row["player_name"]
        if player_key not in team_entry["players"]:
            team_entry["players"][player_key] = {
                "player_name": player_key,
                "player_key": player_key,
                "player_nationality": row["player_nationality"],
                "stats": {"acs": [], "rating": [], "kast": [], "adr": [], "kills": [], "deaths": [], "headshots_percent": [], "first_kills": []},
                "match_history": [],
            }

        player = team_entry["players"][player_key]
        player["stats"]["acs"].append(row["acs"])
        player["stats"]["rating"].append(row["rating"])
        player["stats"]["kast"].append(row["kast"])
        player["stats"]["adr"].append(row["adr"])
        player["stats"]["kills"].append(row["kills"])
        player["stats"]["deaths"].append(row["deaths"])
        player["stats"]["headshots_percent"].append(row["headshot_percent"])
        player["stats"]["first_kills"].append(row["first_kills"])

        player["match_history"].append({
            "date": row["match_date"],
            "map": row["map_name"],
            "acs": row["acs"],
            "rating": row["rating"],
            "kast": row["kast"],
            "adr": row["adr"],
        })

        opponent_name = row["opponent_team_name"] or row["opponent_name"]
        if opponent_name is not None:
            team_entry["match_history"].append({
                "date": row["match_date"],
                "opponent": opponent_name,
                "result": "win" if row["team_score"] is not None and row["opponent_score"] is not None and row["team_score"] > row["opponent_score"] else "loss" if row["team_score"] is not None and row["opponent_score"] is not None and row["team_score"] < row["opponent_score"] else "draw",
                "map": row["map_name"],
                "score_line": f"{row['team_score']}-{row['opponent_score']}" if row["team_score"] is not None and row["opponent_score"] is not None else "n/a",
            })

        map_name = normalize_map_name(row["map_name"])
        if map_name:
            map_entry = team_entry["map_record"][map_name]
            map_entry["total"] += 1
            if row["team_score"] is not None and row["opponent_score"] is not None and row["team_score"] > row["opponent_score"]:
                map_entry["wins"] += 1

    teams = []
    for team_key, team_entry in sorted(team_map.items()):
        players = []
        for player_name, player_data in sorted(team_entry["players"].items()):
            stats = player_data["stats"]
            acs_vals = [v for v in stats["acs"] if v is not None]
            rating_vals = [v for v in stats["rating"] if v is not None]
            kast_vals = [v for v in stats["kast"] if v is not None]
            adr_vals = [v for v in stats["adr"] if v is not None]
            kills_vals = [v for v in stats["kills"] if v is not None]
            deaths_vals = [v for v in stats["deaths"] if v is not None]

            kd_ratio = 0.0
            if deaths_vals:
                kd_ratio = mean_or_default(kills_vals) / max(1.0, mean_or_default(deaths_vals))

            player_obj = {
                "player_name": player_name,
                "player_key": player_name,
                "player_nationality": player_data.get("player_nationality"),
                "stats": {
                    "acs": round(mean_or_default(acs_vals), 2),
                    "rating": round(mean_or_default(rating_vals), 2),
                    "kast": round(mean_or_default(kast_vals), 2),
                    "adr": round(mean_or_default(adr_vals), 2),
                    "kd_ratio": round(kd_ratio, 3),
                    "headshots_percent": round(mean_or_default([v for v in stats["headshots_percent"] if v is not None]), 2),
                    "first_kills": round(mean_or_default([v for v in stats["first_kills"] if v is not None]), 2),
                },
                "recent_form": 0.0,
                "consistency": 0.0,
                "composite_rating": 0.0,
                "last_match_date": max((m["date"] for m in player_data["match_history"]), default=None),
                "match_history": sorted(player_data["match_history"], key=lambda x: x["date"]),
            }
            players.append(player_obj)

        map_stats = {}
        for map_name, map_data in sorted(team_entry["map_record"].items()):
            if map_data["total"] <= 0:
                continue
            map_stats[map_name] = {
                "map_name": map_name,
                "win_rate": round(map_data["wins"] / map_data["total"], 3),
                "map_elo": round((map_data["wins"] / map_data["total"]) * 1600.0, 2),
                "games_played": int(map_data["total"]),
            }

        team_recent_form = 0.0
        team_consistency = 0.0
        team_composite = 0.0
        if players:
            team_recent_form = round(mean_or_default([p["recent_form"] for p in players]), 2)
            team_consistency = round(mean_or_default([p["consistency"] for p in players]), 2)
            team_composite = round(mean_or_default([p["composite_rating"] for p in players]), 2)

        teams.append({
            "team_name": team_entry["team_name"],
            "team_key": team_key,
            "overall_rating": round(team_composite * 1000.0, 2),
            "team_stats": {
                "win_rate": round(mean_or_default([m["result"] == "win" for m in team_entry["match_history"]]), 3),
                "recent_form": team_recent_form,
                "consistency": team_consistency,
                "player_count": len(players),
                "avg_composite_rating": team_composite,
                "avg_acs": round(mean_or_default([p["stats"]["acs"] for p in players]), 2),
            },
            "players": players,
            "map_stats": map_stats,
            "match_history": sorted(team_entry["match_history"], key=lambda x: x["date"]),
        })

    return teams


def print_team_structure(teams, limit=10):
    if not teams:
        print("TEAM_STRUCTURE: no teams available")
        return

    print("\n" + "=" * 140)
    print("TEAM STRUCTURE SUMMARY")
    print("=" * 140)

    for idx, team in enumerate(teams[:limit], start=1):
        team_name = team.get("team_name", "UNKNOWN")
        team_key = team.get("team_key", "")
        stats = team.get("team_stats", {})
        players = team.get("players", [])
        map_stats = team.get("map_stats", {})

        print(f"\n[{idx}] TEAM: {team_name}  |  key={team_key}")
        print("-" * 110)
        print(f"  overall_rating: {team.get('overall_rating', 0.0):>8.2f}")
        print(f"  win_rate: {stats.get('win_rate', 0.0):>6.3f} | "
              f"recent_form: {stats.get('recent_form', 0.0):>8.2f} | "
              f"consistency: {stats.get('consistency', 0.0):>6.2f} | "
              f"player_count: {stats.get('player_count', 0)}")
        print(f"  avg_composite_rating: {stats.get('avg_composite_rating', 0.0):>6.3f} | "
              f"avg_acs: {stats.get('avg_acs', 0.0):>7.2f}")

        if players:
            print("  PLAYERS:")
            for p_idx, player in enumerate(players[:5], start=1):
                s = player.get("stats", {})
                print(
                    f"    {p_idx:02d}. {player.get('player_name', 'unknown'):<18} | "
                    f"acs={s.get('acs', 0.0):>6.1f} | "
                    f"rating={s.get('rating', 0.0):>5.2f} | "
                    f"kast={s.get('kast', 0.0):>5.1f} | "
                    f"adr={s.get('adr', 0.0):>6.1f} | "
                    f"recent_form={player.get('recent_form', 0.0):>7.2f} | "
                    f"consistency={player.get('consistency', 0.0):>5.1f}"
                )
            if len(players) > 5:
                print(f"    ... and {len(players) - 5} more players")
        else:
            print("  PLAYERS: none")

        if map_stats:
            print("  MAP STATS:")
            for m_idx, (map_name, map_info) in enumerate(sorted(map_stats.items())[:5], start=1):
                print(
                    f"    {m_idx:02d}. {map_name:<12} | "
                    f"win_rate={map_info.get('win_rate', 0.0):>5.3f} | "
                    f"map_elo={map_info.get('map_elo', 0.0):>8.2f} | "
                    f"games={map_info.get('games_played', 0)}"
                )
            if len(map_stats) > 5:
                print(f"    ... and {len(map_stats) - 5} more maps")
        else:
            print("  MAP STATS: none")

        recent_matches = team.get("match_history", [])
        if recent_matches:
            print("  RECENT MATCHES:")
            for match in recent_matches[:3]:
                print(
                    f"    - {match.get('date', 'n/a')} | opp={match.get('opponent', 'n/a'):<18} | "
                    f"result={match.get('result', 'n/a'):<5} | map={match.get('map', 'n/a'):<8} | score={match.get('score_line', 'n/a')}"
                )

    print("\n" + "=" * 140)


def export_team_overview_csv(output_path="D:/My Projects/the-vct-project/data/team_builder_overview.csv"):
    players = build_player_features()
    by_team = defaultdict(list)
    for player in players:
        by_team[player["team"]].append(player)

    snapshot = build_team_snapshot()
    map_strength = compute_map_strength()

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    fieldnames = [
        "team",
        "row_type",
        "team_avg_recent_form",
        "team_avg_consistency",
        "team_avg_composite_rating",
        "team_player_count",
        "player_name",
        "player_recent_form",
        "player_consistency",
        "player_composite_rating",
        "player_last_match_date",
        "map_strength_summary",
    ]

    with open(output_path, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()

        for team in sorted(snapshot.keys()):
            team_stats = snapshot[team]
            team_key = normalize_team_name(team)
            team_map = map_strength.get(team_key, {})
            if team_map:
                map_summary = " | ".join(f"{map_name}:{value:.3f}" for map_name, value in sorted(team_map.items()))
            else:
                map_summary = "no map history (default 0.5)"

            writer.writerow({
                "team": team,
                "row_type": "team_summary",
                "team_avg_recent_form": team_stats["avg_recent_form"],
                "team_avg_consistency": team_stats["avg_consistency"],
                "team_avg_composite_rating": team_stats["avg_composite_rating"],
                "team_player_count": team_stats["player_count"],
                "player_name": "",
                "player_recent_form": "",
                "player_consistency": "",
                "player_composite_rating": "",
                "player_last_match_date": "",
                "map_strength_summary": map_summary,
            })

            for player in sorted(by_team.get(team, []), key=lambda p: p["player_name"]):
                writer.writerow({
                    "team": team,
                    "row_type": "player",
                    "team_avg_recent_form": team_stats["avg_recent_form"],
                    "team_avg_consistency": team_stats["avg_consistency"],
                    "team_avg_composite_rating": team_stats["avg_composite_rating"],
                    "team_player_count": team_stats["player_count"],
                    "player_name": player["player_name"],
                    "player_recent_form": player["recent_form"],
                    "player_consistency": player["consistency"],
                    "player_composite_rating": player["composite_rating"],
                    "player_last_match_date": player["last_match_date"],
                    "map_strength_summary": map_summary,
                })

    print(f"Saved team overview CSV to: {output_path}")


if __name__ == "__main__":
    teams = build_team_structure()
    print_team_structure(teams, limit=10)
    print(f"\nTOTAL_TEAMS: {len(teams)}")
    export_team_overview_csv()