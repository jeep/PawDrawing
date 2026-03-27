"""Tests for library management features integrated into main routes."""

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from app import create_app
from session_keys import SK
from tte_client import TTEAPIError


VALID_GAME_ID = "A0000001-0000-4000-A000-000000000001"
VALID_GAME_ID_2 = "A0000002-0000-4000-A000-000000000002"
VALID_CHECKOUT_ID = "B0000001-0000-4000-B000-000000000001"


class LibraryTestBase(unittest.TestCase):
    """Base class with helper setup for library management tests."""

    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

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


# ── Badge Lookup Tests ────────────────────────────────────────────────

class TestBadgeLookup(LibraryTestBase):

    def test_badge_lookup_requires_badge_number(self):
        self._set_session()
        resp = self.client.get("/games/badge-lookup")
        self.assertEqual(resp.status_code, 400)

    def test_badge_lookup_from_cache(self):
        self._set_session(**{SK.PERSON_CACHE: {
            "123": {"name": "Alice", "badge_id": "b-001", "user_id": None}
        }})
        resp = self.client.get("/games/badge-lookup?badge_number=123")
        data = resp.get_json()
        self.assertEqual(data["name"], "Alice")
        self.assertEqual(data["source"], "cache")

    @patch("routes.games._get_client")
    def test_badge_lookup_from_tte(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.search_badges.return_value = [
            {"name_full": "Bob Smith", "id": "badge-002", "user_id": "u-002"}
        ]
        mock_get_client.return_value = mock_client

        self._set_session()
        resp = self.client.get("/games/badge-lookup?badge_number=456")
        data = resp.get_json()
        self.assertEqual(data["name"], "Bob Smith")
        self.assertEqual(data["source"], "tte")

    @patch("routes.games._get_client")
    def test_badge_lookup_not_found(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.search_badges.return_value = []
        mock_get_client.return_value = mock_client

        self._set_session()
        resp = self.client.get("/games/badge-lookup?badge_number=999")
        self.assertEqual(resp.status_code, 404)

    def test_badge_lookup_no_convention(self):
        with self.client.session_transaction() as sess:
            sess[SK.TTE_SESSION_ID] = "test-session"
            sess[SK.LIBRARY_ID] = "lib-001"
            sess[SK.LIBRARY_NAME] = "Test Library"
        resp = self.client.get("/games/badge-lookup?badge_number=123")
        self.assertEqual(resp.status_code, 400)


# ── Checkout Tests ────────────────────────────────────────────────────

class TestCheckout(LibraryTestBase):

    @patch("routes.games._get_client")
    def test_checkout_success(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.get_library_game.return_value = {
            "id": VALID_GAME_ID,
            "is_checked_out": 0,
            "is_in_circulation": 1,
        }
        mock_client.create_checkout.return_value = {"id": "checkout-001"}
        mock_get_client.return_value = mock_client

        self._set_session(**{SK.CACHED_GAMES: [
            {"id": VALID_GAME_ID, "name": "Game 1",
             "is_checked_out": 0, "is_play_to_win": 1}
        ]})

        resp = self.client.post("/games/checkout",
                                json={
                                    "game_id": VALID_GAME_ID,
                                    "renter_name": "Alice",
                                    "badge_number": "100",
                                })
        data = resp.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["checkout_id"], "checkout-001")
        self.assertTrue(data["is_play_to_win"])

        with self.client.session_transaction() as sess:
            games = sess[SK.CACHED_GAMES]
            self.assertEqual(games[0]["is_checked_out"], 1)

    def test_checkout_missing_name(self):
        self._set_session()
        resp = self.client.post("/games/checkout",
                                json={
                                    "game_id": VALID_GAME_ID,
                                    "renter_name": "",
                                })
        self.assertEqual(resp.status_code, 400)

    def test_checkout_invalid_game_id(self):
        self._set_session()
        resp = self.client.post("/games/checkout",
                                json={"game_id": "bad-id", "renter_name": "Alice"})
        self.assertEqual(resp.status_code, 400)


# ── Checkin Tests ─────────────────────────────────────────────────────

class TestCheckin(LibraryTestBase):

    @patch("routes.games._get_client")
    def test_checkin_success(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.checkin_game.return_value = {}
        mock_get_client.return_value = mock_client

        self._set_session(**{SK.CACHED_GAMES: [
            {"id": VALID_GAME_ID, "name": "Game 1",
             "is_checked_out": 1, "is_play_to_win": 0}
        ]})

        resp = self.client.post("/games/checkin",
                                json={"checkout_id": VALID_CHECKOUT_ID,
                                      "game_id": VALID_GAME_ID})
        data = resp.get_json()
        self.assertTrue(data["success"])
        self.assertFalse(data["is_play_to_win"])

        with self.client.session_transaction() as sess:
            games = sess[SK.CACHED_GAMES]
            self.assertEqual(games[0]["is_checked_out"], 0)

    def test_checkin_invalid_checkout_id(self):
        self._set_session()
        resp = self.client.post("/games/checkin",
                                json={"checkout_id": "bad"})
        self.assertEqual(resp.status_code, 400)


# ── P2W Entry Tests ───────────────────────────────────────────────────

class TestP2WEntry(LibraryTestBase):

    @patch("routes.games._get_client")
    def test_p2w_entry_creates_entries(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.create_playtowin_entry.return_value = {"id": "p2w-001"}
        mock_get_client.return_value = mock_client

        self._set_session()
        resp = self.client.post("/games/p2w-entry",
                                json={
                                    "game_id": VALID_GAME_ID,
                                    "entrants": [
                                        {"name": "Alice"},
                                        {"name": "Bob"},
                                    ],
                                })
        data = resp.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(len(data["created"]), 2)

        with self.client.session_transaction() as sess:
            groups = sess.get(SK.PLAY_GROUPS, {})
            self.assertIn("Bob", groups.get("Alice", []))
            self.assertIn("Alice", groups.get("Bob", []))

    def test_p2w_entry_requires_game_id(self):
        self._set_session()
        resp = self.client.post("/games/p2w-entry",
                                json={"game_id": "", "entrants": [{"name": "Alice"}]})
        self.assertEqual(resp.status_code, 400)


# ── P2W Suggestions Tests ────────────────────────────────────────────

class TestP2WSuggestions(LibraryTestBase):

    def test_suggestions_from_play_groups(self):
        self._set_session(**{SK.PLAY_GROUPS: {
            "Alice": ["Bob", "Carol"],
            "Bob": ["Alice"],
        }})
        resp = self.client.get("/games/p2w-suggestions?name=Alice")
        data = resp.get_json()
        names = [s["name"] for s in data["suggestions"]]
        self.assertIn("Bob", names)
        self.assertIn("Carol", names)

    def test_suggestions_empty_for_unknown(self):
        self._set_session()
        resp = self.client.get("/games/p2w-suggestions?name=Nobody")
        data = resp.get_json()
        self.assertEqual(data["suggestions"], [])


# ── Active Checkout Tests ─────────────────────────────────────────────

class TestActiveCheckout(LibraryTestBase):

    @patch("routes.games._get_client")
    def test_active_checkout_found(self, mock_gc):
        mock_client = MagicMock()
        mock_client.get_library_game_checkouts.return_value = [
            {"id": VALID_CHECKOUT_ID, "renter_name": "Alice",
             "date_created": "2026-03-25 10:00:00"},
        ]
        mock_gc.return_value = mock_client

        self._set_session()
        resp = self.client.get(
            f"/games/active-checkout?game_id={VALID_GAME_ID}")
        data = resp.get_json()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(data["checkout_id"], VALID_CHECKOUT_ID)
        self.assertEqual(data["renter_name"], "Alice")

    @patch("routes.games._get_client")
    def test_active_checkout_not_found(self, mock_gc):
        mock_client = MagicMock()
        mock_client.get_library_game_checkouts.return_value = []
        mock_gc.return_value = mock_client

        self._set_session()
        resp = self.client.get(
            f"/games/active-checkout?game_id={VALID_GAME_ID}")
        self.assertEqual(resp.status_code, 404)

    def test_active_checkout_invalid_game_id(self):
        self._set_session()
        resp = self.client.get("/games/active-checkout?game_id=bad")
        self.assertEqual(resp.status_code, 400)


# ── Checkout Verification Tests ───────────────────────────────────────

class TestCheckoutFreshVerification(LibraryTestBase):

    @patch("routes.games._get_client")
    def test_checkout_already_checked_out(self, mock_gc):
        mock_client = MagicMock()
        mock_client.get_library_game.return_value = {
            "id": VALID_GAME_ID, "is_checked_out": 1, "is_in_circulation": 1,
        }
        mock_gc.return_value = mock_client

        self._set_session(**{SK.CACHED_GAMES: [
            {"id": VALID_GAME_ID, "name": "Game 1",
             "is_checked_out": 0, "is_play_to_win": 1},
        ]})
        resp = self.client.post("/games/checkout", json={
            "game_id": VALID_GAME_ID, "renter_name": "Alice",
        })
        self.assertEqual(resp.status_code, 409)
        self.assertIn("already checked out", resp.get_json()["error"])

    @patch("routes.games._get_client")
    def test_checkout_not_in_circulation(self, mock_gc):
        mock_client = MagicMock()
        mock_client.get_library_game.return_value = {
            "id": VALID_GAME_ID, "is_checked_out": 0, "is_in_circulation": 0,
        }
        mock_gc.return_value = mock_client

        self._set_session(**{SK.CACHED_GAMES: []})
        resp = self.client.post("/games/checkout", json={
            "game_id": VALID_GAME_ID, "renter_name": "Alice",
        })
        self.assertEqual(resp.status_code, 409)
        self.assertIn("not in circulation", resp.get_json()["error"])


# ── P2W Duplicate Prevention Tests ────────────────────────────────────

class TestP2WDuplicatePrevention(LibraryTestBase):

    @patch("routes.games._get_client")
    def test_p2w_skips_existing_entries(self, mock_gc):
        mock_client = MagicMock()
        mock_client.get_library_game_playtowins.return_value = [
            {"name": "Alice"},
        ]
        mock_client.create_playtowin_entry.return_value = {"id": "p2w-new"}
        mock_gc.return_value = mock_client

        self._set_session()
        resp = self.client.post("/games/p2w-entry", json={
            "game_id": VALID_GAME_ID,
            "entrants": [{"name": "Alice"}, {"name": "Bob"}],
        })
        data = resp.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(len(data["created"]), 1)
        self.assertEqual(data["created"][0]["name"], "Bob")
        self.assertEqual(len(data["skipped"]), 1)
        self.assertEqual(data["skipped"][0]["name"], "Alice")

    @patch("routes.games._get_client")
    def test_p2w_all_skipped(self, mock_gc):
        mock_client = MagicMock()
        mock_client.get_library_game_playtowins.return_value = [
            {"name": "Alice"}, {"name": "Bob"},
        ]
        mock_gc.return_value = mock_client

        self._set_session()
        resp = self.client.post("/games/p2w-entry", json={
            "game_id": VALID_GAME_ID,
            "entrants": [{"name": "Alice"}, {"name": "Bob"}],
        })
        data = resp.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(len(data["created"]), 0)
        self.assertEqual(len(data["skipped"]), 2)


# ── Reset Checkout Time Tests ─────────────────────────────────────────

class TestResetCheckoutTime(LibraryTestBase):

    @patch("routes.games._get_client")
    def test_reset_checkout_time_success(self, mock_gc):
        mock_client = MagicMock()
        mock_client.reset_checkout_time.return_value = {}
        mock_gc.return_value = mock_client

        self._set_session()
        resp = self.client.post("/games/reset-checkout-time",
                                json={"checkout_id": VALID_CHECKOUT_ID})
        data = resp.get_json()
        self.assertTrue(data["success"])

    def test_reset_checkout_time_invalid_id(self):
        self._set_session()
        resp = self.client.post("/games/reset-checkout-time",
                                json={"checkout_id": "bad"})
        self.assertEqual(resp.status_code, 400)

    def test_reset_checkout_time_missing_id(self):
        self._set_session()
        resp = self.client.post("/games/reset-checkout-time",
                                json={})
        self.assertEqual(resp.status_code, 400)


# ── Notification Tests ────────────────────────────────────────────────

class TestNotifications(LibraryTestBase):

    def test_get_notifications(self):
        self._set_session(**{SK.NOTIFICATIONS: [
            {"id": "n1", "type": "info", "message": "Test notification",
             "dismissed": False, "timestamp": "2026-03-25"},
        ]})
        resp = self.client.get("/games/notifications")
        data = resp.get_json()
        self.assertEqual(len(data["notifications"]), 1)
        self.assertEqual(data["notifications"][0]["message"], "Test notification")

    def test_dismiss_notification(self):
        self._set_session(**{SK.NOTIFICATIONS: [
            {"id": "n1", "type": "info", "message": "Test", "dismissed": False},
        ]})
        resp = self.client.post("/games/notifications/dismiss",
                                json={"id": "n1"})
        data = resp.get_json()
        self.assertTrue(data["success"])

        with self.client.session_transaction() as sess:
            self.assertTrue(sess[SK.NOTIFICATIONS][0]["dismissed"])

    def test_get_notifications_empty(self):
        self._set_session()
        resp = self.client.get("/games/notifications")
        data = resp.get_json()
        self.assertEqual(data["notifications"], [])


# ── Mark All P2W Tests ────────────────────────────────────────────────

class TestMarkAllP2W(LibraryTestBase):

    @patch("routes.games._get_client")
    def test_mark_all_p2w(self, mock_gc):
        mock_client = MagicMock()
        mock_client.update_library_game.return_value = {}
        mock_gc.return_value = mock_client

        self._set_session(**{SK.CACHED_GAMES: [
            {"id": "g1", "name": "Game 1", "is_play_to_win": 0,
             "is_in_circulation": 1},
            {"id": "g2", "name": "Game 2", "is_play_to_win": 1,
             "is_in_circulation": 1},
        ]})
        resp = self.client.post("/games/mark-all-p2w",
                                json={})
        data = resp.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["updated"], 1)

        with self.client.session_transaction() as sess:
            g1 = next(g for g in sess[SK.CACHED_GAMES] if g["id"] == "g1")
            self.assertEqual(g1["is_play_to_win"], 1)

    def test_mark_all_p2w_nothing_to_update(self):
        self._set_session(**{SK.CACHED_GAMES: [
            {"id": "g1", "is_play_to_win": 1, "is_in_circulation": 1},
        ]})
        resp = self.client.post("/games/mark-all-p2w",
                                json={})
        data = resp.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["updated"], 0)


# ── Settings Tests ────────────────────────────────────────────────────

class TestUpdateSettings(LibraryTestBase):

    def test_update_checkout_alert_hours(self):
        self._set_session()
        resp = self.client.post("/games/settings",
                                json={"checkout_alert_hours": 5})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json()["success"])

        with self.client.session_transaction() as sess:
            settings = sess.get(SK.LIBRARY_SETTINGS, {})
            self.assertEqual(settings["checkout_alert_hours"], 5)

    def test_update_settings_clamps_hours(self):
        self._set_session()
        resp = self.client.post("/games/settings",
                                json={"checkout_alert_hours": 100})
        self.assertEqual(resp.status_code, 200)
        with self.client.session_transaction() as sess:
            self.assertEqual(sess[SK.LIBRARY_SETTINGS]["checkout_alert_hours"], 24)


# ── Error Handling Tests ──────────────────────────────────────────────

class TestErrorHandling429(LibraryTestBase):

    @patch("routes.games._get_client")
    def test_checkout_429_rate_limit(self, mock_gc):
        mock_client = MagicMock()
        exc = TTEAPIError("Rate limited")
        exc.status_code = 429
        mock_client.get_library_game.side_effect = exc
        mock_gc.return_value = mock_client

        self._set_session(**{SK.CACHED_GAMES: []})
        resp = self.client.post("/games/checkout", json={
            "game_id": VALID_GAME_ID, "renter_name": "Alice",
        })
        # Non-auth API errors are wrapped as 502 by _handle_api_json_error
        self.assertEqual(resp.status_code, 502)
        self.assertIn("rate limited", resp.get_json()["error"].lower())

    @patch("routes.games._get_client")
    def test_checkout_401_session_expired(self, mock_gc):
        mock_client = MagicMock()
        exc = TTEAPIError("Unauthorized")
        exc.status_code = 401
        mock_client.get_library_game.side_effect = exc
        mock_gc.return_value = mock_client

        self._set_session(**{SK.CACHED_GAMES: []})
        resp = self.client.post("/games/checkout", json={
            "game_id": VALID_GAME_ID, "renter_name": "Alice",
        })
        self.assertEqual(resp.status_code, 401)
        self.assertIn("expired", resp.get_json()["error"].lower())


# ── Suspicious Detection Unit Tests ───────────────────────────────────

class TestSuspiciousDetection(unittest.TestCase):

    def test_compute_threshold_with_play_time(self):
        from routes.suspicious import compute_threshold_seconds
        game = {"max_play_time": 60}
        self.assertEqual(compute_threshold_seconds(game), 7200)

    def test_compute_threshold_minimum_one_hour(self):
        from routes.suspicious import compute_threshold_seconds
        game = {"max_play_time": 10}
        self.assertEqual(compute_threshold_seconds(game), 3600)

    def test_compute_threshold_fallback(self):
        from routes.suspicious import compute_threshold_seconds
        self.assertEqual(compute_threshold_seconds({}), 4 * 3600)
        self.assertEqual(compute_threshold_seconds({"max_play_time": 0}), 4 * 3600)

    def test_check_long_checkouts(self):
        from routes.suspicious import check_long_checkouts
        games = [{"id": "g1", "name": "Catan", "max_play_time": 60}]
        old_time = (datetime.now(timezone.utc) - timedelta(hours=5)).strftime(
            "%Y-%m-%d %H:%M:%S")
        active = [{"id": "co1", "librarygame_id": "g1",
                    "renter_name": "Alice", "date_created": old_time}]
        result = check_long_checkouts(games, active)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["game_name"], "Catan")

    def test_check_long_checkouts_within_threshold(self):
        from routes.suspicious import check_long_checkouts
        games = [{"id": "g1", "name": "Catan", "max_play_time": 120}]
        recent_time = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime(
            "%Y-%m-%d %H:%M:%S")
        active = [{"id": "co1", "librarygame_id": "g1",
                    "renter_name": "Alice", "date_created": recent_time}]
        result = check_long_checkouts(games, active)
        self.assertEqual(len(result), 0)

    def test_check_partner_patterns(self):
        from routes.suspicious import check_partner_patterns
        games = [{"id": "g1", "max_play_time": 60}]
        checkouts = [
            {"librarygame_id": "g1", "renter_name": "Alice",
             "date_created": "2026-03-25 10:00:00", "checkedout_seconds": 10000},
            {"librarygame_id": "g1", "renter_name": "Bob",
             "date_created": "2026-03-25 14:00:00", "checkedout_seconds": 9000},
        ]
        play_groups = {"Alice": ["Bob"], "Bob": ["Alice"]}
        result = check_partner_patterns(checkouts, play_groups, games)
        self.assertEqual(len(result), 1)

    def test_partner_patterns_not_partners(self):
        from routes.suspicious import check_partner_patterns
        checkouts = [
            {"librarygame_id": "g1", "renter_name": "Alice",
             "date_created": "2026-03-25 10:00:00", "checkedout_seconds": 10000},
            {"librarygame_id": "g1", "renter_name": "Bob",
             "date_created": "2026-03-25 14:00:00", "checkedout_seconds": 9000},
        ]
        result = check_partner_patterns(checkouts, {})
        self.assertEqual(len(result), 0)

    def test_flag_suspicious_games(self):
        from routes.suspicious import flag_suspicious_games
        games = [
            {"id": "g1", "name": "Catan"},
            {"id": "g2", "name": "Azul"},
        ]
        suspicious = [{"game_id": "g1"}]
        patterns = [{"game_id": "g2"}]
        flagged = flag_suspicious_games(games, suspicious, patterns)
        self.assertIn("g1", flagged)
        self.assertIn("g2", flagged)
        self.assertTrue(games[0]["_suspicious"])
        self.assertTrue(games[1]["_suspicious"])


class TestPartnerPatternThresholds(unittest.TestCase):

    def test_partner_pattern_uses_game_threshold(self):
        from routes.suspicious import check_partner_patterns
        games = [{"id": "g1", "max_play_time": 30}]
        checkouts = [
            {"librarygame_id": "g1", "renter_name": "Alice",
             "date_created": "2026-03-25 10:00:00", "checkedout_seconds": 4000},
            {"librarygame_id": "g1", "renter_name": "Bob",
             "date_created": "2026-03-25 14:00:00", "checkedout_seconds": 4000},
        ]
        play_groups = {"Alice": ["Bob"]}
        result = check_partner_patterns(checkouts, play_groups, games)
        self.assertEqual(len(result), 1)

    def test_partner_pattern_no_false_positive_with_long_game(self):
        from routes.suspicious import check_partner_patterns
        games = [{"id": "g1", "max_play_time": 180}]
        checkouts = [
            {"librarygame_id": "g1", "renter_name": "Alice",
             "date_created": "2026-03-25 10:00:00", "checkedout_seconds": 10000},
            {"librarygame_id": "g1", "renter_name": "Bob",
             "date_created": "2026-03-25 14:00:00", "checkedout_seconds": 9000},
        ]
        play_groups = {"Alice": ["Bob"]}
        result = check_partner_patterns(checkouts, play_groups, games)
        self.assertEqual(len(result), 0)

    def test_partner_pattern_fallback_no_games(self):
        from routes.suspicious import check_partner_patterns
        checkouts = [
            {"librarygame_id": "g1", "renter_name": "Alice",
             "date_created": "2026-03-25 10:00:00", "checkedout_seconds": 15000},
            {"librarygame_id": "g1", "renter_name": "Bob",
             "date_created": "2026-03-25 14:00:00", "checkedout_seconds": 15000},
        ]
        play_groups = {"Alice": ["Bob"]}
        result = check_partner_patterns(checkouts, play_groups)
        self.assertEqual(len(result), 1)


class TestPremiumFlagInSuspicious(unittest.TestCase):

    def test_long_checkout_premium_flag(self):
        from routes.suspicious import check_long_checkouts
        games = [{"id": "g1", "name": "Catan", "max_play_time": 60}]
        old_time = (datetime.now(timezone.utc) - timedelta(hours=5)).strftime(
            "%Y-%m-%d %H:%M:%S")
        active = [{"id": "co1", "librarygame_id": "g1",
                    "renter_name": "Alice", "date_created": old_time}]
        result = check_long_checkouts(games, active, premium_ids={"g1"})
        self.assertTrue(result[0]["is_premium"])

    def test_long_checkout_not_premium(self):
        from routes.suspicious import check_long_checkouts
        games = [{"id": "g1", "name": "Catan", "max_play_time": 60}]
        old_time = (datetime.now(timezone.utc) - timedelta(hours=5)).strftime(
            "%Y-%m-%d %H:%M:%S")
        active = [{"id": "co1", "librarygame_id": "g1",
                    "renter_name": "Alice", "date_created": old_time}]
        result = check_long_checkouts(games, active)
        self.assertFalse(result[0]["is_premium"])


# ── TTE Client Method Tests ──────────────────────────────────────────

class TestTTEClientNewMethods(unittest.TestCase):

    def test_get_library_privileges_method_exists(self):
        from tte_client import TTEClient
        self.assertTrue(hasattr(TTEClient, "get_library_privileges"))

    def test_create_library_privilege_method_exists(self):
        from tte_client import TTEClient
        self.assertTrue(hasattr(TTEClient, "create_library_privilege"))

    def test_reset_checkout_time_method_exists(self):
        from tte_client import TTEClient
        self.assertTrue(hasattr(TTEClient, "reset_checkout_time"))


# ── Volunteer Login Tests ─────────────────────────────────────────────

class TestVolunteerLogin(LibraryTestBase):

    def test_volunteer_login_page_requires_library(self):
        resp = self.client.get("/volunteer-login", follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.headers["Location"])

    def test_volunteer_login_page_renders(self):
        with self.client.session_transaction() as sess:
            sess[SK.LIBRARY_ID] = "lib-001"
            sess[SK.LIBRARY_NAME] = "Test Library"
        resp = self.client.get("/volunteer-login")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Volunteer Login", resp.data)
        self.assertIn(b"Test Library", resp.data)

    def test_volunteer_login_missing_credentials(self):
        with self.client.session_transaction() as sess:
            sess[SK.LIBRARY_ID] = "lib-001"
            sess[SK.LIBRARY_NAME] = "Test Library"
        resp = self.client.post("/volunteer-login",
                                data={"username": "", "password": "", "api_key": ""})
        self.assertEqual(resp.status_code, 400)

    @patch("tte_client.TTEClient")
    def test_volunteer_login_bad_credentials(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.login.side_effect = TTEAPIError("Invalid credentials")
        MockClient.return_value = mock_instance

        with self.client.session_transaction() as sess:
            sess[SK.LIBRARY_ID] = "lib-001"
            sess[SK.LIBRARY_NAME] = "Test Library"

        resp = self.client.post("/volunteer-login",
                                data={"username": "vol1", "password": "bad",
                                      "api_key": "key1"})
        self.assertEqual(resp.status_code, 401)

    @patch("tte_client.TTEClient")
    def test_volunteer_login_no_privilege(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.user_id = "vol-user-001"
        mock_instance.session_id = "vol-sess-001"
        mock_instance.get_library_privileges.return_value = [
            {"user_id": "vol-user-001", "checkouts": 0},
        ]
        MockClient.return_value = mock_instance

        with self.client.session_transaction() as sess:
            sess[SK.LIBRARY_ID] = "lib-001"
            sess[SK.LIBRARY_NAME] = "Test Library"

        resp = self.client.post("/volunteer-login",
                                data={"username": "vol1", "password": "pass",
                                      "api_key": "key1"})
        self.assertEqual(resp.status_code, 403)

    @patch("tte_client.TTEClient")
    def test_volunteer_login_success(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.user_id = "vol-user-001"
        mock_instance.session_id = "vol-sess-001"
        mock_instance.get_library_privileges.return_value = [
            {"user_id": "vol-user-001", "checkouts": 1},
        ]
        MockClient.return_value = mock_instance

        with self.client.session_transaction() as sess:
            sess[SK.LIBRARY_ID] = "lib-001"
            sess[SK.LIBRARY_NAME] = "Test Library"

        resp = self.client.post("/volunteer-login",
                                data={"username": "vol1", "password": "pass",
                                      "api_key": "key1"},
                                follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/games", resp.headers["Location"])

        with self.client.session_transaction() as sess:
            self.assertEqual(sess[SK.AUTH_MODE], "volunteer")
            self.assertEqual(sess[SK.VOLUNTEER_NAME], "vol1")
            self.assertTrue(sess[SK.HAS_CHECKOUT_PRIVILEGE])
            self.assertEqual(sess[SK.APP_MODE], "management")

    @patch("tte_client.TTEClient")
    def test_volunteer_login_privilege_check_fails(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.user_id = "vol-user-001"
        mock_instance.session_id = "vol-sess-001"
        mock_instance.get_library_privileges.side_effect = TTEAPIError("Server error")
        MockClient.return_value = mock_instance

        with self.client.session_transaction() as sess:
            sess[SK.LIBRARY_ID] = "lib-001"
            sess[SK.LIBRARY_NAME] = "Test Library"

        resp = self.client.post("/volunteer-login",
                                data={"username": "vol1", "password": "pass",
                                      "api_key": "key1"})
        self.assertEqual(resp.status_code, 403)


# ── Volunteer Logout Tests ────────────────────────────────────────────

class TestVolunteerLogout(LibraryTestBase):

    def test_volunteer_logout_preserves_library(self):
        self._set_session(**{
            SK.AUTH_MODE: "volunteer",
            SK.VOLUNTEER_NAME: "vol1",
            SK.CACHED_GAMES: [{"id": "g1", "name": "Catan"}],
        })
        resp = self.client.post("/volunteer-logout",
                                follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("volunteer-login", resp.headers["Location"])

        with self.client.session_transaction() as sess:
            self.assertEqual(sess.get(SK.LIBRARY_ID), "lib-001")
            self.assertEqual(sess.get(SK.LIBRARY_NAME), "Test Library")
            self.assertIsNotNone(sess.get(SK.CACHED_GAMES))
            self.assertIsNone(sess.get(SK.TTE_SESSION_ID))
            self.assertIsNone(sess.get(SK.AUTH_MODE))


# ── Checkout Privilege Gate Tests ─────────────────────────────────────

class TestCheckoutPrivilegeGate(LibraryTestBase):

    def test_checkout_denied_for_unprivileged_volunteer(self):
        self._set_session(**{
            SK.AUTH_MODE: "volunteer",
            SK.HAS_CHECKOUT_PRIVILEGE: False,
        })
        resp = self.client.post("/games/checkout", json={
            "game_id": VALID_GAME_ID, "renter_name": "Alice",
        })
        self.assertEqual(resp.status_code, 403)
        self.assertIn("privilege", resp.get_json()["error"].lower())

    def test_checkin_denied_for_unprivileged_volunteer(self):
        self._set_session(**{
            SK.AUTH_MODE: "volunteer",
            SK.HAS_CHECKOUT_PRIVILEGE: False,
        })
        resp = self.client.post("/games/checkin", json={
            "checkout_id": VALID_CHECKOUT_ID, "game_id": VALID_GAME_ID,
        })
        self.assertEqual(resp.status_code, 403)

    def test_reset_time_denied_for_unprivileged_volunteer(self):
        self._set_session(**{
            SK.AUTH_MODE: "volunteer",
            SK.HAS_CHECKOUT_PRIVILEGE: False,
        })
        resp = self.client.post("/games/reset-checkout-time",
                                json={"checkout_id": VALID_CHECKOUT_ID})
        self.assertEqual(resp.status_code, 403)

    @patch("routes.games._get_client")
    def test_checkout_allowed_for_privileged_volunteer(self, mock_gc):
        mock_client = MagicMock()
        mock_client.get_library_game.return_value = {
            "id": VALID_GAME_ID, "is_checked_out": 0, "is_in_circulation": 1,
        }
        mock_client.create_checkout.return_value = {"id": "co-001"}
        mock_gc.return_value = mock_client

        self._set_session(**{
            SK.AUTH_MODE: "volunteer",
            SK.HAS_CHECKOUT_PRIVILEGE: True,
            SK.CACHED_GAMES: [
                {"id": VALID_GAME_ID, "name": "Catan",
                 "is_checked_out": 0, "is_play_to_win": 1},
            ],
        })
        resp = self.client.post("/games/checkout", json={
            "game_id": VALID_GAME_ID, "renter_name": "Alice",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json()["success"])

    def test_owner_mode_always_allowed(self):
        self._set_session(**{SK.CACHED_GAMES: []})
        resp = self.client.post("/games/checkout", json={
            "game_id": VALID_GAME_ID, "renter_name": "Alice",
        })
        self.assertNotEqual(resp.status_code, 403)


if __name__ == "__main__":
    unittest.main()
