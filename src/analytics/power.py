import re


TEAM_POWER_WEIGHTS = {
    "international_achievement": 0.40,
    "regional_achievement": 0.15,
    "season_results": 0.20,
    "recent_performance": 0.10,
    "in_game_execution": 0.10,
    "opponent_strength": 0.05,
}
PLACEMENT_POINTS = {
    "champions": (36, 29, 22, 14, 8),
    "masters": (22, 17, 13, 8, 4),
    "regional": (10, 7, 4, 2, 0),
}
PLAYER_POWER_POINTS = {
    "season_performance": 65,
    "season_maps": 10,
    "international_performance": 10,
    "tournament_finishes": 15,
}
PLAYER_METRIC_WEIGHTS = {
    "rating": (0.35, 1.2),
    "acs": (0.25, 300),
    "kast": (0.2, 100),
    "adr": (0.1, 150),
    "kd_strength": (0.1, 1),
}
PLAYER_SAMPLE_PRIOR_MAPS = 20
PLAYER_VOLUME_CAP = 60
PLAYER_INTERNATIONAL_PRIOR_MAPS = 6
PLAYER_INTERNATIONAL_RATING_CEILING = 1.25
PLAYER_EVENT_WIN_POINTS = {"champions": 12, "masters": 8, "regional": 3}
PLAYER_EVENT_FULL_CREDIT_MAPS = 5
PLAYER_FINISHES_COUNT = 3


def placement_rank(text):
    match = re.fullmatch(
        r"\s*(\d+)(?:st|nd|rd|th)?(?:\s*[-–—]\s*(\d+)(?:st|nd|rd|th)?)?\s*",
        text or "", re.IGNORECASE,
    )
    return int(match[2] or match[1]) if match else None


def achievement_points(event_kind, placement):
    rank = placement_rank(placement)
    points = PLACEMENT_POINTS[event_kind]
    for limit, value in zip((1, 2, 4, 8), points):
        if rank is not None and 0 < rank <= limit:
            return value
    return points[-1]


def shrink_rate(rate, count, prior):
    return (rate * count + 0.5 * prior) / (count + prior)


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
        components = {
            "international_achievement": stats.get("international_achievement", 0),
            "regional_achievement": stats.get("regional_achievement", 0),
            "season_results": shrink_rate(match_win_rate, match_count, 5),
            "recent_performance": shrink_rate(recent_performance_rate, min(match_count, 5), 3),
            "in_game_execution": execution_score,
            "opponent_strength": opponent_strength_rate,
        }
        base_power_score = 100 * sum(
            TEAM_POWER_WEIGHTS[key] * value for key, value in components.items()
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
                "score_breakdown": {
                    key: round(100 * TEAM_POWER_WEIGHTS[key] * value, 2)
                    for key, value in components.items()
                },
                "round_differential": rounds_for - rounds_against,
                "unscaled_power_score": round(base_power_score, 1),
                "power_score": round(base_power_score, 1),
            }
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
    for stats in player_stats:
        maps_played = int(stats.get("maps_played", 0))
        if maps_played <= 0:
            continue

        kills = float(stats.get("kills") or 0)
        deaths = float(stats.get("deaths") or 0)
        kd_strength = kills / (kills + deaths) if kills + deaths else 0.5
        metrics = {**stats, "kd_strength": kd_strength}
        performance = sum(
            weight * min(1.0, max(0.0, float(metrics[metric]) / ceiling))
            if metrics.get(metric) is not None else weight * 0.5
            for metric, (weight, ceiling) in PLAYER_METRIC_WEIGHTS.items()
        )
        ratings.append((metrics, maps_played, performance))

    if not ratings:
        return []
    baseline = sum(maps * performance for _, maps, performance in ratings) / sum(
        maps for _, maps, _ in ratings
    )
    standings = []
    for player, maps, performance in ratings:
        prior = PLAYER_SAMPLE_PRIOR_MAPS
        adjusted = (maps * performance + prior * baseline) / (maps + prior)
        intl_maps = player.get("international_rated_maps", 0)
        intl_rating = float(player.get("weighted_international_rating") or 0)
        intl_rate = min(1.0, max(0.0, intl_rating / PLAYER_INTERNATIONAL_RATING_CEILING))
        event_points = {}
        for event in player.get("tournament_finishes", ()):
            event_id = event["event_id"]
            event_points[event_id] = max(event_points.get(event_id, 0), player_finish_points(event))
        components = {
            "season_performance": PLAYER_POWER_POINTS["season_performance"] * adjusted,
            "season_maps": PLAYER_POWER_POINTS["season_maps"] * min(1.0, maps / PLAYER_VOLUME_CAP),
            "international_performance": PLAYER_POWER_POINTS["international_performance"]
            * intl_rate * intl_maps / (intl_maps + PLAYER_INTERNATIONAL_PRIOR_MAPS),
            "tournament_finishes": min(
                PLAYER_POWER_POINTS["tournament_finishes"],
                sum(sorted(event_points.values(), reverse=True)[:PLAYER_FINISHES_COUNT]),
            ),
        }
        score = round(sum(components.values()), 1)
        standings.append({
            **player,
            "maps_played": maps,
            "kd_strength": round(player["kd_strength"], 4),
            "power_score": score,
            "unscaled_power_score": score,
            "power_components": {key: round(value, 2) for key, value in components.items()},
        })

    return sorted(
        standings,
        key=lambda player: (
            -player["power_score"],
            -player["maps_played"],
            player["name"].casefold(),
        ),
    )


def player_finish_points(event):
    kind = event["kind"]
    placement = event["placement"]
    rank = placement_rank(placement)
    if rank is None or rank <= 0:
        return 0
    maximum, *_, floor = PLACEMENT_POINTS[kind]
    finish = (achievement_points(kind, placement) - floor) / (maximum - floor)
    participation = min(1.0, event["maps"] / PLAYER_EVENT_FULL_CREDIT_MAPS)
    return PLAYER_EVENT_WIN_POINTS[kind] * finish * participation
