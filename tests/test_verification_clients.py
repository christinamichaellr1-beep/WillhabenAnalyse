"""Tests for verification API clients — no real HTTP calls."""
from __future__ import annotations
import datetime
import unittest
from unittest.mock import MagicMock, patch

import requests


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------

def _make_response(json_data, status_code=200):
    """Return a mock requests.Response with .json() and .raise_for_status()."""
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.json.return_value = json_data
    mock_resp.raise_for_status = MagicMock()  # no-op by default
    return mock_resp


# ---------------------------------------------------------------------------
# EventCandidate dataclass
# ---------------------------------------------------------------------------

class TestEventCandidateDataclass(unittest.TestCase):
    def test_event_candidate_dataclass(self):
        from verification.clients.base import EventCandidate

        ec = EventCandidate(event_name="Test Event")
        self.assertEqual(ec.event_name, "Test Event")
        self.assertIsNone(ec.event_datum)
        self.assertIsNone(ec.venue)
        self.assertIsNone(ec.stadt)
        self.assertEqual(ec.source, "")
        self.assertEqual(ec.confidence_score, 0.0)
        self.assertEqual(ec.raw, {})

        ec2 = EventCandidate(
            event_name="Concert",
            event_datum=datetime.date(2026, 6, 1),
            venue="Wiener Stadthalle",
            stadt="Wien",
            source="test",
            confidence_score=0.9,
            raw={"key": "val"},
        )
        self.assertEqual(ec2.event_datum, datetime.date(2026, 6, 1))
        self.assertEqual(ec2.confidence_score, 0.9)


# ---------------------------------------------------------------------------
# BaseClient ABC
# ---------------------------------------------------------------------------

class TestBaseClientIsAbstract(unittest.TestCase):
    def test_base_client_is_abstract(self):
        from verification.clients.base import BaseClient
        import abc

        self.assertTrue(issubclass(BaseClient, abc.ABC))
        with self.assertRaises(TypeError):
            BaseClient()  # type: ignore[abstract]


# ---------------------------------------------------------------------------
# WikidataClient
# ---------------------------------------------------------------------------

WIKIDATA_VALID_RESPONSE = {
    "results": {
        "bindings": [
            {
                "itemLabel": {"value": "Test Concert"},
                "dateLabel": {"value": "2026-06-01T00:00:00Z"},
            }
        ]
    }
}


class TestWikidataClient(unittest.TestCase):
    def test_wikidata_search_returns_candidates(self):
        from verification.clients.wikidata import WikidataClient

        with patch("requests.get", return_value=_make_response(WIKIDATA_VALID_RESPONSE)):
            client = WikidataClient()
            results = client.search("Test Concert")

        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[0].event_name, "Test Concert")
        self.assertEqual(results[0].source, "wikidata")
        self.assertEqual(results[0].confidence_score, 0.6)
        self.assertEqual(results[0].event_datum, datetime.date(2026, 6, 1))

    def test_wikidata_search_http_error_returns_empty(self):
        from verification.clients.wikidata import WikidataClient

        with patch("requests.get", side_effect=requests.RequestException("timeout")):
            client = WikidataClient()
            results = client.search("Test Concert")

        self.assertEqual(results, [])


# ---------------------------------------------------------------------------
# MusicBrainzClient
# ---------------------------------------------------------------------------

MB_VALID_RESPONSE = {
    "artists": [
        {"name": "Rammstein", "score": 100},
        {"name": "Ramstein", "score": 60},
    ]
}


class TestMusicBrainzClient(unittest.TestCase):
    def test_musicbrainz_search_returns_candidates(self):
        from verification.clients.musicbrainz import MusicBrainzClient

        with patch("requests.get", return_value=_make_response(MB_VALID_RESPONSE)):
            client = MusicBrainzClient()
            results = client.search("Rammstein")

        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[0].event_name, "Rammstein")
        self.assertAlmostEqual(results[0].confidence_score, 1.0)
        self.assertEqual(results[1].confidence_score, 0.6)
        self.assertEqual(results[0].source, "musicbrainz")

    def test_musicbrainz_search_http_error_returns_empty(self):
        from verification.clients.musicbrainz import MusicBrainzClient

        with patch("requests.get", side_effect=requests.RequestException("connection error")):
            client = MusicBrainzClient()
            results = client.search("Rammstein")

        self.assertEqual(results, [])


# ---------------------------------------------------------------------------
# SongkickClient
# ---------------------------------------------------------------------------

SK_VALID_RESPONSE = {
    "resultsPage": {
        "results": {
            "event": [
                {
                    "displayName": "Rammstein live",
                    "start": {"date": "2026-07-10"},
                    "venue": {
                        "displayName": "Ernst-Happel-Stadion",
                        "metroArea": {"displayName": "Wien"},
                    },
                }
            ]
        }
    }
}


class TestSongkickClient(unittest.TestCase):
    def test_songkick_not_available_without_key(self):
        from verification.clients.songkick import SongkickClient
        import os

        # Ensure env var not set
        os.environ.pop("SONGKICK_API_KEY", None)
        client = SongkickClient(api_key=None)
        self.assertFalse(client.is_available())
        results = client.search("Rammstein")
        self.assertEqual(results, [])

    def test_songkick_search_with_key(self):
        from verification.clients.songkick import SongkickClient
        import os

        os.environ["SONGKICK_API_KEY"] = "test-key-123"
        try:
            with patch("requests.get", return_value=_make_response(SK_VALID_RESPONSE)):
                client = SongkickClient()
                self.assertTrue(client.is_available())
                results = client.search("Rammstein", stadt="Wien")

            self.assertGreaterEqual(len(results), 1)
            self.assertEqual(results[0].event_name, "Rammstein live")
            self.assertEqual(results[0].event_datum, datetime.date(2026, 7, 10))
            self.assertEqual(results[0].venue, "Ernst-Happel-Stadion")
            self.assertEqual(results[0].stadt, "Wien")
            self.assertEqual(results[0].source, "songkick")
        finally:
            os.environ.pop("SONGKICK_API_KEY", None)


# ---------------------------------------------------------------------------
# BandsintownClient
# ---------------------------------------------------------------------------

BIT_VALID_RESPONSE = [
    {
        "datetime": "2026-08-15T20:00:00",
        "venue": {"name": "Gasometer", "city": "Wien"},
    },
    {
        "datetime": "2026-09-01T19:00:00",
        "venue": {"name": "Arena Wien", "city": "Wien"},
    },
]


class TestBandsintownClient(unittest.TestCase):
    def test_bandsintown_not_available_without_key(self):
        from verification.clients.bandsintown import BandsintownClient
        import os

        os.environ.pop("BANDSINTOWN_APP_ID", None)
        client = BandsintownClient(api_key=None)
        self.assertFalse(client.is_available())

    def test_bandsintown_search_returns_candidates(self):
        from verification.clients.bandsintown import BandsintownClient
        import os

        os.environ["BANDSINTOWN_APP_ID"] = "test-app-id"
        try:
            with patch("requests.get", return_value=_make_response(BIT_VALID_RESPONSE)):
                client = BandsintownClient()
                self.assertTrue(client.is_available())
                results = client.search("Bilderbuch")

            self.assertGreaterEqual(len(results), 1)
            self.assertEqual(results[0].event_name, "Bilderbuch")
            self.assertEqual(results[0].event_datum, datetime.date(2026, 8, 15))
            self.assertEqual(results[0].venue, "Gasometer")
            self.assertEqual(results[0].stadt, "Wien")
            self.assertEqual(results[0].source, "bandsintown")
            self.assertAlmostEqual(results[0].confidence_score, 0.75)
        finally:
            os.environ.pop("BANDSINTOWN_APP_ID", None)


if __name__ == "__main__":
    unittest.main()
