import unittest

from src.analytics.power import calculate_player_power, calculate_team_power


class TeamPowerTests(unittest.TestCase):
    def test_equal_performance_scores_fifty(self):
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
        self.assertEqual(teams[0]["unscaled_power_score"], 50.0)
        self.assertEqual(teams[0]["power_score"], 100.0)
        self.assertEqual(teams[0]["round_differential"], 0)

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
        self.assertEqual(teams[0]["unscaled_power_score"], 54.4)
        self.assertEqual(teams[0]["power_score"], 100.0)

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
        self.assertEqual(teams[0]["unscaled_power_score"], 74.5)
        self.assertEqual(teams[0]["power_score"], 100.0)

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
        self.assertEqual(teams[0]["unscaled_power_score"], 54.0)
        self.assertEqual(teams[0]["power_score"], 100.0)

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
        self.assertEqual(teams[0]["power_score"], 100.0)
        self.assertLess(teams[1]["power_score"], 100.0)

    def test_player_power_is_normalized_to_the_top_player(self):
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
        self.assertEqual(players[0]["power_score"], 100.0)
        self.assertEqual(players[1]["power_score"], 51.0)
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
