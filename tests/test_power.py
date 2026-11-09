import unittest

from src.analytics.power import achievement_points, calculate_player_power, calculate_team_power


class TeamPowerTests(unittest.TestCase):
    def test_neutral_performance_without_achievement_scores_22_5(self):
        teams = calculate_team_power(
            [
                {
                    "id": 1,
                    "name": "Team Alpha",
                    "matches_played": 4,
                    "matches_won": 2,
                    "matches_drawn": 0,
                    "maps_played": 10,
                    "maps_won": 5,
                    "maps_drawn": 0,
                    "rounds_for": 100,
                    "rounds_against": 100,
                }
            ]
        )
        self.assertEqual(teams[0]["unscaled_power_score"], 22.5)
        self.assertEqual(teams[0]["power_score"], teams[0]["unscaled_power_score"])
        self.assertEqual(teams[0]["round_differential"], 0)

    def test_placement_points_distinguish_finishes_from_group_seeds(self):
        self.assertEqual(achievement_points("champions", "1st"), 36)
        self.assertEqual(achievement_points("champions", "7th–8th"), 14)
        self.assertEqual(achievement_points("champions", "Group A (#1)"), 8)
        self.assertEqual(achievement_points("regional", "Group A (#1)"), 0)

    def test_international_achievement_outweighs_a_short_win_streak(self):
        stats = {
            "matches_played": 3, "matches_won": 3, "maps_played": 6,
            "maps_won": 6, "rounds_for": 78, "rounds_against": 36,
            "recent_performance_rate": 1,
        }
        teams = calculate_team_power([
            {**stats, "name": "Regional streak"},
            {
                **stats, "name": "International finalist", "matches_played": 20,
                "matches_won": 10, "maps_played": 40, "maps_won": 20,
                "rounds_for": 400, "rounds_against": 400,
                "recent_performance_rate": 0.5, "international_achievement": 0.5,
            },
        ])
        self.assertEqual(teams[0]["name"], "International finalist")

    def test_draws_count_as_half_a_win(self):
        teams = calculate_team_power(
            [
                {
                    "id": 1,
                    "name": "Team Alpha",
                    "matches_played": 4,
                    "matches_won": 2,
                    "matches_drawn": 1,
                    "maps_played": 0,
                    "maps_won": 0,
                    "maps_drawn": 0,
                    "rounds_for": 0,
                    "rounds_against": 0,
                }
            ]
        )
        self.assertEqual(teams[0]["match_win_rate"], 0.625)
        self.assertEqual(teams[0]["map_win_rate"], 0.5)
        self.assertEqual(teams[0]["unscaled_power_score"], 23.6)
        self.assertEqual(teams[0]["power_score"], teams[0]["unscaled_power_score"])

    def test_recent_form_execution_and_opponents_use_documented_weights(self):
        teams = calculate_team_power(
            [
                {
                    "id": 1,
                    "name": "Team Alpha",
                    "matches_played": 10,
                    "matches_won": 5,
                    "matches_drawn": 0,
                    "maps_played": 10,
                    "maps_won": 8,
                    "maps_drawn": 0,
                    "rounds_for": 120,
                    "rounds_against": 80,
                    "recent_performance_rate": 1.0,
                    "opponent_strength_rate": 1.0,
                    "kills": 60,
                    "deaths": 40,
                }
            ]
        )
        self.assertEqual(teams[0]["execution_score"], 0.68)
        self.assertEqual(teams[0]["kd_strength"], 0.6)
        self.assertEqual(teams[0]["unscaled_power_score"], 29.9)
        self.assertEqual(teams[0]["power_score"], teams[0]["unscaled_power_score"])

    def test_event_weighted_results_and_execution_use_weighted_totals(self):
        teams = calculate_team_power(
            [
                {
                    "id": 1,
                    "name": "Team Alpha",
                    "matches_played": 2,
                    "matches_won": 1,
                    "matches_drawn": 0,
                    "maps_played": 3,
                    "maps_won": 2,
                    "maps_drawn": 0,
                    "rounds_for": 60,
                    "rounds_against": 40,
                    "weighted_matches_played": 4,
                    "weighted_match_points": 2,
                    "weighted_maps_played": 4,
                    "weighted_map_points": 3,
                    "weighted_rounds_for": 120,
                    "weighted_rounds_against": 80,
                    "weighted_kills": 60,
                    "weighted_deaths": 40,
                }
            ]
        )
        self.assertEqual(teams[0]["matches_played"], 2)
        self.assertEqual(teams[0]["match_win_rate"], 0.5)
        self.assertEqual(teams[0]["map_win_rate"], 0.75)
        self.assertEqual(teams[0]["execution_score"], 0.66)
        self.assertEqual(teams[0]["unscaled_power_score"], 24.1)
        self.assertEqual(teams[0]["power_score"], teams[0]["unscaled_power_score"])

    def test_rankings_are_sorted_by_score_then_sample_size(self):
        teams = calculate_team_power(
            [
                {
                    "id": 2,
                    "name": "Smaller Sample",
                    "matches_played": 2,
                    "matches_won": 1,
                    "maps_played": 2,
                    "maps_won": 1,
                    "rounds_for": 20,
                    "rounds_against": 20,
                },
                {
                    "id": 1,
                    "name": "Larger Sample",
                    "matches_played": 4,
                    "matches_won": 2,
                    "maps_played": 4,
                    "maps_won": 2,
                    "rounds_for": 40,
                    "rounds_against": 40,
                },
                {
                    "id": 3,
                    "name": "High Power",
                    "matches_played": 4,
                    "matches_won": 4,
                    "maps_played": 8,
                    "maps_won": 8,
                    "rounds_for": 104,
                    "rounds_against": 72,
                },
            ]
        )
        self.assertEqual([team["name"] for team in teams], [
            "High Power",
            "Larger Sample",
            "Smaller Sample",
        ])
        self.assertEqual(teams[0]["power_score"], teams[0]["unscaled_power_score"])
        self.assertLess(teams[1]["power_score"], teams[0]["power_score"])

    def test_player_power_displays_sample_adjusted_points(self):
        players = calculate_player_power(
            [
                {
                    "id": 1,
                    "name": "Player One",
                    "maps_played": 10,
                    "rating": 1.2,
                    "acs": 300,
                    "kast": 100,
                    "adr": 150,
                    "kills": 60,
                    "deaths": 40,
                },
                {
                    "id": 2,
                    "name": "Player Two",
                    "maps_played": 10,
                    "rating": 0.6,
                    "acs": 150,
                    "kast": 50,
                    "adr": 75,
                    "kills": 40,
                    "deaths": 60,
                },
            ]
        )
        self.assertEqual(players[0]["name"], "Player One")
        self.assertEqual(players[0]["power_score"], 84.2)
        self.assertEqual(players[1]["power_score"], 60.8)
        self.assertEqual(players[1]["kd_strength"], 0.4)

    def test_teams_without_matches_are_not_ranked(self):
        self.assertEqual(
            calculate_team_power(
                [
                    {
                        "id": 1,
                        "name": "No Results",
                        "matches_played": 0,
                        "matches_won": 0,
                        "maps_played": 0,
                        "maps_won": 0,
                        "rounds_for": 0,
                        "rounds_against": 0,
                    }
                ]
            ),
            [],
        )


if __name__ == "__main__":
    unittest.main()
