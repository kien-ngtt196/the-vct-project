def calculate_team_power(team_stats):
    ratings = []
    for stats in team_stats:
        match_count = int(stats["matches_played"])
        if match_count <= 0:
            continue

        matches_won = int(stats["matches_won"])
        matches_drawn = int(stats.get("matches_drawn", 0))
        map_count = int(stats["maps_played"])
        maps_won = int(stats["maps_won"])
        maps_drawn = int(stats.get("maps_drawn", 0))
        rounds_for = int(stats["rounds_for"])
        rounds_against = int(stats["rounds_against"])
        kills = int(stats.get("kills", 0))
        deaths = int(stats.get("deaths", 0))
        weighted_match_count = float(stats.get("weighted_matches_played", match_count))
        weighted_match_points = float(
            stats.get("weighted_match_points", matches_won + 0.5 * matches_drawn)
        )
        weighted_map_count = float(stats.get("weighted_maps_played", map_count))
        weighted_map_points = float(
            stats.get("weighted_map_points", maps_won + 0.5 * maps_drawn)
        )
        weighted_rounds_for = float(stats.get("weighted_rounds_for", rounds_for))
        weighted_rounds_against = float(
            stats.get("weighted_rounds_against", rounds_against)
        )
        weighted_kills = float(stats.get("weighted_kills", kills))
        weighted_deaths = float(stats.get("weighted_deaths", deaths))
        match_win_rate = (
            weighted_match_points / weighted_match_count
            if weighted_match_count
            else 0.5
        )
        map_win_rate = (
            weighted_map_points / weighted_map_count if weighted_map_count else 0.5
        )
        total_rounds = weighted_rounds_for + weighted_rounds_against
        round_strength = (
            (weighted_rounds_for - weighted_rounds_against) / total_rounds
            if total_rounds
            else 0.0
        )
        round_win_rate = 0.5 + 0.5 * round_strength
        recent_performance_rate = float(stats.get("recent_performance_rate", 0.5))
        opponent_strength_rate = float(stats.get("opponent_strength_rate", 0.5))
        kd_strength = (
            weighted_kills / (weighted_kills + weighted_deaths)
            if weighted_kills + weighted_deaths
            else 0.5
        )
        execution_score = (
            0.4 * map_win_rate
            + 0.4 * round_win_rate
            + 0.2 * kd_strength
        )
        base_power_score = 100 * (
            0.35 * match_win_rate
            + 0.25 * recent_performance_rate
            + 0.25 * execution_score
            + 0.15 * opponent_strength_rate
        )

        ratings.append(
            {
                **stats,
                "matches_played": match_count,
                "matches_won": matches_won,
                "matches_drawn": matches_drawn,
                "maps_played": map_count,
                "maps_won": maps_won,
                "maps_drawn": maps_drawn,
                "rounds_for": rounds_for,
                "rounds_against": rounds_against,
                "match_win_rate": round(match_win_rate, 4),
                "map_win_rate": round(map_win_rate, 4),
                "round_win_rate": round(round_win_rate, 4),
                "recent_performance_rate": round(recent_performance_rate, 4),
                "opponent_strength_rate": round(opponent_strength_rate, 4),
                "kills": kills,
                "deaths": deaths,
                "kd_strength": round(kd_strength, 4),
                "execution_score": round(execution_score, 4),
                "round_differential": rounds_for - rounds_against,
                "unscaled_power_score": round(base_power_score, 1),
                "power_score": base_power_score,
            }
        )

    highest_score = max(
        (team["power_score"] for team in ratings),
        default=0,
    )
    if highest_score > 0:
        for team in ratings:
            team["power_score"] = round(
                team["power_score"] / highest_score * 100,
                1,
            )

    return sorted(
        ratings,
        key=lambda team: (
            -team["power_score"],
            -team["matches_played"],
            team["name"].casefold(),
        ),
    )


def calculate_player_power(player_stats):
    ratings = []
    metric_weights = {
        "rating": (0.35, 1.2),
        "acs": (0.25, 300),
        "kast": (0.2, 100),
        "adr": (0.1, 150),
    }

    for stats in player_stats:
        maps_played = int(stats.get("maps_played", 0))
        if maps_played <= 0:
            continue

        components = {}
        for metric, (_, ceiling) in metric_weights.items():
            value = stats.get(metric)
            rate = (
                min(1.0, max(0.0, float(value) / ceiling))
                if value is not None
                else 0.5
            )
            components[metric] = rate

        kills = float(stats.get("kills") or 0)
        deaths = float(stats.get("deaths") or 0)
        kd_strength = kills / (kills + deaths) if kills + deaths else 0.5
        base_power_score = 100 * (
            sum(
                metric_weights[metric][0] * components[metric]
                for metric in metric_weights
            )
            + 0.1 * kd_strength
        )
        ratings.append(
            {
                **stats,
                "maps_played": maps_played,
                "kd_strength": round(kd_strength, 4),
                "unscaled_power_score": round(base_power_score, 1),
                "power_score": base_power_score,
            }
        )

    highest_score = max(
        (player["power_score"] for player in ratings),
        default=0,
    )
    if highest_score > 0:
        for player in ratings:
            player["power_score"] = round(
                player["power_score"] / highest_score * 100,
                1,
            )

    return sorted(
        ratings,
        key=lambda player: (
            -player["power_score"],
            -player["maps_played"],
            player["name"].casefold(),
        ),
    )
