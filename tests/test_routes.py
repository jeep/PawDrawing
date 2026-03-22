"""Tests for login/logout routes."""

import unittest
from unittest.mock import patch, MagicMock

from app import create_app
from tte_client import TTEAPIError, TTETimeoutError


class TestLoginRoute(unittest.TestCase):

    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.app.config["TTE_API_KEY"] = "test-key"
        self.client = self.app.test_client()

    def test_index_redirects_to_login(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.headers["Location"])

    def test_login_page_renders(self):
        resp = self.client.get("/login")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Log In", resp.data)
        self.assertIn(b"username", resp.data)
        self.assertIn(b"password", resp.data)

    def test_login_empty_fields_returns_error(self):
        resp = self.client.post("/login", data={"username": "", "password": ""})
        self.assertEqual(resp.status_code, 400)
        self.assertIn(b"required", resp.data)

    @patch("routes.TTEClient")
    def test_login_success_redirects_to_convention(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.session_id = "session-123"
        mock_instance.login.return_value = {"id": "session-123"}
        MockClient.return_value = mock_instance

        resp = self.client.post("/login", data={
            "username": "admin",
            "password": "secret",
        })
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/convention", resp.headers["Location"])
        mock_instance.login.assert_called_once_with("admin", "secret")

    @patch("routes.TTEClient")
    def test_login_success_stores_session(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.session_id = "session-123"
        mock_instance.login.return_value = {"id": "session-123"}
        MockClient.return_value = mock_instance

        with self.client.session_transaction() as sess:
            sess.clear()

        self.client.post("/login", data={
            "username": "admin",
            "password": "secret",
        })

        with self.client.session_transaction() as sess:
            self.assertEqual(sess["tte_session_id"], "session-123")
            self.assertEqual(sess["tte_username"], "admin")

    @patch("routes.TTEClient")
    def test_login_failure_shows_error(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.login.side_effect = TTEAPIError("Invalid credentials")
        MockClient.return_value = mock_instance

        resp = self.client.post("/login", data={
            "username": "admin",
            "password": "wrong",
        })
        self.assertEqual(resp.status_code, 401)
        self.assertIn(b"Login failed", resp.data)

    def test_password_field_is_masked(self):
        resp = self.client.get("/login")
        self.assertIn(b'type="password"', resp.data)


class TestLogoutRoute(unittest.TestCase):

    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.app.config["TTE_API_KEY"] = "test-key"
        self.client = self.app.test_client()

    @patch("routes.TTEClient")
    def test_logout_clears_session(self, MockClient):
        mock_instance = MagicMock()
        MockClient.return_value = mock_instance

        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["tte_username"] = "admin"

        resp = self.client.post("/logout")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.headers["Location"])

        with self.client.session_transaction() as sess:
            self.assertNotIn("tte_session_id", sess)
            self.assertNotIn("tte_username", sess)

    @patch("routes.TTEClient")
    def test_logout_calls_api_logout(self, MockClient):
        mock_instance = MagicMock()
        MockClient.return_value = mock_instance

        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"

        self.client.post("/logout")
        mock_instance.logout.assert_called_once()


class TestConventionSelectRoute(unittest.TestCase):

    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.app.config["TTE_API_KEY"] = "test-key"
        self.client = self.app.test_client()

    def test_convention_requires_login(self):
        resp = self.client.get("/convention")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.headers["Location"])

    def test_convention_accessible_when_logged_in(self):
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["tte_username"] = "admin"

        resp = self.client.get("/convention")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Select Convention", resp.data)


class TestConventionSearchRoute(unittest.TestCase):

    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.app.config["TTE_API_KEY"] = "test-key"
        self.client = self.app.test_client()

    def test_search_requires_login(self):
        resp = self.client.get("/convention/search?q=test")
        self.assertEqual(resp.status_code, 401)

    def test_search_short_query_returns_empty(self):
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"

        resp = self.client.get("/convention/search?q=a")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["results"], [])

    @patch("routes.TTEClient")
    def test_search_returns_results(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.search_conventions.return_value = [
            {"id": "conv-1", "name": "GameFest 2026"},
            {"id": "conv-2", "name": "GameCon 2026"},
        ]
        MockClient.return_value = mock_instance

        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"

        resp = self.client.get("/convention/search?q=game")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(len(data["results"]), 2)
        self.assertEqual(data["results"][0]["name"], "GameFest 2026")

    @patch("routes.TTEClient")
    def test_search_api_error_returns_502(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.search_conventions.side_effect = TTEAPIError("API down")
        MockClient.return_value = mock_instance

        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"

        resp = self.client.get("/convention/search?q=test")
        self.assertEqual(resp.status_code, 502)
        data = resp.get_json()
        self.assertIn("error", data)


class TestConventionConfirmRoute(unittest.TestCase):

    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.app.config["TTE_API_KEY"] = "test-key"
        self.client = self.app.test_client()

    def test_select_requires_login(self):
        resp = self.client.post("/convention/select", data={"convention_id": "x"})
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.headers["Location"])

    def test_select_empty_id_redirects_with_error(self):
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"

        resp = self.client.post("/convention/select", data={"convention_id": ""})
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/convention", resp.headers["Location"])

    @patch("routes.TTEClient")
    def test_select_success_stores_session(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.get_convention.return_value = {
            "id": "conv-1",
            "name": "GameFest 2026",
            "library": {"id": "lib-1", "name": "GameFest Library"},
        }
        MockClient.return_value = mock_instance

        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"

        resp = self.client.post("/convention/select", data={"convention_id": "conv-1"})
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"GameFest 2026", resp.data)
        self.assertIn(b"GameFest Library", resp.data)

        with self.client.session_transaction() as sess:
            self.assertEqual(sess["convention_id"], "conv-1")
            self.assertEqual(sess["library_id"], "lib-1")

    @patch("routes.TTEClient")
    def test_select_no_library_shows_error(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.get_convention.return_value = {
            "id": "conv-1",
            "name": "GameFest 2026",
        }
        MockClient.return_value = mock_instance

        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"

        resp = self.client.post("/convention/select", data={"convention_id": "conv-1"})
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/convention", resp.headers["Location"])

    @patch("routes.TTEClient")
    def test_select_api_error_shows_flash(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.get_convention.side_effect = TTEAPIError("Not found", 404)
        MockClient.return_value = mock_instance

        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"

        resp = self.client.post("/convention/select", data={"convention_id": "bad-id"})
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/convention", resp.headers["Location"])


class TestGamesRoute(unittest.TestCase):

    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.app.config["TTE_API_KEY"] = "test-key"
        self.client = self.app.test_client()

    def test_games_requires_login(self):
        resp = self.client.get("/games")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.headers["Location"])

    def test_games_requires_convention(self):
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"

        resp = self.client.get("/games")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/convention", resp.headers["Location"])

    @patch("routes.TTEClient")
    def test_games_loads_and_displays(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.get_library_games.return_value = [
            {"id": "G1", "name": "Catan"},
            {"id": "G2", "name": "Wingspan"},
        ]
        mock_instance.get_convention_playtowins.return_value = [
            {"badge_id": "B1", "librarygame_id": "G1", "id": "e1"},
            {"badge_id": "B2", "librarygame_id": "G1", "id": "e2"},
            {"badge_id": "B1", "librarygame_id": "G1", "id": "e3"},  # dup
            {"badge_id": None, "librarygame_id": "G2", "id": "e4"},  # no badge
            {"badge_id": "B3", "librarygame_id": "G2", "id": "e5"},
        ]
        MockClient.return_value = mock_instance

        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["library_id"] = "lib-1"
            sess["convention_id"] = "conv-1"
            sess["convention_name"] = "GameFest"

        resp = self.client.get("/games")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Catan", resp.data)
        self.assertIn(b"Wingspan", resp.data)
        # 3 unique entries after de-dup and badge filter
        self.assertIn(b"3", resp.data)

    @patch("routes.TTEClient")
    def test_games_shows_no_entries_badge(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.get_library_games.return_value = [
            {"id": "G1", "name": "Catan"},
        ]
        mock_instance.get_convention_playtowins.return_value = []
        MockClient.return_value = mock_instance

        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["library_id"] = "lib-1"
            sess["convention_id"] = "conv-1"
            sess["convention_name"] = "GameFest"

        resp = self.client.get("/games")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"No entries", resp.data)

    @patch("routes.TTEClient")
    def test_games_api_error_redirects(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.get_library_games.side_effect = TTEAPIError("API error")
        MockClient.return_value = mock_instance

        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["library_id"] = "lib-1"
            sess["convention_id"] = "conv-1"

        resp = self.client.get("/games")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/convention", resp.headers["Location"])

    @patch("routes.TTEClient")
    def test_games_uses_library_when_no_convention(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.get_library_games.return_value = []
        mock_instance.get_library_playtowins.return_value = []
        MockClient.return_value = mock_instance

        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["library_id"] = "lib-1"
            sess["convention_name"] = "Test"
            # no convention_id

        resp = self.client.get("/games")
        self.assertEqual(resp.status_code, 200)
        mock_instance.get_library_playtowins.assert_called_once_with("lib-1")


class TestPremiumGamesRoute(unittest.TestCase):

    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.app.config["TTE_API_KEY"] = "test-key"
        self.client = self.app.test_client()

    def test_set_premium_requires_login(self):
        resp = self.client.post("/games/premium",
                                json={"premium_games": ["G1"]})
        self.assertEqual(resp.status_code, 401)

    def test_set_premium_stores_in_session(self):
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"

        resp = self.client.post("/games/premium",
                                json={"premium_games": ["G1", "G2"]})
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["count"], 2)

        with self.client.session_transaction() as sess:
            self.assertEqual(sess["premium_games"], ["G1", "G2"])

    def test_set_premium_empty_list(self):
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["premium_games"] = ["G1"]

        resp = self.client.post("/games/premium",
                                json={"premium_games": []})
        self.assertEqual(resp.status_code, 200)

        with self.client.session_transaction() as sess:
            self.assertEqual(sess["premium_games"], [])

    def test_set_premium_invalid_body(self):
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"

        resp = self.client.post("/games/premium",
                                data="not json",
                                content_type="text/plain")
        self.assertEqual(resp.status_code, 400)

    def test_set_premium_missing_key(self):
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"

        resp = self.client.post("/games/premium",
                                json={"other": "data"})
        self.assertEqual(resp.status_code, 400)

    @patch("routes.TTEClient")
    def test_games_page_shows_premium_styling(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.get_library_games.return_value = [
            {"id": "G1", "name": "Catan"},
            {"id": "G2", "name": "Wingspan"},
        ]
        mock_instance.get_convention_playtowins.return_value = [
            {"badge_id": "B1", "librarygame_id": "G1", "id": "e1"},
        ]
        MockClient.return_value = mock_instance

        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["library_id"] = "lib-1"
            sess["convention_id"] = "conv-1"
            sess["convention_name"] = "GameFest"
            sess["premium_games"] = ["G1"]

        resp = self.client.get("/games")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Premium", resp.data)
        self.assertIn(b"checked", resp.data)

    @patch("routes.TTEClient")
    def test_games_page_no_premium(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.get_library_games.return_value = [
            {"id": "G1", "name": "Catan"},
        ]
        mock_instance.get_convention_playtowins.return_value = []
        MockClient.return_value = mock_instance

        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["library_id"] = "lib-1"
            sess["convention_id"] = "conv-1"
            sess["convention_name"] = "GameFest"
            # no premium_games in session

        resp = self.client.get("/games")
        self.assertEqual(resp.status_code, 200)
        # No premium-label badge should appear (the column header "Premium" will exist)
        self.assertNotIn(b'class="premium-label"', resp.data)


class TestDrawingRoutes(unittest.TestCase):

    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.app.config["TTE_API_KEY"] = "test-key"
        self.client = self.app.test_client()

    def test_drawing_requires_auth(self):
        resp = self.client.post("/drawing")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.headers["Location"])

    def test_drawing_requires_convention(self):
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"

        resp = self.client.post("/drawing")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/convention", resp.headers["Location"])

    @patch("routes.TTEClient")
    def test_drawing_runs_and_shows_results(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.get_library_games.return_value = [
            {"id": "G1", "name": "Catan"},
            {"id": "G2", "name": "Ticket to Ride"},
        ]
        mock_instance.get_convention_playtowins.return_value = [
            {"id": "e1", "badge_id": "B1", "librarygame_id": "G1", "name": "Alice"},
            {"id": "e2", "badge_id": "B2", "librarygame_id": "G2", "name": "Bob"},
        ]
        MockClient.return_value = mock_instance

        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["library_id"] = "lib-1"
            sess["convention_id"] = "conv-1"
            sess["convention_name"] = "GameFest"

        resp = self.client.post("/drawing")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Drawing Results", resp.data)
        self.assertIn(b"Catan", resp.data)
        self.assertIn(b"Ticket to Ride", resp.data)

    @patch("routes.TTEClient")
    def test_drawing_with_conflict_shows_panel(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.get_library_games.return_value = [
            {"id": "G1", "name": "Catan"},
            {"id": "G2", "name": "Ticket to Ride"},
        ]
        # B1 entered both games -> potential conflict
        mock_instance.get_convention_playtowins.return_value = [
            {"id": "e1", "badge_id": "B1", "librarygame_id": "G1", "name": "Alice"},
            {"id": "e2", "badge_id": "B1", "librarygame_id": "G2", "name": "Alice"},
        ]
        MockClient.return_value = mock_instance

        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["library_id"] = "lib-1"
            sess["convention_id"] = "conv-1"
            sess["convention_name"] = "GameFest"

        resp = self.client.post("/drawing")
        self.assertEqual(resp.status_code, 200)
        # B1 must win both since they're the only entrant — conflict
        self.assertIn(b"Multi-Win Conflicts", resp.data)
        # Verify the person's name is shown, not just badge
        self.assertIn(b"Alice", resp.data)
        # Verify conflict badge on the results table
        self.assertIn(b'class="conflict-badge"', resp.data)

    @patch("routes.TTEClient")
    def test_drawing_conflict_shows_rerun_button(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.get_library_games.return_value = [
            {"id": "G1", "name": "Catan"},
        ]
        mock_instance.get_convention_playtowins.return_value = [
            {"id": "e1", "badge_id": "B1", "librarygame_id": "G1", "name": "Alice"},
        ]
        MockClient.return_value = mock_instance

        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["library_id"] = "lib-1"
            sess["convention_id"] = "conv-1"
            sess["convention_name"] = "GameFest"

        resp = self.client.post("/drawing")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Re-run Drawing", resp.data)

    @patch("routes.TTEClient")
    def test_drawing_separates_premium_conflicts(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.get_library_games.return_value = [
            {"id": "G1", "name": "Catan"},
            {"id": "G2", "name": "Ticket to Ride"},
            {"id": "G3", "name": "Wingspan"},
            {"id": "G4", "name": "Azul"},
        ]
        # B1 wins G1+G2 (both premium), B2 wins G3+G4 (not premium)
        mock_instance.get_convention_playtowins.return_value = [
            {"id": "e1", "badge_id": "B1", "librarygame_id": "G1", "name": "Alice"},
            {"id": "e2", "badge_id": "B1", "librarygame_id": "G2", "name": "Alice"},
            {"id": "e3", "badge_id": "B2", "librarygame_id": "G3", "name": "Bob"},
            {"id": "e4", "badge_id": "B2", "librarygame_id": "G4", "name": "Bob"},
        ]
        MockClient.return_value = mock_instance

        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["library_id"] = "lib-1"
            sess["convention_id"] = "conv-1"
            sess["convention_name"] = "GameFest"
            sess["premium_games"] = ["G1", "G2"]

        resp = self.client.post("/drawing")
        self.assertEqual(resp.status_code, 200)
        # Separate sections for premium and standard conflicts
        self.assertIn(b"Premium Game Conflicts", resp.data)
        self.assertIn(b"Multi-Win Conflicts", resp.data)

    def test_resolve_requires_auth(self):
        resp = self.client.post("/drawing/resolve",
                                json={"resolutions": []},
                                content_type="application/json")
        self.assertEqual(resp.status_code, 401)

    def test_resolve_requires_drawing_state(self):
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"

        resp = self.client.post("/drawing/resolve",
                                json={"resolutions": []},
                                content_type="application/json")
        self.assertEqual(resp.status_code, 400)

    def test_resolve_applies_resolution(self):
        drawing_state = [
            {
                "game": {"id": "G1", "name": "Catan"},
                "shuffled": [
                    {"badge_id": "B1", "librarygame_id": "G1", "id": "e1", "name": "Alice"},
                    {"badge_id": "B2", "librarygame_id": "G1", "id": "e3", "name": "Bob"},
                ],
                "winner_index": 0,
            },
            {
                "game": {"id": "G2", "name": "Ticket to Ride"},
                "shuffled": [
                    {"badge_id": "B1", "librarygame_id": "G2", "id": "e2", "name": "Alice"},
                    {"badge_id": "B3", "librarygame_id": "G2", "id": "e4", "name": "Carol"},
                ],
                "winner_index": 0,
            },
        ]

        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["drawing_state"] = drawing_state
            sess["premium_games"] = []

        resp = self.client.post("/drawing/resolve",
                                json={"resolutions": [
                                    {"badge_id": "B1", "keep_game_id": "G1"}
                                ]},
                                content_type="application/json")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["ok"])

        # B1 keeps G1, G2 advanced to B3
        winners = {r["game_id"]: r["winner_badge"] for r in data["results"]}
        self.assertEqual(winners["G1"], "B1")
        self.assertEqual(winners["G2"], "B3")
        # Verify no remaining conflicts
        self.assertEqual(data["conflicts"], [])

    def test_resolve_cascading_conflict_returns_new_conflicts(self):
        # B1 wins G1+G2, B2 also entered G2 and G3.
        # Resolving B1 -> keep G1 cascades G2 to B2, who now wins G2+G3.
        drawing_state = [
            {
                "game": {"id": "G1", "name": "Catan"},
                "shuffled": [
                    {"badge_id": "B1", "librarygame_id": "G1", "id": "e1", "name": "Alice"},
                ],
                "winner_index": 0,
            },
            {
                "game": {"id": "G2", "name": "Ticket to Ride"},
                "shuffled": [
                    {"badge_id": "B1", "librarygame_id": "G2", "id": "e2", "name": "Alice"},
                    {"badge_id": "B2", "librarygame_id": "G2", "id": "e3", "name": "Bob"},
                ],
                "winner_index": 0,
            },
            {
                "game": {"id": "G3", "name": "Wingspan"},
                "shuffled": [
                    {"badge_id": "B2", "librarygame_id": "G3", "id": "e4", "name": "Bob"},
                ],
                "winner_index": 0,
            },
        ]

        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["drawing_state"] = drawing_state
            sess["premium_games"] = []

        resp = self.client.post("/drawing/resolve",
                                json={"resolutions": [
                                    {"badge_id": "B1", "keep_game_id": "G1"}
                                ]},
                                content_type="application/json")
        data = resp.get_json()
        self.assertTrue(data["ok"])
        # B2 now has a cascading conflict
        self.assertEqual(len(data["conflicts"]), 1)
        self.assertEqual(data["conflicts"][0]["badge_id"], "B2")
        self.assertEqual(data["conflicts"][0]["winner_name"], "Bob")

    @patch("routes.TTEClient")
    def test_drawing_has_view_tabs(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.get_library_games.return_value = [
            {"id": "G1", "name": "Catan"},
        ]
        mock_instance.get_convention_playtowins.return_value = [
            {"id": "e1", "badge_id": "B1", "librarygame_id": "G1", "name": "Alice"},
        ]
        MockClient.return_value = mock_instance

        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["library_id"] = "lib-1"
            sess["convention_id"] = "conv-1"
            sess["convention_name"] = "GameFest"

        resp = self.client.post("/drawing")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"By Game", resp.data)
        self.assertIn(b"By Winner", resp.data)
        self.assertIn(b'id="tab-by-game"', resp.data)
        self.assertIn(b'id="tab-by-winner"', resp.data)
        self.assertIn(b'id="panel-by-game"', resp.data)
        self.assertIn(b'id="panel-by-winner"', resp.data)

    @patch("routes.TTEClient")
    def test_by_game_view_shows_all_games(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.get_library_games.return_value = [
            {"id": "G1", "name": "Catan"},
            {"id": "G2", "name": "Ticket to Ride"},
        ]
        mock_instance.get_convention_playtowins.return_value = [
            {"id": "e1", "badge_id": "B1", "librarygame_id": "G1", "name": "Alice"},
        ]
        MockClient.return_value = mock_instance

        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["library_id"] = "lib-1"
            sess["convention_id"] = "conv-1"
            sess["convention_name"] = "GameFest"

        resp = self.client.post("/drawing")
        html = resp.data.decode()
        # By Game panel shows both games
        self.assertIn("Catan", html)
        self.assertIn("Ticket to Ride", html)
        # Game with no entries shows "No entries"
        self.assertIn("No entries", html)

    @patch("routes.TTEClient")
    def test_by_winner_view_shows_winners_only(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.get_library_games.return_value = [
            {"id": "G1", "name": "Catan"},
            {"id": "G2", "name": "Ticket to Ride"},
        ]
        mock_instance.get_convention_playtowins.return_value = [
            {"id": "e1", "badge_id": "B1", "librarygame_id": "G1", "name": "Alice"},
        ]
        MockClient.return_value = mock_instance

        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["library_id"] = "lib-1"
            sess["convention_id"] = "conv-1"
            sess["convention_name"] = "GameFest"

        resp = self.client.post("/drawing")
        html = resp.data.decode()
        # The winner table (By Winner view) should have Alice once
        # The By Winner table is inside panel-by-winner
        winner_panel_start = html.index('id="panel-by-winner"')
        winner_panel = html[winner_panel_start:]
        self.assertIn("Alice", winner_panel)
        self.assertIn("Catan", winner_panel)
        # Ticket to Ride has no entries, so shouldn't appear in winner table
        winner_table_start = winner_panel.index('id="winner-table"')
        winner_table_end = winner_panel.index('</table>')
        winner_table = winner_panel[winner_table_start:winner_table_end]
        self.assertNotIn("Ticket to Ride", winner_table)

    @patch("routes.TTEClient")
    def test_by_winner_view_highlights_premium(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.get_library_games.return_value = [
            {"id": "G1", "name": "Catan"},
            {"id": "G2", "name": "Ticket to Ride"},
        ]
        mock_instance.get_convention_playtowins.return_value = [
            {"id": "e1", "badge_id": "B1", "librarygame_id": "G1", "name": "Alice"},
            {"id": "e2", "badge_id": "B2", "librarygame_id": "G2", "name": "Bob"},
        ]
        MockClient.return_value = mock_instance

        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["library_id"] = "lib-1"
            sess["convention_id"] = "conv-1"
            sess["convention_name"] = "GameFest"
            sess["premium_games"] = ["G1"]

        resp = self.client.post("/drawing")
        html = resp.data.decode()
        # By Winner table should show Premium label for Catan
        winner_panel_start = html.index('id="panel-by-winner"')
        winner_panel = html[winner_panel_start:]
        self.assertIn("Premium", winner_panel)

    @patch("routes.TTEClient")
    def test_drawing_shows_pickup_summary(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.get_library_games.return_value = [
            {"id": "G1", "name": "Catan"},
        ]
        mock_instance.get_convention_playtowins.return_value = [
            {"id": "e1", "badge_id": "B1", "librarygame_id": "G1", "name": "Alice"},
        ]
        MockClient.return_value = mock_instance

        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["library_id"] = "lib-1"
            sess["convention_id"] = "conv-1"
            sess["convention_name"] = "GameFest"

        resp = self.client.post("/drawing")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"picked up", resp.data)
        self.assertIn(b'id="pickup-count"', resp.data)

    @patch("routes.TTEClient")
    def test_drawing_shows_pickup_buttons(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.get_library_games.return_value = [
            {"id": "G1", "name": "Catan"},
            {"id": "G2", "name": "Ticket to Ride"},
        ]
        mock_instance.get_convention_playtowins.return_value = [
            {"id": "e1", "badge_id": "B1", "librarygame_id": "G1", "name": "Alice"},
        ]
        MockClient.return_value = mock_instance

        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["library_id"] = "lib-1"
            sess["convention_id"] = "conv-1"
            sess["convention_name"] = "GameFest"

        resp = self.client.post("/drawing")
        html = resp.data.decode()
        # Game with winner should have pickup button
        self.assertIn("Mark Picked Up", html)

    def test_pickup_requires_auth(self):
        resp = self.client.post("/drawing/pickup",
                                json={"game_id": "G1"},
                                content_type="application/json")
        self.assertEqual(resp.status_code, 401)

    def test_pickup_requires_drawing_state(self):
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"

        resp = self.client.post("/drawing/pickup",
                                json={"game_id": "G1"},
                                content_type="application/json")
        self.assertEqual(resp.status_code, 400)

    def test_pickup_requires_game_id(self):
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["drawing_state"] = [{"game": {"id": "G1"}, "shuffled": [], "winner_index": 0}]

        resp = self.client.post("/drawing/pickup",
                                json={},
                                content_type="application/json")
        self.assertEqual(resp.status_code, 400)

    def test_pickup_toggle_marks_picked_up(self):
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["drawing_state"] = [{"game": {"id": "G1"}, "shuffled": [], "winner_index": 0}]
            sess["picked_up"] = []

        resp = self.client.post("/drawing/pickup",
                                json={"game_id": "G1"},
                                content_type="application/json")
        data = resp.get_json()
        self.assertTrue(data["ok"])
        self.assertTrue(data["is_picked_up"])
        self.assertEqual(data["picked_up_count"], 1)

        # Verify session was updated
        with self.client.session_transaction() as sess:
            self.assertIn("G1", sess["picked_up"])

    def test_pickup_toggle_unmarks_picked_up(self):
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["drawing_state"] = [{"game": {"id": "G1"}, "shuffled": [], "winner_index": 0}]
            sess["picked_up"] = ["G1"]

        resp = self.client.post("/drawing/pickup",
                                json={"game_id": "G1"},
                                content_type="application/json")
        data = resp.get_json()
        self.assertTrue(data["ok"])
        self.assertFalse(data["is_picked_up"])
        self.assertEqual(data["picked_up_count"], 0)

        with self.client.session_transaction() as sess:
            self.assertNotIn("G1", sess["picked_up"])

    @patch("routes.TTEClient")
    def test_rerun_drawing_clears_pickup(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.get_library_games.return_value = [
            {"id": "G1", "name": "Catan"},
        ]
        mock_instance.get_convention_playtowins.return_value = [
            {"id": "e1", "badge_id": "B1", "librarygame_id": "G1", "name": "Alice"},
        ]
        MockClient.return_value = mock_instance

        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["library_id"] = "lib-1"
            sess["convention_id"] = "conv-1"
            sess["convention_name"] = "GameFest"
            sess["picked_up"] = ["G1"]

        self.client.post("/drawing")

        with self.client.session_transaction() as sess:
            self.assertEqual(sess["picked_up"], [])

    @patch("routes.TTEClient")
    def test_drawing_shows_redistribution_button(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.get_library_games.return_value = [
            {"id": "G1", "name": "Catan"},
        ]
        mock_instance.get_convention_playtowins.return_value = [
            {"id": "e1", "badge_id": "B1", "librarygame_id": "G1", "name": "Alice"},
        ]
        MockClient.return_value = mock_instance

        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["library_id"] = "lib-1"
            sess["convention_id"] = "conv-1"
            sess["convention_name"] = "GameFest"

        resp = self.client.post("/drawing")
        self.assertIn(b"Start Redistribution", resp.data)


class TestRedistributionRoutes(unittest.TestCase):

    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.app.config["TTE_API_KEY"] = "test-key"
        self.client = self.app.test_client()

    def _setup_drawing_state(self, picked_up=None):
        """Helper to set up session with a drawing state."""
        drawing_state = [
            {
                "game": {"id": "G1", "name": "Catan"},
                "shuffled": [
                    {"badge_id": "B1", "librarygame_id": "G1", "id": "e1", "name": "Alice"},
                    {"badge_id": "B2", "librarygame_id": "G1", "id": "e2", "name": "Bob"},
                    {"badge_id": "B3", "librarygame_id": "G1", "id": "e3", "name": "Carol"},
                ],
                "winner_index": 0,
            },
            {
                "game": {"id": "G2", "name": "Ticket to Ride"},
                "shuffled": [
                    {"badge_id": "B4", "librarygame_id": "G2", "id": "e4", "name": "Dave"},
                ],
                "winner_index": 0,
            },
        ]
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["drawing_state"] = drawing_state
            sess["convention_name"] = "GameFest"
            sess["picked_up"] = picked_up or []
            sess["redistribution_declined"] = {}
            sess["redistribution_winners"] = {}

    def test_redistribute_requires_auth(self):
        resp = self.client.get("/drawing/redistribute")
        self.assertEqual(resp.status_code, 302)

    def test_redistribute_requires_drawing_state(self):
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
        resp = self.client.get("/drawing/redistribute")
        self.assertEqual(resp.status_code, 302)

    def test_redistribute_shows_unclaimed_games(self):
        self._setup_drawing_state(picked_up=["G2"])
        resp = self.client.get("/drawing/redistribute")
        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode()
        # G1 is unclaimed, so it should appear
        self.assertIn("Catan", html)
        # G2 is picked up, so it should NOT appear
        self.assertNotIn("Ticket to Ride", html)
        # Shows unclaimed count
        self.assertIn("1", html)

    def test_redistribute_shows_entrant_list(self):
        self._setup_drawing_state(picked_up=["G2"])
        resp = self.client.get("/drawing/redistribute")
        html = resp.data.decode()
        # All 3 entrants should be listed for Catan
        self.assertIn("Alice", html)
        self.assertIn("Bob", html)
        self.assertIn("Carol", html)
        # Original winner tag
        self.assertIn("Original Winner", html)

    def test_redistribute_all_picked_up(self):
        self._setup_drawing_state(picked_up=["G1", "G2"])
        resp = self.client.get("/drawing/redistribute")
        html = resp.data.decode()
        self.assertIn("All games have been picked up", html)

    def test_redistribute_claim_requires_auth(self):
        resp = self.client.post("/drawing/redistribute/claim",
                                json={"game_id": "G1", "badge_id": "B2", "action": "claim"},
                                content_type="application/json")
        self.assertEqual(resp.status_code, 401)

    def test_redistribute_claim_requires_drawing_state(self):
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
        resp = self.client.post("/drawing/redistribute/claim",
                                json={"game_id": "G1", "badge_id": "B2", "action": "claim"},
                                content_type="application/json")
        self.assertEqual(resp.status_code, 400)

    def test_redistribute_claim_validates_input(self):
        self._setup_drawing_state()
        resp = self.client.post("/drawing/redistribute/claim",
                                json={"game_id": "G1"},
                                content_type="application/json")
        self.assertEqual(resp.status_code, 400)

    def test_redistribute_claim_invalid_action(self):
        self._setup_drawing_state()
        resp = self.client.post("/drawing/redistribute/claim",
                                json={"game_id": "G1", "badge_id": "B2", "action": "invalid"},
                                content_type="application/json")
        self.assertEqual(resp.status_code, 400)

    def test_redistribute_claim_marks_winner(self):
        self._setup_drawing_state()
        resp = self.client.post("/drawing/redistribute/claim",
                                json={"game_id": "G1", "badge_id": "B2", "action": "claim"},
                                content_type="application/json")
        data = resp.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["action"], "claim")

        with self.client.session_transaction() as sess:
            self.assertEqual(sess["redistribution_winners"]["G1"], "B2")

    def test_redistribute_decline_stores_in_session(self):
        self._setup_drawing_state()
        resp = self.client.post("/drawing/redistribute/claim",
                                json={"game_id": "G1", "badge_id": "B1", "action": "decline"},
                                content_type="application/json")
        data = resp.get_json()
        self.assertTrue(data["ok"])

        with self.client.session_transaction() as sess:
            self.assertIn("B1", sess["redistribution_declined"]["G1"])

    def test_redistribute_decline_removes_winner(self):
        self._setup_drawing_state()
        # First claim B2
        self.client.post("/drawing/redistribute/claim",
                         json={"game_id": "G1", "badge_id": "B2", "action": "claim"},
                         content_type="application/json")
        # Then decline B2
        self.client.post("/drawing/redistribute/claim",
                         json={"game_id": "G1", "badge_id": "B2", "action": "decline"},
                         content_type="application/json")

        with self.client.session_transaction() as sess:
            self.assertNotIn("G1", sess["redistribution_winners"])

    def test_redistribute_page_shows_declined(self):
        self._setup_drawing_state(picked_up=["G2"])
        # Decline B1
        self.client.post("/drawing/redistribute/claim",
                         json={"game_id": "G1", "badge_id": "B1", "action": "decline"},
                         content_type="application/json")
        resp = self.client.get("/drawing/redistribute")
        html = resp.data.decode()
        self.assertIn("Declined / Absent", html)

    def test_redistribute_page_shows_new_winner(self):
        self._setup_drawing_state(picked_up=["G2"])
        # Claim B2 as new winner
        self.client.post("/drawing/redistribute/claim",
                         json={"game_id": "G1", "badge_id": "B2", "action": "claim"},
                         content_type="application/json")
        resp = self.client.get("/drawing/redistribute")
        html = resp.data.decode()
        self.assertIn("New Winner", html)

    @patch("routes.TTEClient")
    def test_rerun_clears_redistribution(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.get_library_games.return_value = [
            {"id": "G1", "name": "Catan"},
        ]
        mock_instance.get_convention_playtowins.return_value = [
            {"id": "e1", "badge_id": "B1", "librarygame_id": "G1", "name": "Alice"},
        ]
        MockClient.return_value = mock_instance

        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["library_id"] = "lib-1"
            sess["convention_id"] = "conv-1"
            sess["convention_name"] = "GameFest"
            sess["redistribution_declined"] = {"G1": ["B1"]}
            sess["redistribution_winners"] = {"G1": "B2"}

        self.client.post("/drawing")

        with self.client.session_transaction() as sess:
            self.assertEqual(sess["redistribution_declined"], {})
            self.assertEqual(sess["redistribution_winners"], {})


class TestPushToTTE(unittest.TestCase):

    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.app.config["TTE_API_KEY"] = "test-key"
        self.client = self.app.test_client()

    def _setup_session(self, picked_up=None, redist_winners=None):
        drawing_state = [
            {
                "game": {"id": "G1", "name": "Catan"},
                "shuffled": [
                    {"badge_id": "B1", "librarygame_id": "G1", "id": "e1", "name": "Alice"},
                    {"badge_id": "B2", "librarygame_id": "G1", "id": "e2", "name": "Bob"},
                ],
                "winner_index": 0,
            },
            {
                "game": {"id": "G2", "name": "Ticket to Ride"},
                "shuffled": [
                    {"badge_id": "B3", "librarygame_id": "G2", "id": "e3", "name": "Carol"},
                ],
                "winner_index": 0,
            },
        ]
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["drawing_state"] = drawing_state
            sess["picked_up"] = picked_up or []
            sess["redistribution_winners"] = redist_winners or {}

    def test_push_requires_auth(self):
        resp = self.client.post("/drawing/push",
                                content_type="application/json")
        self.assertEqual(resp.status_code, 401)

    def test_push_requires_drawing_state(self):
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
        resp = self.client.post("/drawing/push",
                                content_type="application/json")
        self.assertEqual(resp.status_code, 400)

    def test_push_requires_picked_up(self):
        self._setup_session(picked_up=[])
        resp = self.client.post("/drawing/push",
                                content_type="application/json")
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertIn("No games", data["error"])

    @patch("routes.TTEClient")
    def test_push_updates_picked_up_games(self, MockClient):
        mock_instance = MagicMock()
        MockClient.return_value = mock_instance

        self._setup_session(picked_up=["G1", "G2"])
        resp = self.client.post("/drawing/push",
                                content_type="application/json")
        data = resp.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["successes"], 2)
        self.assertEqual(data["total"], 2)
        self.assertEqual(data["failures"], [])

        # Verify update_playtowin was called for each game's winner entry
        calls = mock_instance.update_playtowin.call_args_list
        called_ids = {call[0][0] for call in calls}
        self.assertEqual(called_ids, {"e1", "e3"})
        for call in calls:
            self.assertEqual(call[0][1], {"win": 1})

    @patch("routes.TTEClient")
    def test_push_uses_redistribution_winner(self, MockClient):
        mock_instance = MagicMock()
        MockClient.return_value = mock_instance

        # G1 was redistributed to B2 (entry e2)
        self._setup_session(picked_up=["G1"], redist_winners={"G1": "B2"})
        resp = self.client.post("/drawing/push",
                                content_type="application/json")
        data = resp.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["successes"], 1)

        # Should update e2 (Bob's entry), not e1 (Alice's)
        mock_instance.update_playtowin.assert_called_once_with("e2", {"win": 1})

    @patch("routes.TTEClient")
    def test_push_handles_partial_failure(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.update_playtowin.side_effect = [
            None,  # first call succeeds
            TTEAPIError("Server error", 500),  # second call fails
        ]
        MockClient.return_value = mock_instance

        self._setup_session(picked_up=["G1", "G2"])
        resp = self.client.post("/drawing/push",
                                content_type="application/json")
        data = resp.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["successes"], 1)
        self.assertEqual(len(data["failures"]), 1)
        self.assertIn("Server error", data["failures"][0]["error"])

    @patch("routes.TTEClient")
    def test_push_button_in_results(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.get_library_games.return_value = [
            {"id": "G1", "name": "Catan"},
        ]
        mock_instance.get_convention_playtowins.return_value = [
            {"id": "e1", "badge_id": "B1", "librarygame_id": "G1", "name": "Alice"},
        ]
        MockClient.return_value = mock_instance

        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["library_id"] = "lib-1"
            sess["convention_id"] = "conv-1"
            sess["convention_name"] = "GameFest"

        resp = self.client.post("/drawing")
        self.assertIn(b"Push to TTE", resp.data)
        self.assertIn(b'id="push-btn"', resp.data)


class TestCSVExport(unittest.TestCase):

    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.app.config["TTE_API_KEY"] = "test-key"
        self.client = self.app.test_client()

    def _setup_session(self, picked_up=None, premium=None, redist_winners=None,
                       convention_name="PawCon 2026"):
        drawing_state = [
            {
                "game": {"id": "G1", "name": "Catan"},
                "shuffled": [
                    {"badge_id": "B1", "librarygame_id": "G1", "id": "e1", "name": "Alice"},
                    {"badge_id": "B2", "librarygame_id": "G1", "id": "e2", "name": "Bob"},
                ],
                "winner_index": 0,
            },
            {
                "game": {"id": "G2", "name": "Ticket to Ride"},
                "shuffled": [
                    {"badge_id": "B3", "librarygame_id": "G2", "id": "e3", "name": "Carol"},
                ],
                "winner_index": 0,
            },
        ]
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["convention_name"] = convention_name
            sess["drawing_state"] = drawing_state
            sess["picked_up"] = picked_up or []
            sess["premium_games"] = premium or []
            sess["redistribution_winners"] = redist_winners or {}

    def test_export_requires_auth(self):
        resp = self.client.get("/drawing/export")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.headers["Location"])

    def test_export_requires_drawing_state(self):
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
        resp = self.client.get("/drawing/export")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/games", resp.headers["Location"])

    def test_export_returns_csv_content_type(self):
        self._setup_session()
        resp = self.client.get("/drawing/export")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/csv", resp.content_type)

    def test_export_has_content_disposition(self):
        self._setup_session()
        resp = self.client.get("/drawing/export")
        disposition = resp.headers.get("Content-Disposition", "")
        self.assertIn("attachment", disposition)
        self.assertIn("PawDrawing_", disposition)
        self.assertIn(".csv", disposition)

    def test_export_filename_contains_convention_name(self):
        self._setup_session(convention_name="PawCon 2026")
        resp = self.client.get("/drawing/export")
        disposition = resp.headers["Content-Disposition"]
        self.assertIn("PawCon_2026", disposition)

    def test_export_filename_sanitizes_special_chars(self):
        self._setup_session(convention_name="Con/Event: Test!")
        resp = self.client.get("/drawing/export")
        disposition = resp.headers["Content-Disposition"]
        # Special chars removed, spaces become underscores
        self.assertNotIn("/", disposition.split("filename=")[1])
        self.assertNotIn(":", disposition.split("filename=")[1])
        self.assertNotIn("!", disposition.split("filename=")[1])

    def test_export_csv_headers(self):
        self._setup_session()
        resp = self.client.get("/drawing/export")
        lines = resp.data.decode().strip().split("\r\n")
        self.assertEqual(lines[0], "Game,Premium,Entries,Winner,Badge,Picked Up")

    def test_export_csv_data_rows(self):
        self._setup_session()
        resp = self.client.get("/drawing/export")
        lines = resp.data.decode().strip().split("\r\n")
        # Header + 2 data rows
        self.assertEqual(len(lines), 3)
        # Rows sorted by game name: Catan before Ticket to Ride
        self.assertTrue(lines[1].startswith("Catan,"))
        self.assertTrue(lines[2].startswith("Ticket to Ride,"))

    def test_export_csv_winner_data(self):
        self._setup_session()
        resp = self.client.get("/drawing/export")
        lines = resp.data.decode().strip().split("\r\n")
        # Catan: winner is Alice (index 0), 2 entries
        self.assertIn("Alice", lines[1])
        self.assertIn("B1", lines[1])
        self.assertIn(",2,", lines[1])
        # Ticket to Ride: winner is Carol, 1 entry
        self.assertIn("Carol", lines[2])
        self.assertIn("B3", lines[2])
        self.assertIn(",1,", lines[2])

    def test_export_premium_column(self):
        self._setup_session(premium=["G1"])
        resp = self.client.get("/drawing/export")
        lines = resp.data.decode().strip().split("\r\n")
        # Catan is premium
        self.assertIn("Catan,Yes,", lines[1])
        # Ticket to Ride is not premium
        self.assertIn("Ticket to Ride,No,", lines[2])

    def test_export_picked_up_column(self):
        self._setup_session(picked_up=["G1"])
        resp = self.client.get("/drawing/export")
        lines = resp.data.decode().strip().split("\r\n")
        # Catan picked up -> Yes
        self.assertTrue(lines[1].endswith(",Yes"))
        # Ticket to Ride not picked up -> No
        self.assertTrue(lines[2].endswith(",No"))

    def test_export_redistribution_winner(self):
        # G1 redistribution winner is Bob (B2)
        self._setup_session(redist_winners={"G1": "B2"})
        resp = self.client.get("/drawing/export")
        lines = resp.data.decode().strip().split("\r\n")
        # Winner should be Bob instead of Alice
        self.assertIn("Bob", lines[1])
        self.assertIn("B2", lines[1])

    def test_export_button_on_results_page(self):
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["convention_id"] = "conv-1"
            sess["convention_name"] = "Test Con"
            sess["library_id"] = "lib-1"
            sess["library_name"] = "P2W Library"
            sess["premium_games"] = []
        with patch("routes.TTEClient") as MockClient:
            mock_instance = MagicMock()
            mock_instance.get_playtowin_entries.return_value = [
                {"librarygame_id": "G1", "badge_id": "B1", "id": "e1",
                 "name": "Alice", "gamename": "Catan"},
            ]
            MockClient.return_value = mock_instance
            resp = self.client.post("/drawing")
        self.assertIn(b"Export CSV", resp.data)


class TestErrorHandlingRoutes(unittest.TestCase):
    """Tests for consistent error handling across routes."""

    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.app.config["TTE_API_KEY"] = "test-key"
        self.client = self.app.test_client()

    def _setup_session(self):
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["convention_id"] = "conv-1"
            sess["convention_name"] = "Test Con"
            sess["library_id"] = "lib-1"
            sess["library_name"] = "P2W Library"
            sess["premium_games"] = []

    # ── Auth expiration clears session ─────────────────────────────────

    @patch("routes.TTEClient")
    def test_convention_select_auth_error_clears_session(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.get_convention.side_effect = TTEAPIError("Unauthorized", 401)
        MockClient.return_value = mock_instance
        self._setup_session()

        resp = self.client.post("/convention/select",
                                data={"convention_id": "conv-1"})
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.headers["Location"])

        with self.client.session_transaction() as sess:
            self.assertNotIn("tte_session_id", sess)

    @patch("routes.TTEClient")
    def test_games_auth_error_clears_session(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.get_library_games.side_effect = TTEAPIError("Forbidden", 403)
        MockClient.return_value = mock_instance
        self._setup_session()

        resp = self.client.get("/games")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.headers["Location"])

        with self.client.session_transaction() as sess:
            self.assertNotIn("tte_session_id", sess)

    @patch("routes.TTEClient")
    def test_drawing_auth_error_clears_session(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.get_library_games.side_effect = TTEAPIError("Expired", 401)
        MockClient.return_value = mock_instance
        self._setup_session()

        resp = self.client.post("/drawing")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.headers["Location"])

        with self.client.session_transaction() as sess:
            self.assertNotIn("tte_session_id", sess)

    @patch("routes.TTEClient")
    def test_search_auth_error_returns_401(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.search_conventions.side_effect = TTEAPIError("Expired", 401)
        MockClient.return_value = mock_instance

        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"

        resp = self.client.get("/convention/search?q=test")
        self.assertEqual(resp.status_code, 401)
        data = resp.get_json()
        self.assertIn("expired", data["error"].lower())

    @patch("routes.TTEClient")
    def test_push_auth_error_returns_401(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.update_playtowin.side_effect = TTEAPIError("Expired", 401)
        MockClient.return_value = mock_instance

        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["drawing_state"] = [{
                "game": {"id": "G1", "name": "Catan"},
                "shuffled": [{"badge_id": "B1", "id": "e1", "name": "Alice"}],
                "winner_index": 0,
            }]
            sess["picked_up"] = ["G1"]
            sess["redistribution_winners"] = {}

        resp = self.client.post("/drawing/push",
                                content_type="application/json")
        self.assertEqual(resp.status_code, 401)
        data = resp.get_json()
        self.assertIn("expired", data["error"].lower())

    # ── Timeout produces friendly message ──────────────────────────────

    @patch("routes.TTEClient")
    def test_games_timeout_shows_friendly_message(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.get_library_games.side_effect = TTETimeoutError()
        MockClient.return_value = mock_instance
        self._setup_session()

        resp = self.client.get("/games", follow_redirects=True)
        self.assertIn(b"timed out", resp.data)
        self.assertIn(b"try again", resp.data.lower())

    @patch("routes.TTEClient")
    def test_drawing_timeout_shows_friendly_message(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.get_library_games.side_effect = TTETimeoutError()
        MockClient.return_value = mock_instance
        self._setup_session()

        resp = self.client.post("/drawing", follow_redirects=True)
        self.assertIn(b"timed out", resp.data)

    @patch("routes.TTEClient")
    def test_convention_timeout_shows_friendly_message(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.get_convention.side_effect = TTETimeoutError()
        MockClient.return_value = mock_instance
        self._setup_session()

        resp = self.client.post("/convention/select",
                                data={"convention_id": "conv-1"},
                                follow_redirects=True)
        self.assertIn(b"timed out", resp.data)

    @patch("routes.TTEClient")
    def test_search_timeout_returns_error(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.search_conventions.side_effect = TTETimeoutError()
        MockClient.return_value = mock_instance

        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"

        resp = self.client.get("/convention/search?q=test")
        self.assertEqual(resp.status_code, 502)
        data = resp.get_json()
        self.assertIn("timed out", data["error"].lower())

    # ── Non-auth API errors show descriptive flash ─────────────────────

    @patch("routes.TTEClient")
    def test_games_500_error_shows_action_message(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.get_library_games.side_effect = TTEAPIError("Server error", 500)
        MockClient.return_value = mock_instance
        self._setup_session()

        resp = self.client.get("/games", follow_redirects=True)
        self.assertIn(b"Could not load games", resp.data)

    @patch("routes.TTEClient")
    def test_games_entry_loading_error_shows_action(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.get_library_games.return_value = []
        mock_instance.get_convention_playtowins.side_effect = TTEAPIError("Server error", 500)
        MockClient.return_value = mock_instance
        self._setup_session()

        resp = self.client.get("/games", follow_redirects=True)
        self.assertIn(b"Could not load entries", resp.data)

    @patch("routes.TTEClient")
    def test_drawing_entry_loading_error_shows_action(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.get_library_games.return_value = []
        mock_instance.get_convention_playtowins.side_effect = TTEAPIError("Not found", 404)
        MockClient.return_value = mock_instance
        self._setup_session()

        resp = self.client.post("/drawing", follow_redirects=True)
        self.assertIn(b"Could not load entries", resp.data)


if __name__ == "__main__":
    unittest.main()
