import argparse
import re
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path

from src.db.database import connect
from src.db.initialize import initialize_database


ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw"

TEAM_CANONICAL_NAMES = {
    alias: canonical
    for canonical, aliases in {
        "100 thieves": ("100 thieves", "100t"),
        "a team": ("a team", "at"),
        "all gamers": ("all gamers", "ag"),
        "any questions gaming": ("any questions gaming", "aq"),
        "bbl esports": ("bbl esports", "bbl"),
        "bilibili gaming": (
            "bilibili gaming",
            "blg",
            "guangzhou huadu bilibili gamingbilibili gaming",
        ),
        "cloud9": ("cloud9", "c9"),
        "detonation focusme": ("detonation focusme", "dfm"),
        "dragon ranger gaming": ("dragon ranger gaming", "drg"),
        "edward gaming": ("edward gaming", "edg"),
        "eternal fire": ("eternal fire", "ef"),
        "evil geniuses": ("evil geniuses", "eg"),
        "fire flux esports": ("fire flux esports", "ff"),
        "fnatic": ("fnatic", "fnc"),
        "funplus phoenix": ("funplus phoenix", "fpx"),
        "full sense": ("full sense", "fs"),
        "furia": ("furia", "fur"),
        "fut esports": ("fut esports", "fut"),
        "g2 esports": ("g2 esports", "g2"),
        "global esports": ("global esports", "ge"),
        "geng": ("geng", "gen", "gen g"),
        "giantx": ("giantx", "gx"),
        "jd gaming": ("jd gaming", "jdg", "jd mall jdg esportsjd gaming"),
        "karmine corp": ("karmine corp", "kc"),
        "keepbest gaming": ("keepbest gaming", "kbg"),
        "krü esports": ("krü esports", "krü", "kru", "kru esports", "kr esports"),
        "kiwoom drx": ("kiwoom drx", "krx"),
        "leviatán": ("leviatán", "lev", "leviat n"),
        "nova esports": ("nova esports", "nova"),
        "natus vincere": ("natus vincere", "navi"),
        "nongshim redforce": (
            "nongshim redforce",
            "nongshin redforce",
            "ns",
        ),
        "octagonal disposition gaming": ("octagonal disposition gaming", "odg"),
        "onside gaming": ("onside gaming", "ong"),
        "paper rex": ("paper rex", "paperrex", "prx"),
        "pcific esports": ("pcific esports", "pcf"),
        "rare atom": ("rare atom", "ra"),
        "rex regum qeon": ("rex regum qeon", "rrq"),
        "sentinels": ("sentinels", "sen"),
        "team heretics": ("team heretics", "th"),
        "team liquid": ("team liquid", "tl"),
        "team secret": ("team secret", "ts"),
        "team vitality": ("team vitality", "vit"),
        "titan esports club": (
            "titan esports club",
            "tec",
            "wuxi titan esports clubtitan esports club",
        ),
        "tyloo": ("tyloo", "tyl"),
        "trace esports": ("trace esports", "te"),
        "ulf esports": ("ulf esports", "ulf"),
        "unsettled resentment": ("unsettled resentment", "ur"),
        "victory no limits gaming": ("victory no limits gaming", "vlg"),
        "weibo gaming": ("weibo gaming", "wbg"),
        "wolves esports": ("wolves esports", "wol"),
        "world sports invictus gaming": ("world sports invictus gaming", "wsig"),
        "xi lai gaming": ("xi lai gaming", "xlg"),
        "zeta division": ("zeta division", "zeta"),
    }.items()
    for alias in aliases
}


def safe_int(value):
    if value is None or str(value).strip() == "":
        return None
    try:
        return int(str(value).replace("+", "").strip())
    except ValueError:
        return None


def safe_float(value):
    if value is None or str(value).strip() == "":
        return None
    try:
        number = float(str(value).replace("%", "").strip())
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def parse_match_date(value):
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


def normalize_name(value):
    if value is None:
        return ""
    text = str(value).strip().lower().replace("&", "and")
    text = "".join(char for char in text if char.isalnum() or char.isspace())
    return " ".join(text.split())


def canonical_team_name(value):
    normalized = normalize_name(value)
    return TEAM_CANONICAL_NAMES.get(normalized, normalized)


def resolve_input_path(input_path=None):
    configured = input_path or os.getenv("VCT_INPUT_JSON")
    if configured:
        path = Path(configured)
        if not path.is_absolute():
            path = ROOT / path
        if not path.is_file():
            raise FileNotFoundError(f"VLR snapshot does not exist: {path}")
        return path

    candidates = sorted(
        path for path in RAW_DIR.glob("events_*.json")
        if not path.name.endswith("_catalog.json")
    )
    if not candidates:
        raise FileNotFoundError(
            "No VLR snapshots found. Run the tier-one scraper or set VCT_INPUT_JSON."
        )
    return candidates[-1]


def get_or_create_season(cursor, season):
    if season is None or str(season).strip() == "":
        return None
    season_year = safe_int(season)
    season_name = str(season_year) if season_year is not None else str(season).strip()
    if not season_name:
        return None
    cursor.execute(
        """
        INSERT INTO seasons (season_name, year)
        VALUES (%s, %s)
        ON CONFLICT (season_name) DO UPDATE SET year = COALESCE(EXCLUDED.year, seasons.year)
        RETURNING season_id
        """,
        (season_name, season_year),
    )
    return cursor.fetchone()[0]


def get_or_create_team(cursor, name, source_url=None, logo_url=None):
    canonical = canonical_team_name(name)
    if not canonical:
        return None
    cursor.execute(
        """
        INSERT INTO teams (canonical_name, source_url, logo_url)
        VALUES (%s, %s, %s)
        ON CONFLICT (canonical_name) DO UPDATE SET
            source_url = COALESCE(EXCLUDED.source_url, teams.source_url),
            logo_url = COALESCE(EXCLUDED.logo_url, teams.logo_url)
        RETURNING team_id
        """,
        (canonical, source_url, logo_url),
    )
    team_id = cursor.fetchone()[0]
    cursor.execute(
        """
        INSERT INTO team_aliases (team_id, alias_name)
        VALUES (%s, %s)
        ON CONFLICT (team_id, alias_name) DO NOTHING
        """,
        (team_id, str(name).strip()),
    )
    return team_id


def get_or_create_player(cursor, player):
    name = player.get("name")
    canonical = normalize_name(name)
    if not canonical:
        return None
    cursor.execute(
        """
        INSERT INTO players (canonical_name, source_url, image_url, nationality)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (canonical_name) DO UPDATE SET
            source_url = COALESCE(EXCLUDED.source_url, players.source_url),
            image_url = COALESCE(EXCLUDED.image_url, players.image_url),
            nationality = COALESCE(EXCLUDED.nationality, players.nationality)
        RETURNING player_id
        """,
        (
            canonical,
            player.get("profile_url"),
            player.get("image_url"),
            player.get("nationality"),
        ),
    )
    player_id = cursor.fetchone()[0]
    cursor.execute(
        """
        INSERT INTO player_aliases (player_id, alias_name)
        VALUES (%s, %s)
        ON CONFLICT (player_id, alias_name) DO NOTHING
        """,
        (player_id, str(name).strip()),
    )
    return player_id


def get_or_create_map(cursor, map_name):
    canonical = normalize_name(map_name)
    if not canonical:
        return None
    cursor.execute(
        """
        INSERT INTO maps (canonical_name) VALUES (%s)
        ON CONFLICT (canonical_name) DO UPDATE SET canonical_name = EXCLUDED.canonical_name
        RETURNING map_id
        """,
        (canonical,),
    )
    return cursor.fetchone()[0]


def is_tier_one_event(title):
    return not re.search(
        r"ascension|game changers|china evolution series|china threshold|road to vct|emea promotion",
        title, re.IGNORECASE,
    )


def upsert_tournament(cursor, tournament, season_id):
    tournament_id = tournament.get("id")
    if not tournament_id:
        raise ValueError(f"Tournament has no VLR event id: {tournament.get('title')!r}")
    cursor.execute(
        """
        INSERT INTO tournaments (
            id, title, url, status, season_id, tier, region, logo_url,
            start_date, end_date, last_scraped_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
        ON CONFLICT (id) DO UPDATE SET
            title = EXCLUDED.title,
            url = EXCLUDED.url,
            status = EXCLUDED.status,
            season_id = EXCLUDED.season_id,
            tier = EXCLUDED.tier,
            region = COALESCE(EXCLUDED.region, tournaments.region),
            logo_url = COALESCE(EXCLUDED.logo_url, tournaments.logo_url),
            start_date = COALESCE(EXCLUDED.start_date, tournaments.start_date),
            end_date = COALESCE(EXCLUDED.end_date, tournaments.end_date),
            last_scraped_at = now()
        """,
        (
            str(tournament_id),
            tournament["title"],
            tournament["url"],
            tournament.get("status") or "unknown",
            season_id,
            "tier1" if is_tier_one_event(tournament["title"]) else "outside-tier1",
            tournament.get("region"),
            tournament.get("logo_url"),
            tournament.get("start_date"),
            tournament.get("end_date"),
        ),
    )


def upsert_match(cursor, match, tournament_id, season_id):
    match_id = match.get("id")
    if not match_id:
        raise ValueError(f"Match has no VLR id: {match.get('url')!r}")
    team1_id = get_or_create_team(
        cursor,
        match.get("team1"),
        match.get("team1_url"),
        match.get("team1_logo_url"),
    )
    team2_id = get_or_create_team(
        cursor,
        match.get("team2"),
        match.get("team2_url"),
        match.get("team2_logo_url"),
    )
    cursor.execute(
        """
        INSERT INTO matches (
            id, tournament_id, season_id, url, status, format, team1, team2,
            team1_id, team2_id, team1_score, team2_score, match_date
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO UPDATE SET
            tournament_id = EXCLUDED.tournament_id,
            season_id = EXCLUDED.season_id,
            url = EXCLUDED.url,
            status = EXCLUDED.status,
            format = EXCLUDED.format,
            team1 = EXCLUDED.team1,
            team2 = EXCLUDED.team2,
            team1_id = EXCLUDED.team1_id,
            team2_id = EXCLUDED.team2_id,
            team1_score = COALESCE(EXCLUDED.team1_score, matches.team1_score),
            team2_score = COALESCE(EXCLUDED.team2_score, matches.team2_score),
            match_date = COALESCE(EXCLUDED.match_date, matches.match_date)
        """,
        (
            str(match_id),
            str(tournament_id),
            season_id,
            match["url"],
            match.get("status") or "unknown",
            match.get("format"),
            match.get("team1"),
            match.get("team2"),
            team1_id,
            team2_id,
            safe_int(match.get("team1_score")),
            safe_int(match.get("team2_score")),
            parse_match_date(match.get("date")),
        ),
    )


def upsert_game(cursor, game, match_id, season_id):
    game_id = game.get("game_id")
    if not game_id:
        raise ValueError(f"Map record has no VLR game id in match {match_id}.")
    map_id = get_or_create_map(cursor, game.get("map_name"))
    cursor.execute(
        """
        INSERT INTO games (id, match_id, season_id, map_name, map_id, team1_score, team2_score)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO UPDATE SET
            match_id = EXCLUDED.match_id,
            season_id = EXCLUDED.season_id,
            map_name = EXCLUDED.map_name,
            map_id = EXCLUDED.map_id,
            team1_score = EXCLUDED.team1_score,
            team2_score = EXCLUDED.team2_score
        """,
        (
            str(game_id),
            str(match_id),
            season_id,
            game.get("map_name"),
            map_id,
            safe_int(game.get("team1_score")),
            safe_int(game.get("team2_score")),
        ),
    )


def resolve_match_player_team(player, game, match):
    players = game.get("players", [])
    if len(players) != 10:
        return None

    # VLR orders the two five-player groups in match-header team order.
    tags = [normalize_name(row.get("team")) for row in players]
    first_team_tag = tags[0]
    second_team_tag = tags[5]
    if (
        not first_team_tag
        or not second_team_tag
        or first_team_tag == second_team_tag
        or any(tag != first_team_tag for tag in tags[:5])
        or any(tag != second_team_tag for tag in tags[5:])
    ):
        return None

    player_tag = normalize_name(player.get("team"))
    if player_tag == first_team_tag:
        side = 1
    elif player_tag == second_team_tag:
        side = 2
    else:
        return None

    team_name = match.get(f"team{side}")
    if not team_name:
        return None
    return {
        "name": team_name,
        "source_url": match.get(f"team{side}_url"),
        "logo_url": match.get(f"team{side}_logo_url"),
    }


def upsert_player_stats(cursor, player, game, match, season_id):
    player_id = get_or_create_player(cursor, player)
    observed_team = player.get("team")
    match_team = resolve_match_player_team(player, game, match)
    team_name = match_team["name"] if match_team else observed_team
    team_id = get_or_create_team(
        cursor,
        team_name,
        source_url=match_team.get("source_url") if match_team else None,
        logo_url=match_team.get("logo_url") if match_team else None,
    )
    player_name = player.get("name")
    if player_id is None or team_id is None or not player_name:
        return

    if observed_team and match_team:
        cursor.execute(
            """
            INSERT INTO team_aliases (team_id, alias_name)
            VALUES (%s, %s)
            ON CONFLICT (team_id, alias_name) DO NOTHING
            """,
            (team_id, str(observed_team).strip()),
        )

    date_played = parse_match_date(match.get("date"))
    if date_played is not None:
        cursor.execute(
            """
            INSERT INTO match_players (match_id, player_id, team_id, first_seen_at, source_url)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (match_id, player_id, team_id) DO UPDATE SET
                first_seen_at = LEAST(match_players.first_seen_at, EXCLUDED.first_seen_at),
                source_url = COALESCE(EXCLUDED.source_url, match_players.source_url)
            """,
            (
                str(match["id"]),
                player_id,
                team_id,
                date_played,
                player.get("profile_url"),
            ),
        )

    cursor.execute(
        """
        INSERT INTO player_stats (
            game_id, player_name, player_id, team, team_id, season_id, nationality, agent,
            rating, acs, kills, deaths, assists, kd_diff, kast_percentage, adr,
            headshot_percentage, first_kills, first_deaths
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (game_id, player_name) DO UPDATE SET
            player_id = EXCLUDED.player_id,
            team = EXCLUDED.team,
            team_id = EXCLUDED.team_id,
            season_id = EXCLUDED.season_id,
            nationality = EXCLUDED.nationality,
            agent = EXCLUDED.agent,
            rating = EXCLUDED.rating,
            acs = EXCLUDED.acs,
            kills = EXCLUDED.kills,
            deaths = EXCLUDED.deaths,
            assists = EXCLUDED.assists,
            kd_diff = EXCLUDED.kd_diff,
            kast_percentage = EXCLUDED.kast_percentage,
            adr = EXCLUDED.adr,
            headshot_percentage = EXCLUDED.headshot_percentage,
            first_kills = EXCLUDED.first_kills,
            first_deaths = EXCLUDED.first_deaths
        """,
        (
            str(game["game_id"]),
            str(player_name),
            player_id,
            team_name,
            team_id,
            season_id,
            player.get("nationality"),
            player.get("agent"),
            safe_float(player.get("rating")),
            safe_float(player.get("acs")),
            safe_int(player.get("kills")),
            safe_int(player.get("deaths")),
            safe_int(player.get("assists")),
            safe_int(player.get("kd_diff")),
            safe_float(player.get("kast")),
            safe_float(player.get("adr")),
            safe_float(player.get("headshot_percentage")),
            safe_int(player.get("first_kills")),
            safe_int(player.get("first_deaths")),
        ),
    )


def import_snapshot(input_path=None):
    snapshot_path = resolve_input_path(input_path)
    with snapshot_path.open("r", encoding="utf-8") as snapshot_file:
        tournaments = json.load(snapshot_file)
    if not isinstance(tournaments, list):
        raise ValueError("VLR snapshot must contain a list of tournaments.")

    initialize_database()
    connection = connect()
    try:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO ingestion_runs (source, input_path, events_seen, matches_seen)
                    VALUES (%s, %s, %s, %s)
                    RETURNING ingestion_run_id
                    """,
                    (
                        "vlr.gg-tier1",
                        str(snapshot_path),
                        len(tournaments),
                        sum(len(event.get("matches", [])) for event in tournaments),
                    ),
                )
                run_id = cursor.fetchone()[0]

                match_ids = [
                    str(match["id"])
                    for event in tournaments
                    for match in event.get("matches", [])
                ]
                if match_ids:
                    cursor.execute(
                        "DELETE FROM match_players WHERE match_id = ANY(%s)",
                        (match_ids,),
                    )

                for event in tournaments:
                    event_season = safe_int(event.get("season"))
                    season_id = get_or_create_season(
                        cursor, event_season
                    )
                    upsert_tournament(cursor, event, season_id)
                    for match in event.get("matches", []):
                        match_date = parse_match_date(match.get("date"))
                        match_season_id = get_or_create_season(
                            cursor, match_date.year if match_date else event_season
                        )
                        upsert_match(cursor, match, event["id"], match_season_id)
                        for game in match.get("maps", []):
                            upsert_game(cursor, game, match["id"], match_season_id)
                            for player in game.get("players", []):
                                upsert_player_stats(
                                    cursor, player, game, match, match_season_id
                                )
                cursor.execute(
                    """
                    UPDATE ingestion_runs
                    SET completed_at = now()
                    WHERE ingestion_run_id = %s
                    """,
                    (run_id,),
                )
    finally:
        connection.close()

    print(
        f"Imported {len(tournaments)} tier-one events from {snapshot_path.name}."
    )


def main():
    parser = argparse.ArgumentParser(description="Import a VLR tier-one JSON snapshot.")
    parser.add_argument("--input", help="Snapshot path; defaults to the newest raw snapshot.")
    args = parser.parse_args()
    import_snapshot(args.input)


if __name__ == "__main__":
    main()
