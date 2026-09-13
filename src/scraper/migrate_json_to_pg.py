import json
import psycopg2

DATABASE_CONFIG = {
    "dbname": "vct_db",
    "user": "postgres",
    "password": "kotoha19062007",
    "host": "localhost",
    "port": "5432",
}

def safe_int(val):
    if val is None or str(val).strip() == "":
        return None
    try:
        return int(str(val).replace("+","").strip())
    except ValueError:
        return None

def safe_float(val):
    if val is None or str(val).strip() == "":
        return None
    try:
        return float(str(val).strip())
    except ValueError:
        return None

def safe_percentage(val):
    if val is None or str(val).strip() == "":
        return None
    try:
        return float(str(val).replace("%","").strip())
    except ValueError:
        return None

def create_tables(curs):
    #create tables if they do not exist
    curs.execute("""
        CREATE TABLE IF NOT EXISTS tournaments (
            id VARCHAR(50) PRIMARY KEY,
            title VARCHAR(255) NOT NULL,
            url VARCHAR(500) NOT NULL,
            status VARCHAR(50) NOT NULL
        );
        CREATE TABLE IF NOT EXISTS matches (
            id VARCHAR(50) PRIMARY KEY,
            tournament_id VARCHAR(50) REFERENCES tournaments(id) ON DELETE CASCADE,
            url VARCHAR(500) NOT NULL,
            status VARCHAR(50),
            format VARCHAR(50),
            team1 VARCHAR(100),
            team2 VARCHAR(100),
            team1_score INT,
            team2_score INT,
            match_date TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS games (
            id VARCHAR(50) PRIMARY KEY,
            match_id VARCHAR(50) REFERENCES matches(id) ON DELETE CASCADE,
            map_name VARCHAR(100),
            team1_score INT,
            team2_score INT
        );
        CREATE TABLE IF NOT EXISTS player_stats (
            id SERIAL PRIMARY KEY,
            game_id VARCHAR(50) REFERENCES games(id) ON DELETE CASCADE,
            player_name VARCHAR(100) NOT NULL,
            team VARCHAR(100),
            nationality VARCHAR(100),
            agent VARCHAR(50),
            rating NUMERIC(4, 2),
            acs INT,
            kills INT,
            deaths INT,
            assists INT,
            kd_diff INT,
            kast_percentage NUMERIC(5, 2),
            adr INT,
            headshot_percentage NUMERIC(5, 2),
            first_kills INT,
            first_deaths INT,
            CONSTRAINT unique_game_player UNIQUE (game_id, player_name)
        );
    """)

def upsert_tournament(curs, tournament):
    curs.execute("""
        INSERT INTO tournaments (id, title, url, status)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (id) DO UPDATE SET
            title = EXCLUDED.title,
            url = EXCLUDED.url,
            status = EXCLUDED.status;
    """, (tournament["id"], tournament["title"], tournament["url"], tournament["status"]))


def upsert_match(curs, match, tournament_id):
    team1_score = safe_int(match.get("team1_score"))
    team2_score = safe_int(match.get("team2_score"))
    match_date = match.get("date")

    curs.execute("""
        INSERT INTO matches (id, tournament_id, url, status, format, team1, team2, team1_score, team2_score, match_date)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO UPDATE SET
            tournament_id = EXCLUDED.tournament_id,
            url = EXCLUDED.url,
            status = EXCLUDED.status,
            format = EXCLUDED.format,
            team1 = EXCLUDED.team1,
            team2 = EXCLUDED.team2,
            team1_score = EXCLUDED.team1_score,
            team2_score = EXCLUDED.team2_score,
            match_date = EXCLUDED.match_date;
    """, (
        match["id"], 
        tournament_id, 
        match["url"], 
        match["status"], 
        match.get("format"), 
        match.get("team1"), 
        match.get("team2"), 
        team1_score, 
        team2_score,
        match_date
    ))


def upsert_game(curs, game, match_id):
    game_team1_score = safe_int(game.get("team1_score"))
    game_team2_score = safe_int(game.get("team2_score"))

    curs.execute("""
        INSERT INTO games (id, match_id, map_name, team1_score, team2_score)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (id) DO UPDATE SET
            match_id = EXCLUDED.match_id,
            map_name = EXCLUDED.map_name,
            team1_score = EXCLUDED.team1_score,
            team2_score = EXCLUDED.team2_score;
    """, (
        game["game_id"], 
        match_id, 
        game.get("map_name"), 
        game_team1_score, 
        game_team2_score
    ))


def upsert_player_stats(curs, player, game_id):
    rating = safe_float(player.get("rating"))
    acs = safe_int(player.get("acs"))
    kills = safe_int(player.get("kills"))
    deaths = safe_int(player.get("deaths"))
    assists = safe_int(player.get("assists"))
    kd_diff = safe_int(player.get("kd_diff"))
    kast = safe_percentage(player.get("kast"))
    adr = safe_int(player.get("adr"))
    hsp = safe_percentage(player.get("headshot_percentage"))
    fk = safe_int(player.get("first_kills"))
    fd = safe_int(player.get("first_deaths"))

    curs.execute("""
        INSERT INTO player_stats (
            game_id, player_name, team, nationality, agent, rating, acs, kills, 
            deaths, assists, kd_diff, kast_percentage, adr, headshot_percentage, 
            first_kills, first_deaths
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (game_id, player_name) DO UPDATE SET
            team = EXCLUDED.team,
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
            first_deaths = EXCLUDED.first_deaths;
    """, (
        game_id,
        player.get("name"),
        player.get("team"),
        player.get("nationality"),
        player.get("agent"),
        rating,
        acs,
        kills,
        deaths,
        assists,
        kd_diff,
        kast,
        adr,
        hsp,
        fk,
        fd
    ))

def migrate():
    with open("data/data.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    conn = psycopg2.connect(**DATABASE_CONFIG)
    curs = conn.cursor()

    try: 
        print("Connected to PostgreSQL successfully!")
        
        create_tables(curs)

        for tournament in data:
            print(f"Updating tournament: {tournament['title']}")
            upsert_tournament(curs, tournament)

            for match in tournament.get("matches", []):
                print(f"  -> Updating match: {match['id']}")
                upsert_match(curs, match, tournament["id"])

                for game in match.get("maps", []):
                    upsert_game(curs, game, match["id"])

                    for player in game.get("players", []):
                        upsert_player_stats(curs, player, game["game_id"])
                   
        conn.commit()
        print("Migration complete!")
    
    except Exception as e:
        conn.rollback()
        print(f"Error occurred during migration: {e}")
        raise e

    finally:
        curs.close()
        conn.close()

if __name__ == "__main__":
    migrate()