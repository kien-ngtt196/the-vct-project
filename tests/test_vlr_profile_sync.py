import unittest
from unittest.mock import patch

from src.db.sync_vlr_profiles import _save_event_results


class VlrProfileSyncTests(unittest.TestCase):
    @patch("src.db.sync_vlr_profiles._request", return_value=None)
    def test_unavailable_event_page_returns_failure_with_expected_shape(self, _):
        result = _save_event_results(
            cursor=None,
            event=("event-id", "Event title", "https://www.vlr.gg/event/1/event"),
            aliases={},
            source_urls={},
        )

        self.assertEqual(result, ({}, False))


if __name__ == "__main__":
    unittest.main()
