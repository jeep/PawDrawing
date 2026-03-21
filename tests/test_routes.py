"""Tests for login/logout routes."""

import unittest
from unittest.mock import patch, MagicMock

from app import create_app
from tte_client import TTEAPIError


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
        self.assertIn(b"Conflicts Requiring Resolution", resp.data)

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


if __name__ == "__main__":
    unittest.main()
