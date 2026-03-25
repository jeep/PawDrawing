"""Tests for library management routes."""

import unittest
from unittest.mock import MagicMock, patch

from app import create_app
from session_keys import SK


class LibraryTestBase(unittest.TestCase):
    """Base class with helper setup for library management tests."""

    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

        # Standard session data for authenticated user with a library selected
        self.session_data = {
            SK.TTE_SESSION_ID: "test-session-id",
            SK.TTE_USERNAME: "testuser",
            SK.TTE_USER_ID: "user-001",
            SK.LIBRARY_ID: "lib-001",
            SK.LIBRARY_NAME: "Test Library",
            SK.CONVENTION_ID: "conv-001",
            SK.CONVENTION_NAME: "Test Convention",
        }

    def _set_session(self, **extra):
        with self.client.session_transaction() as sess:
            for k, v in self.session_data.items():
                sess[k] = v
            for k, v in extra.items():
                sess[k] = v


class TestDashboard(LibraryTestBase):

    def test_dashboard_requires_login(self):
        resp = self.client.get("/library-mgmt/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.headers["Location"])

    def test_dashboard_requires_library(self):
        with self.client.session_transaction() as sess:
            sess[SK.TTE_SESSION_ID] = "test-session"
        resp = self.client.get("/library-mgmt/", follow_redirects=False)
        self.assertEqual(resp.status_code, 302)

    def test_dashboard_renders_with_library(self):
        self._set_session(**{SK.CACHED_GAMES: [
            {"id": "g1", "name": "Game 1", "is_checked_out": 0, "is_play_to_win": 1},
            {"id": "g2", "name": "Game 2", "is_checked_out": 1, "is_play_to_win": 1},
        ]})
        resp = self.client.get("/library-mgmt/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Test Library", resp.data)
        self.assertIn(b"Dashboard", resp.data)

    def test_dashboard_shows_stats(self):
        self._set_session(**{SK.CACHED_GAMES: [
            {"id": "g1", "is_checked_out": 0, "is_play_to_win": 1},
            {"id": "g2", "is_checked_out": 1, "is_play_to_win": 1},
            {"id": "g3", "is_checked_out": 0, "is_play_to_win": 0},
        ]})
        resp = self.client.get("/library-mgmt/")
        data = resp.data.decode()
        # Total games = 3, checked out = 1, P2W = 2
        self.assertIn("3", data)  # total
        self.assertIn("1", data)  # checked out


class TestSwitchMode(LibraryTestBase):

    def test_switch_to_library_mode(self):
        self._set_session()
        resp = self.client.post("/library-mgmt/switch-mode",
                                data={"mode": "library"})
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/library-mgmt", resp.headers["Location"])
        with self.client.session_transaction() as sess:
            self.assertEqual(sess[SK.APP_MODE], "library")

    def test_switch_to_drawing_mode(self):
        self._set_session()
        resp = self.client.post("/library-mgmt/switch-mode",
                                data={"mode": "drawing"})
        self.assertEqual(resp.status_code, 302)
        with self.client.session_transaction() as sess:
            self.assertEqual(sess[SK.APP_MODE], "drawing")

    def test_switch_mode_invalid_defaults_drawing(self):
        self._set_session()
        resp = self.client.post("/library-mgmt/switch-mode",
                                data={"mode": "invalid"})
        with self.client.session_transaction() as sess:
            self.assertEqual(sess[SK.APP_MODE], "drawing")


class TestBadgeLookup(LibraryTestBase):

    def test_badge_lookup_requires_badge_number(self):
        self._set_session()
        resp = self.client.get("/library-mgmt/badge-lookup")
        self.assertEqual(resp.status_code, 400)

    def test_badge_lookup_from_cache(self):
        self._set_session(**{SK.PERSON_CACHE: {
            "123": {"name": "Alice", "badge_id": "b-001", "user_id": None}
        }})
        resp = self.client.get("/library-mgmt/badge-lookup?badge_number=123")
        data = resp.get_json()
        self.assertEqual(data["name"], "Alice")
        self.assertEqual(data["source"], "cache")

    @patch("routes.library.checkout._get_client")
    def test_badge_lookup_from_tte(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.search_badges.return_value = [
            {"name_full": "Bob Smith", "id": "badge-002", "user_id": "u-002"}
        ]
        mock_get_client.return_value = mock_client

        self._set_session()
        resp = self.client.get("/library-mgmt/badge-lookup?badge_number=456")
        data = resp.get_json()
        self.assertEqual(data["name"], "Bob Smith")
        self.assertEqual(data["source"], "tte")

    @patch("routes.library.checkout._get_client")
    def test_badge_lookup_not_found(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.search_badges.return_value = []
        mock_get_client.return_value = mock_client

        self._set_session()
        resp = self.client.get("/library-mgmt/badge-lookup?badge_number=999")
        self.assertEqual(resp.status_code, 404)

    def test_badge_lookup_no_convention(self):
        """Without convention, should return error when not in cache."""
        with self.client.session_transaction() as sess:
            sess[SK.TTE_SESSION_ID] = "test-session"
            sess[SK.LIBRARY_ID] = "lib-001"
            sess[SK.LIBRARY_NAME] = "Test Library"
        resp = self.client.get("/library-mgmt/badge-lookup?badge_number=123")
        self.assertEqual(resp.status_code, 400)


class TestCheckout(LibraryTestBase):

    @patch("routes.library.checkout._get_client")
    def test_checkout_success(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.create_checkout.return_value = {"id": "checkout-001"}
        mock_get_client.return_value = mock_client

        self._set_session(**{SK.CACHED_GAMES: [
            {"id": "A0000001-0000-4000-A000-000000000001", "name": "Game 1",
             "is_checked_out": 0, "is_play_to_win": 1}
        ]})

        resp = self.client.post("/library-mgmt/checkout",
                                json={
                                    "game_id": "A0000001-0000-4000-A000-000000000001",
                                    "renter_name": "Alice",
                                    "badge_number": "100",
                                })
        data = resp.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["checkout_id"], "checkout-001")
        self.assertTrue(data["is_play_to_win"])

        # Verify cache updated
        with self.client.session_transaction() as sess:
            games = sess[SK.CACHED_GAMES]
            self.assertEqual(games[0]["is_checked_out"], 1)

    def test_checkout_missing_name(self):
        self._set_session()
        resp = self.client.post("/library-mgmt/checkout",
                                json={
                                    "game_id": "A0000001-0000-4000-A000-000000000001",
                                    "renter_name": "",
                                })
        self.assertEqual(resp.status_code, 400)

    def test_checkout_invalid_game_id(self):
        self._set_session()
        resp = self.client.post("/library-mgmt/checkout",
                                json={"game_id": "bad-id", "renter_name": "Alice"})
        self.assertEqual(resp.status_code, 400)


class TestCheckin(LibraryTestBase):

    @patch("routes.library.checkout._get_client")
    def test_checkin_success(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.checkin_game.return_value = {}
        mock_get_client.return_value = mock_client

        game_id = "A0000001-0000-4000-A000-000000000001"
        checkout_id = "A0000002-0000-4000-A000-000000000002"
        self._set_session(**{SK.CACHED_GAMES: [
            {"id": game_id, "name": "Game 1", "is_checked_out": 1, "is_play_to_win": 0}
        ]})

        resp = self.client.post("/library-mgmt/checkin",
                                json={"checkout_id": checkout_id, "game_id": game_id})
        data = resp.get_json()
        self.assertTrue(data["success"])
        self.assertFalse(data["is_play_to_win"])

        with self.client.session_transaction() as sess:
            games = sess[SK.CACHED_GAMES]
            self.assertEqual(games[0]["is_checked_out"], 0)

    def test_checkin_invalid_checkout_id(self):
        self._set_session()
        resp = self.client.post("/library-mgmt/checkin",
                                json={"checkout_id": "bad"})
        self.assertEqual(resp.status_code, 400)


class TestP2WEntry(LibraryTestBase):

    @patch("routes.library.checkout._get_client")
    def test_p2w_entry_creates_entries(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.create_playtowin_entry.return_value = {"id": "p2w-001"}
        mock_get_client.return_value = mock_client

        game_id = "A0000001-0000-4000-A000-000000000001"
        self._set_session()

        resp = self.client.post("/library-mgmt/p2w-entry",
                                json={
                                    "game_id": game_id,
                                    "entrants": [
                                        {"name": "Alice"},
                                        {"name": "Bob"},
                                    ],
                                })
        data = resp.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(len(data["created"]), 2)

        # Verify play groups updated
        with self.client.session_transaction() as sess:
            groups = sess.get(SK.PLAY_GROUPS, {})
            self.assertIn("Bob", groups.get("Alice", []))
            self.assertIn("Alice", groups.get("Bob", []))

    def test_p2w_entry_requires_game_id(self):
        self._set_session()
        resp = self.client.post("/library-mgmt/p2w-entry",
                                json={"game_id": "", "entrants": [{"name": "Alice"}]})
        self.assertEqual(resp.status_code, 400)


class TestP2WSuggestions(LibraryTestBase):

    def test_suggestions_from_play_groups(self):
        self._set_session(**{SK.PLAY_GROUPS: {
            "Alice": ["Bob", "Carol"],
            "Bob": ["Alice"],
        }})
        resp = self.client.get("/library-mgmt/p2w-suggestions?name=Alice")
        data = resp.get_json()
        names = [s["name"] for s in data["suggestions"]]
        self.assertIn("Bob", names)
        self.assertIn("Carol", names)

    def test_suggestions_empty_for_unknown(self):
        self._set_session()
        resp = self.client.get("/library-mgmt/p2w-suggestions?name=Nobody")
        data = resp.get_json()
        self.assertEqual(data["suggestions"], [])


class TestGameSearch(LibraryTestBase):

    def test_game_search_by_name(self):
        self._set_session(**{SK.CACHED_GAMES: [
            {"id": "g1", "name": "Catan", "catalog_number": "PTW-001",
             "is_checked_out": 0, "is_play_to_win": 1, "is_in_circulation": 1},
            {"id": "g2", "name": "Azul", "catalog_number": "PTW-002",
             "is_checked_out": 1, "is_play_to_win": 1, "is_in_circulation": 1},
        ]})

        resp = self.client.get("/library-mgmt/game-search?q=catan")
        data = resp.get_json()
        self.assertEqual(len(data["results"]), 1)
        self.assertEqual(data["results"][0]["name"], "Catan")

    def test_game_search_by_catalog(self):
        self._set_session(**{SK.CACHED_GAMES: [
            {"id": "g1", "name": "Catan", "catalog_number": "PTW-001",
             "is_checked_out": 0, "is_play_to_win": 1, "is_in_circulation": 1},
        ]})

        resp = self.client.get("/library-mgmt/game-search?q=PTW-001")
        data = resp.get_json()
        self.assertEqual(len(data["results"]), 1)

    def test_game_search_empty_query(self):
        self._set_session()
        resp = self.client.get("/library-mgmt/game-search?q=")
        data = resp.get_json()
        self.assertEqual(data["results"], [])


class TestPersonSearch(LibraryTestBase):

    def test_person_search_by_name(self):
        self._set_session(**{SK.PERSON_CACHE: {
            "100": {"name": "Alice Smith", "badge_id": "b1"},
            "200": {"name": "Bob Jones", "badge_id": "b2"},
        }})

        resp = self.client.get("/library-mgmt/person-search?q=alice")
        data = resp.get_json()
        self.assertEqual(len(data["results"]), 1)
        self.assertEqual(data["results"][0]["name"], "Alice Smith")

    def test_person_search_by_badge(self):
        self._set_session(**{SK.PERSON_CACHE: {
            "100": {"name": "Alice Smith", "badge_id": "b1"},
        }})

        resp = self.client.get("/library-mgmt/person-search?q=100")
        data = resp.get_json()
        self.assertEqual(len(data["results"]), 1)


class TestNotifications(LibraryTestBase):

    def test_notifications_page(self):
        self._set_session(**{SK.NOTIFICATIONS: [
            {"id": "n1", "type": "info", "message": "Test notification",
             "dismissed": False, "timestamp": "2026-03-25"},
        ]})
        resp = self.client.get("/library-mgmt/notifications")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Test notification", resp.data)

    def test_dismiss_notification(self):
        self._set_session(**{SK.NOTIFICATIONS: [
            {"id": "n1", "type": "info", "message": "Test", "dismissed": False},
        ]})
        resp = self.client.post("/library-mgmt/notifications/dismiss",
                                json={"id": "n1"})
        data = resp.get_json()
        self.assertTrue(data["success"])

        with self.client.session_transaction() as sess:
            self.assertTrue(sess[SK.NOTIFICATIONS][0]["dismissed"])

    def test_notifications_empty(self):
        self._set_session()
        resp = self.client.get("/library-mgmt/notifications")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"No notifications", resp.data)


class TestGameDetail(LibraryTestBase):

    @patch("routes.library.lookup._get_client")
    def test_game_detail_page(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.get_library_game.return_value = {
            "id": "A0000001-0000-4000-A000-000000000001",
            "name": "Catan",
            "catalog_number": "PTW-001",
            "is_play_to_win": 1,
            "is_checked_out": 0,
            "is_in_circulation": 1,
            "publisher_name": "Asmodee",
            "min_players": 3,
            "max_players": 4,
            "checkout_count": 5,
        }
        mock_client.get_library_game_checkouts.return_value = []
        mock_client.get_library_game_playtowins.return_value = [
            {"name": "Alice"}, {"name": "Bob"},
        ]
        mock_get_client.return_value = mock_client

        self._set_session()
        resp = self.client.get("/library-mgmt/game/A0000001-0000-4000-A000-000000000001")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Catan", resp.data)

    def test_game_detail_invalid_id(self):
        self._set_session()
        resp = self.client.get("/library-mgmt/game/bad-id")
        self.assertEqual(resp.status_code, 400)
