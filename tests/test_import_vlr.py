import unittest
from datetime import datetime, timezone

from src.db.import_vlr import (
    canonical_team_name,
    get_or_create_season,
    normalize_name,
    parse_match_date,
    resolve_match_player_team,
    safe_float,
    safe_int,
    upsert_tournament,
)


class RecordingCursor:
    def __init__(self):
        self.statement = None
        self.parameters = None

    def execute(self, statement, parameters):
        self.statement = statement
        self.parameters = parameters


class ImportVlrTests(unittest.TestCase):
    def test_parses_vlr_unix_and_iso_dates_as_utc(self):
        unix_date = parse_match_date("1762032000")
        iso_date = parse_match_date("2026-11-02T10:00:00Z")
        self.assertEqual(unix_date.tzinfo, timezone.utc)
        self.assertEqual(iso_date, datetime(2026, 11, 2, 10, tzinfo=timezone.utc))

    def test_invalid_date_is_not_silently_replaced(self):
        self.assertIsNone(parse_match_date("not-a-date"))

    def test_safe_numeric_parsing_preserves_stat_precision(self):
        self.assertEqual(safe_int("+12"), 12)
        self.assertEqual(safe_float("143.75"), 143.75)
        self.assertIsNone(safe_float("NaN"))
        self.assertIsNone(safe_int("unknown"))

    def test_alias_normalization_is_stable(self):
        self.assertEqual(normalize_name("Paper Rex"), "paper rex")
        self.assertEqual(normalize_name("A & B"), "a and b")
        self.assertEqual(normalize_name(None), "")

    def test_team_tags_and_full_names_share_canonical_identity(self):
        self.assertEqual(canonical_team_name("PRX"), "paper rex")
        self.assertEqual(canonical_team_name("Paper Rex"), "paper rex")
        self.assertEqual(canonical_team_name("LOUD"), "loud")
        self.assertEqual(canonical_team_name("NS"), "nongshim redforce")
        self.assertEqual(canonical_team_name("Nongshin RedForce"), "nongshim redforce")
        self.assertEqual(
            canonical_team_name("Guangzhou Huadu Bilibili Gaming(Bilibili Gaming)"),
            "bilibili gaming",
        )
        self.assertEqual(
            canonical_team_name("Wuxi Titan Esports Club(Titan Esports Club)"),
            "titan esports club",
        )
        self.assertEqual(canonical_team_name("KRU"), "krü esports")
        self.assertEqual(canonical_team_name("kr esports"), "krü esports")
        self.assertEqual(canonical_team_name("leviat n"), "leviatán")

    def test_missing_season_is_not_replaced_with_a_guessed_year(self):
        cursor = RecordingCursor()
        self.assertIsNone(get_or_create_season(cursor, None))
        self.assertIsNone(cursor.statement)

    def test_resolves_vlr_team_tags_to_match_participants(self):
        players = [
            {"team": "UR"} for _ in range(5)
        ] + [
            {"team": "VLG"} for _ in range(5)
        ]
        match = {
            "team1": "Unsettled Resentment",
            "team1_url": "https://www.vlr.gg/team/1/example",
            "team1_logo_url": "https://owcdn.net/img/team1.png",
            "team2": "Victory No Limits Gaming",
        }

        self.assertEqual(
            resolve_match_player_team(players[0], {"players": players}, match),
            {
                "name": "Unsettled Resentment",
                "source_url": "https://www.vlr.gg/team/1/example",
                "logo_url": "https://owcdn.net/img/team1.png",
            },
        )
        self.assertEqual(
            resolve_match_player_team(players[-1], {"players": players}, match)["name"],
            "Victory No Limits Gaming",
        )

    def test_unreliable_player_grouping_does_not_guess_a_match_team(self):
        game_players = [{"team": "UR"} for _ in range(4)] + [
            {"team": "VLG"} for _ in range(6)
        ]
        self.assertIsNone(
            resolve_match_player_team(
                game_players[0],
                {"players": game_players},
                {"team1": "Unsettled Resentment", "team2": "Victory No Limits Gaming"},
            )
        )

    def test_tournament_upsert_preserves_source_calendar_dates(self):
        cursor = RecordingCursor()
        upsert_tournament(
            cursor,
            {
                "id": "3175",
                "title": "VCT 2027: EMEA Kickoff - Europe Qualifier",
                "url": "https://www.vlr.gg/event/3175/test",
                "status": "upcoming",
                "region": "EMEA",
                "logo_url": None,
                "start_date": "2026-11-05",
                "end_date": "2026-12-06",
            },
            7,
        )
        self.assertEqual(len(cursor.parameters), 10)
        self.assertEqual(cursor.parameters[5], "tier1")
        self.assertEqual(cursor.parameters[-2:], ("2026-11-05", "2026-12-06"))


if __name__ == "__main__":
    unittest.main()
