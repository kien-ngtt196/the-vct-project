import unittest
from unittest.mock import patch

from src.scraper import main as scraper


class ScraperTests(unittest.TestCase):
    @patch("src.scraper.main.get_event_details")
    def test_event_parser_marks_results_from_tier_one_feed(self, event_details):
        event_details.return_value = {
            "season": 2026,
            "logo_url": None,
            "region": None,
            "start_date": None,
            "end_date": None,
        }
        html = """
        <a class="event-item" href="/event/123/vct-2026">
          <span class="event-item-title">VCT 2026: Test Stage</span>
          <span class="event-item-desc-item-status">Completed</span>
        </a>
        """
        events = scraper.parse_tournaments(html)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["tier"], "tier1")
        self.assertEqual(events[0]["id"], "123")

    def test_event_dates_use_explicit_calendar_year_not_season_label(self):
        dates = scraper.parse_event_dates(
            "VCT 2027 EMEA Kickoff Dates Nov 5 – Dec 6, 2026"
        )
        self.assertEqual(dates, ("2026-11-05", "2026-12-06"))

    def test_event_date_range_can_omit_repeated_month(self):
        dates = scraper.parse_event_dates("Dates Mar 1—16, 2026")
        self.assertEqual(dates, ("2026-03-01", "2026-03-16"))

    def test_scheduled_match_is_kept_without_player_stats(self):
        html = """
        <div class="match-header-vs-note">Scheduled</div>
        <div class="match-header-vs-note">Best of 3</div>
        <a class="match-header-link mod-1">
          <span class="wf-title-med">Team Alpha</span>
        </a>
        <a class="match-header-link mod-2">
          <span class="wf-title-med">Team Beta</span>
        </a>
        <span class="match-header-vs-score-winner"></span>
        """
        with patch.object(scraper, "safe_get", return_value=type("Response", (), {"text": html})()):
            match = scraper.parse_match("https://www.vlr.gg/987/test-match")
        self.assertIsNotNone(match)
        self.assertEqual(match["status"], "scheduled")
        self.assertEqual(match["id"], "987")
        self.assertEqual(match["maps"], [])

    def test_match_links_are_deduplicated(self):
        html = """
        <a href="/123/match-one">first</a>
        <a href="/123/match-one">duplicate</a>
        <a href="/456/match-two">second</a>
        """
        with patch.object(scraper, "safe_get", return_value=type("Response", (), {"text": html})()):
            links = scraper.get_match_links("https://www.vlr.gg/event/matches/100/test")
        self.assertEqual(
            links,
            ["https://www.vlr.gg/123/match-one", "https://www.vlr.gg/456/match-two"],
        )


if __name__ == "__main__":
    unittest.main()
