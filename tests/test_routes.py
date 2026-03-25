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
        resp = self.client.post("/login", data={
            "username": "", "password": "", "api_key": "",
        })
        self.assertEqual(resp.status_code, 400)
        self.assertIn(b"required", resp.data)

    @patch("routes.auth.TTEClient")
    def test_login_success_redirects_to_convention(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.session_id = "session-123"
        mock_instance.user_id = "user-456"
        mock_instance.login.return_value = {"id": "session-123"}
        MockClient.return_value = mock_instance

        resp = self.client.post("/login", data={
            "username": "admin",
            "password": "secret",
            "api_key": "user-api-key",
        })
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/convention", resp.headers["Location"])
        MockClient.assert_called_once_with(api_key_id="user-api-key")
        mock_instance.login.assert_called_once_with("admin", "secret")

    @patch("routes.auth.TTEClient")
    def test_login_success_stores_session(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.session_id = "session-123"
        mock_instance.user_id = "user-456"
        mock_instance.login.return_value = {"id": "session-123"}
        MockClient.return_value = mock_instance

        with self.client.session_transaction() as sess:
            sess.clear()

        self.client.post("/login", data={
            "username": "admin",
            "password": "secret",
            "api_key": "user-api-key",
        })

        with self.client.session_transaction() as sess:
            self.assertEqual(sess["tte_session_id"], "session-123")
            self.assertEqual(sess["tte_username"], "admin")
            self.assertEqual(sess["tte_user_id"], "user-456")
            self.assertEqual(sess["tte_api_key"], "user-api-key")

    @patch("routes.auth.TTEClient")
    def test_login_failure_shows_error(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.login.side_effect = TTEAPIError("Invalid credentials")
        MockClient.return_value = mock_instance

        resp = self.client.post("/login", data={
            "username": "admin",
            "password": "wrong",
            "api_key": "user-api-key",
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

    @patch("routes.auth.TTEClient")
    def test_logout_clears_session(self, MockClient):
        mock_instance = MagicMock()
        MockClient.return_value = mock_instance

        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["tte_username"] = "admin"
            sess["tte_api_key"] = "user-api-key"

        resp = self.client.post("/logout")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.headers["Location"])

        with self.client.session_transaction() as sess:
            self.assertNotIn("tte_session_id", sess)
            self.assertNotIn("tte_username", sess)
            self.assertNotIn("tte_api_key", sess)

    @patch("routes.auth.TTEClient")
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
        self.assertIn(b"Convention", resp.data)


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

    @patch("routes.helpers.TTEClient")
    def test_search_returns_results(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.search_conventions.return_value = [
            {"id": "C0000001-0000-4000-A000-000000000001", "name": "GameFest 2026"},
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

    @patch("routes.helpers.TTEClient")
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

    @patch("routes.helpers.TTEClient")
    def test_select_success_stores_session(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.get_convention.return_value = {
            "id": "C0000001-0000-4000-A000-000000000001",
            "name": "GameFest 2026",
            "library": {"id": "10000001-0000-4000-A000-000000000001", "name": "GameFest Library"},
        }
        MockClient.return_value = mock_instance

        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"

        resp = self.client.post("/convention/select", data={"convention_id": "C0000001-0000-4000-A000-000000000001"})
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/convention/confirm", resp.headers["Location"])

        with self.client.session_transaction() as sess:
            self.assertEqual(sess["convention_id"], "C0000001-0000-4000-A000-000000000001")
            self.assertEqual(sess["library_id"], "10000001-0000-4000-A000-000000000001")

    @patch("routes.helpers.TTEClient")
    def test_confirm_shows_loading_overlay_and_warning(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.get_convention.return_value = {
            "id": "C0000001-0000-4000-A000-000000000001",
            "name": "GameFest 2026",
            "library": {"id": "10000001-0000-4000-A000-000000000001", "name": "GameFest Library"},
        }
        MockClient.return_value = mock_instance

        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"

        resp = self.client.post("/convention/select", data={"convention_id": "C0000001-0000-4000-A000-000000000001"}, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"loading-overlay", resp.data)
        self.assertIn(b"may take a minute or two", resp.data)

    def test_convention_confirm_get_requires_login(self):
        resp = self.client.get("/convention/confirm")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.headers["Location"])

    def test_convention_confirm_get_requires_convention(self):
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
        resp = self.client.get("/convention/confirm")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/convention", resp.headers["Location"])

    def test_convention_confirm_get_renders_page(self):
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["convention_name"] = "GameFest 2026"
            sess["library_name"] = "GameFest Library"
        resp = self.client.get("/convention/confirm")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"GameFest 2026", resp.data)
        self.assertIn(b"GameFest Library", resp.data)

    @patch("routes.helpers.TTEClient")
    def test_select_no_library_shows_error(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.get_convention.return_value = {
            "id": "C0000001-0000-4000-A000-000000000001",
            "name": "GameFest 2026",
        }
        MockClient.return_value = mock_instance

        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"

        resp = self.client.post("/convention/select", data={"convention_id": "C0000001-0000-4000-A000-000000000001"})
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/convention", resp.headers["Location"])

    @patch("routes.helpers.TTEClient")
    def test_select_api_error_shows_flash(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.get_convention.side_effect = TTEAPIError("Not found", 404)
        MockClient.return_value = mock_instance

        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"

        resp = self.client.post("/convention/select", data={"convention_id": "bad-id"})
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/convention", resp.headers["Location"])


class TestLibraryBrowseRoute(unittest.TestCase):

    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.app.config["TTE_API_KEY"] = "test-key"
        self.client = self.app.test_client()

    def test_browse_requires_login(self):
        resp = self.client.get("/library/browse")
        self.assertEqual(resp.status_code, 401)

    def test_browse_requires_user_id(self):
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"

        resp = self.client.get("/library/browse")
        self.assertEqual(resp.status_code, 400)

    @patch("routes.helpers.TTEClient")
    def test_browse_returns_libraries(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.get_user_libraries.return_value = [
            {"id": "10000001-0000-4000-A000-000000000001", "name": "My Library"},
            {"id": "lib-2", "name": "Second Library"},
        ]
        MockClient.return_value = mock_instance

        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["tte_user_id"] = "user-456"

        resp = self.client.get("/library/browse")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(len(data["results"]), 2)
        self.assertEqual(data["results"][0]["name"], "My Library")

    @patch("routes.helpers.TTEClient")
    def test_browse_empty_libraries(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.get_user_libraries.return_value = []
        MockClient.return_value = mock_instance

        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["tte_user_id"] = "user-456"

        resp = self.client.get("/library/browse")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(len(data["results"]), 0)

    @patch("routes.helpers.TTEClient")
    def test_browse_api_error(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.get_user_libraries.side_effect = TTEAPIError("Server error", 500)
        MockClient.return_value = mock_instance

        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["tte_user_id"] = "user-456"

        resp = self.client.get("/library/browse")
        self.assertEqual(resp.status_code, 502)

    @patch("routes.helpers.TTEClient")
    def test_browse_auth_error_clears_session(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.get_user_libraries.side_effect = TTEAPIError("Unauthorized", 401)
        MockClient.return_value = mock_instance

        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["tte_user_id"] = "user-456"

        resp = self.client.get("/library/browse")
        self.assertEqual(resp.status_code, 401)


class TestLibraryConfirmRoute(unittest.TestCase):

    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.app.config["TTE_API_KEY"] = "test-key"
        self.client = self.app.test_client()

    def test_library_confirm_requires_login(self):
        resp = self.client.post("/library/select", data={"library_id": "10000001-0000-4000-A000-000000000001"})
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.headers["Location"])

    def test_library_confirm_requires_id(self):
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"

        resp = self.client.post("/library/select", data={"library_id": ""})
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/convention", resp.headers["Location"])

    @patch("routes.helpers.TTEClient")
    def test_library_confirm_stores_session(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.get_library.return_value = {
            "id": "10000001-0000-4000-A000-000000000001",
            "name": "My P2W Library",
        }
        MockClient.return_value = mock_instance

        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"

        resp = self.client.post("/library/select", data={"library_id": "10000001-0000-4000-A000-000000000001"})
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/library/confirm", resp.headers["Location"])

        with self.client.session_transaction() as sess:
            self.assertEqual(sess["library_id"], "10000001-0000-4000-A000-000000000001")
            self.assertEqual(sess["library_name"], "My P2W Library")
            self.assertNotIn("convention_id", sess)

    @patch("routes.helpers.TTEClient")
    def test_library_confirm_clears_convention(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.get_library.return_value = {
            "id": "10000001-0000-4000-A000-000000000001",
            "name": "My Library",
        }
        MockClient.return_value = mock_instance

        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["convention_id"] = "conv-old"
            sess["convention_name"] = "Old Convention"

        self.client.post("/library/select", data={"library_id": "10000001-0000-4000-A000-000000000001"})

        with self.client.session_transaction() as sess:
            self.assertNotIn("convention_id", sess)
            self.assertNotIn("convention_name", sess)
            self.assertEqual(sess["library_id"], "10000001-0000-4000-A000-000000000001")

    @patch("routes.helpers.TTEClient")
    def test_library_confirm_shows_loading_overlay_and_warning(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.get_library.return_value = {
            "id": "10000001-0000-4000-A000-000000000001",
            "name": "My Library",
        }
        MockClient.return_value = mock_instance

        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"

        # POST redirects, then follow to GET /library/confirm
        resp = self.client.post("/library/select", data={"library_id": "10000001-0000-4000-A000-000000000001"}, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"loading-overlay", resp.data)
        self.assertIn(b"may take a minute or two", resp.data)

    def test_library_confirm_get_requires_login(self):
        resp = self.client.get("/library/confirm")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.headers["Location"])

    def test_library_confirm_get_requires_library(self):
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
        resp = self.client.get("/library/confirm")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/convention", resp.headers["Location"])

    def test_library_confirm_get_renders_page(self):
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["library_name"] = "Test Library"
        resp = self.client.get("/library/confirm")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Test Library", resp.data)

    @patch("routes.helpers.TTEClient")
    def test_library_confirm_api_error(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.get_library.side_effect = TTEAPIError("Not found", 404)
        MockClient.return_value = mock_instance

        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"

        resp = self.client.post("/library/select", data={"library_id": "bad-id"})
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/convention", resp.headers["Location"])

    @patch("routes.helpers.TTEClient")
    def test_games_page_works_in_library_only_mode(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.get_library_games.return_value = [
            {"id": "A0000001-0000-4000-A000-000000000001", "name": "Catan"},
        ]
        mock_instance.get_library_playtowins.return_value = [
            {"id": "e1", "badge_id": "B1", "librarygame_id": "A0000001-0000-4000-A000-000000000001"},
        ]
        MockClient.return_value = mock_instance

        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["library_id"] = "10000001-0000-4000-A000-000000000001"
            sess["library_name"] = "My Library"

        resp = self.client.get("/games")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Catan", resp.data)
        self.assertIn(b"My Library", resp.data)
        mock_instance.get_library_playtowins.assert_called_once_with("10000001-0000-4000-A000-000000000001")

    def test_drawing_works_in_library_only_mode(self):
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["library_id"] = "10000001-0000-4000-A000-000000000001"
            sess["library_name"] = "My Library"
            sess["cached_games"] = [{"id": "A0000001-0000-4000-A000-000000000001", "name": "Catan"}]
            sess["cached_entries"] = [
                {"id": "e1", "badge_id": "B1", "librarygame_id": "A0000001-0000-4000-A000-000000000001", "name": "Alice"},
            ]

        resp = self.client.post("/drawing", follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Drawing Results", resp.data)
        self.assertIn(b"My Library", resp.data)

    def test_convention_select_shows_library_tab(self):
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"

        resp = self.client.get("/convention")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Library Only", resp.data)
        self.assertIn(b"Browse My Libraries", resp.data)


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

    @patch("routes.helpers.TTEClient")
    def test_games_loads_and_displays(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.get_library_games.return_value = [
            {"id": "A0000001-0000-4000-A000-000000000001", "name": "Catan"},
            {"id": "A0000002-0000-4000-A000-000000000002", "name": "Wingspan"},
        ]
        mock_instance.get_convention_playtowins.return_value = [
            {"badge_id": "B1", "librarygame_id": "A0000001-0000-4000-A000-000000000001", "id": "e1"},
            {"badge_id": "B2", "librarygame_id": "A0000001-0000-4000-A000-000000000001", "id": "e2"},
            {"badge_id": "B1", "librarygame_id": "A0000001-0000-4000-A000-000000000001", "id": "e3"},  # dup
            {"badge_id": None, "librarygame_id": "A0000002-0000-4000-A000-000000000002", "id": "e4"},  # no badge
            {"badge_id": "B3", "librarygame_id": "A0000002-0000-4000-A000-000000000002", "id": "e5"},
        ]
        MockClient.return_value = mock_instance

        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["library_id"] = "10000001-0000-4000-A000-000000000001"
            sess["convention_id"] = "C0000001-0000-4000-A000-000000000001"
            sess["convention_name"] = "GameFest"

        resp = self.client.get("/games")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Catan", resp.data)
        self.assertIn(b"Wingspan", resp.data)
        # 3 unique entries after de-dup and badge filter
        self.assertIn(b"3", resp.data)

    @patch("routes.helpers.TTEClient")
    def test_games_shows_no_entries_badge(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.get_library_games.return_value = [
            {"id": "A0000001-0000-4000-A000-000000000001", "name": "Catan"},
        ]
        mock_instance.get_convention_playtowins.return_value = []
        MockClient.return_value = mock_instance

        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["library_id"] = "10000001-0000-4000-A000-000000000001"
            sess["convention_id"] = "C0000001-0000-4000-A000-000000000001"
            sess["convention_name"] = "GameFest"

        resp = self.client.get("/games")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"No entries", resp.data)

    @patch("routes.helpers.TTEClient")
    def test_games_api_error_redirects(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.get_library_games.side_effect = TTEAPIError("API error")
        MockClient.return_value = mock_instance

        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["library_id"] = "10000001-0000-4000-A000-000000000001"
            sess["convention_id"] = "C0000001-0000-4000-A000-000000000001"

        resp = self.client.get("/games")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/convention", resp.headers["Location"])

    @patch("routes.helpers.TTEClient")
    def test_games_uses_library_when_no_convention(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.get_library_games.return_value = [
            {"id": "A0000001-0000-4000-A000-000000000001", "name": "TestGame"},
        ]
        mock_instance.get_library_playtowins.return_value = []
        MockClient.return_value = mock_instance

        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["library_id"] = "10000001-0000-4000-A000-000000000001"
            sess["convention_name"] = "Test"
            # no convention_id

        resp = self.client.get("/games")
        self.assertEqual(resp.status_code, 200)
        mock_instance.get_library_playtowins.assert_called_once_with("10000001-0000-4000-A000-000000000001")


class TestPremiumGamesRoute(unittest.TestCase):

    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.app.config["TTE_API_KEY"] = "test-key"
        self.client = self.app.test_client()

    def test_set_premium_requires_login(self):
        resp = self.client.post("/games/premium",
                                json={"premium_games": ["A0000001-0000-4000-A000-000000000001"]})
        self.assertEqual(resp.status_code, 401)

    def test_set_premium_stores_in_session(self):
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"

        resp = self.client.post("/games/premium",
                                json={"premium_games": ["A0000001-0000-4000-A000-000000000001", "A0000002-0000-4000-A000-000000000002"]})
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["count"], 2)

        with self.client.session_transaction() as sess:
            self.assertEqual(sess["premium_games"], ["A0000001-0000-4000-A000-000000000001", "A0000002-0000-4000-A000-000000000002"])

    def test_set_premium_empty_list(self):
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["premium_games"] = ["A0000001-0000-4000-A000-000000000001"]

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

    @patch("routes.helpers.TTEClient")
    def test_games_page_shows_premium_styling(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.get_library_games.return_value = [
            {"id": "A0000001-0000-4000-A000-000000000001", "name": "Catan"},
            {"id": "A0000002-0000-4000-A000-000000000002", "name": "Wingspan"},
        ]
        mock_instance.get_convention_playtowins.return_value = [
            {"badge_id": "B1", "librarygame_id": "A0000001-0000-4000-A000-000000000001", "id": "e1"},
        ]
        MockClient.return_value = mock_instance

        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["library_id"] = "10000001-0000-4000-A000-000000000001"
            sess["convention_id"] = "C0000001-0000-4000-A000-000000000001"
            sess["convention_name"] = "GameFest"
            sess["premium_games"] = ["A0000001-0000-4000-A000-000000000001"]

        resp = self.client.get("/games")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Premium", resp.data)
        self.assertIn(b"checked", resp.data)

    @patch("routes.helpers.TTEClient")
    def test_games_page_no_premium(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.get_library_games.return_value = [
            {"id": "A0000001-0000-4000-A000-000000000001", "name": "Catan"},
        ]
        mock_instance.get_convention_playtowins.return_value = []
        MockClient.return_value = mock_instance

        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["library_id"] = "10000001-0000-4000-A000-000000000001"
            sess["convention_id"] = "C0000001-0000-4000-A000-000000000001"
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

    def test_drawing_results_requires_auth(self):
        resp = self.client.get("/drawing/results")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.headers["Location"])

    def test_drawing_results_requires_drawing_state(self):
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
        resp = self.client.get("/drawing/results")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/games", resp.headers["Location"])

    def test_drawing_post_redirects_to_results(self):
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["library_id"] = "10000001-0000-4000-A000-000000000001"
            sess["convention_id"] = "C0000001-0000-4000-A000-000000000001"
            sess["convention_name"] = "Test Con"
            sess["premium_games"] = []
            sess["cached_games"] = [{"id": "A0000001-0000-4000-A000-000000000001", "name": "Catan"}]
            sess["cached_entries"] = [
                {"id": "e1", "badge_id": "B1", "librarygame_id": "A0000001-0000-4000-A000-000000000001",
                 "name": "Alice"},
            ]
        resp = self.client.post("/drawing")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/drawing/results", resp.headers["Location"])

    def test_drawing_requires_convention(self):
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"

        resp = self.client.post("/drawing")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/convention", resp.headers["Location"])

    def test_drawing_runs_and_shows_results(self):
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["library_id"] = "10000001-0000-4000-A000-000000000001"
            sess["convention_id"] = "C0000001-0000-4000-A000-000000000001"
            sess["convention_name"] = "GameFest"
            sess["cached_games"] = [
                {"id": "A0000001-0000-4000-A000-000000000001", "name": "Catan"},
                {"id": "A0000002-0000-4000-A000-000000000002", "name": "Ticket to Ride"},
            ]
            sess["cached_entries"] = [
                {"id": "e1", "badge_id": "B1", "librarygame_id": "A0000001-0000-4000-A000-000000000001", "name": "Alice"},
                {"id": "e2", "badge_id": "B2", "librarygame_id": "A0000002-0000-4000-A000-000000000002", "name": "Bob"},
            ]

        resp = self.client.post("/drawing", follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Drawing Results", resp.data)
        self.assertIn(b"Catan", resp.data)
        self.assertIn(b"Ticket to Ride", resp.data)

    def test_drawing_with_conflict_shows_panel(self):
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["library_id"] = "10000001-0000-4000-A000-000000000001"
            sess["convention_id"] = "C0000001-0000-4000-A000-000000000001"
            sess["convention_name"] = "GameFest"
            sess["cached_games"] = [
                {"id": "A0000001-0000-4000-A000-000000000001", "name": "Catan"},
                {"id": "A0000002-0000-4000-A000-000000000002", "name": "Ticket to Ride"},
            ]
            # B1 entered both games -> potential conflict
            sess["cached_entries"] = [
                {"id": "e1", "badge_id": "B1", "librarygame_id": "A0000001-0000-4000-A000-000000000001", "name": "Alice"},
                {"id": "e2", "badge_id": "B1", "librarygame_id": "A0000002-0000-4000-A000-000000000002", "name": "Alice"},
            ]

        resp = self.client.post("/drawing", follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        # B1 must win both since they're the only entrant — conflict
        self.assertIn(b"Multi-Win Conflicts", resp.data)
        # Verify the person's name is shown, not just badge
        self.assertIn(b"Alice", resp.data)
        # Verify conflict badge on the results table
        self.assertIn(b'class="conflict-badge"', resp.data)

    def test_drawing_conflict_shows_rerun_button(self):
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["library_id"] = "10000001-0000-4000-A000-000000000001"
            sess["convention_id"] = "C0000001-0000-4000-A000-000000000001"
            sess["convention_name"] = "GameFest"
            sess["cached_games"] = [{"id": "A0000001-0000-4000-A000-000000000001", "name": "Catan"}]
            sess["cached_entries"] = [
                {"id": "e1", "badge_id": "B1", "librarygame_id": "A0000001-0000-4000-A000-000000000001", "name": "Alice"},
            ]

        resp = self.client.post("/drawing", follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Re-run Drawing", resp.data)

    def test_drawing_separates_premium_conflicts(self):
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["library_id"] = "10000001-0000-4000-A000-000000000001"
            sess["convention_id"] = "C0000001-0000-4000-A000-000000000001"
            sess["convention_name"] = "GameFest"
            sess["premium_games"] = ["A0000001-0000-4000-A000-000000000001", "A0000002-0000-4000-A000-000000000002"]
            sess["cached_games"] = [
                {"id": "A0000001-0000-4000-A000-000000000001", "name": "Catan"},
                {"id": "A0000002-0000-4000-A000-000000000002", "name": "Ticket to Ride"},
                {"id": "A0000003-0000-4000-A000-000000000003", "name": "Wingspan"},
                {"id": "A0000004-0000-4000-A000-000000000004", "name": "Azul"},
            ]
            # B1 wins G1+G2 (both premium), B2 wins G3+G4 (not premium)
            sess["cached_entries"] = [
                {"id": "e1", "badge_id": "B1", "librarygame_id": "A0000001-0000-4000-A000-000000000001", "name": "Alice"},
                {"id": "e2", "badge_id": "B1", "librarygame_id": "A0000002-0000-4000-A000-000000000002", "name": "Alice"},
                {"id": "e3", "badge_id": "B2", "librarygame_id": "A0000003-0000-4000-A000-000000000003", "name": "Bob"},
                {"id": "e4", "badge_id": "B2", "librarygame_id": "A0000004-0000-4000-A000-000000000004", "name": "Bob"},
            ]

        resp = self.client.post("/drawing", follow_redirects=True)
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
                "game": {"id": "A0000001-0000-4000-A000-000000000001", "name": "Catan"},
                "shuffled": [
                    {"badge_id": "B1", "librarygame_id": "A0000001-0000-4000-A000-000000000001", "id": "e1", "name": "Alice"},
                    {"badge_id": "B2", "librarygame_id": "A0000001-0000-4000-A000-000000000001", "id": "e3", "name": "Bob"},
                ],
                "winner_index": 0,
            },
            {
                "game": {"id": "A0000002-0000-4000-A000-000000000002", "name": "Ticket to Ride"},
                "shuffled": [
                    {"badge_id": "B1", "librarygame_id": "A0000002-0000-4000-A000-000000000002", "id": "e2", "name": "Alice"},
                    {"badge_id": "B3", "librarygame_id": "A0000002-0000-4000-A000-000000000002", "id": "e4", "name": "Carol"},
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
                                    {"badge_id": "B1", "keep_game_id": "A0000001-0000-4000-A000-000000000001"}
                                ]},
                                content_type="application/json")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["ok"])

        # B1 keeps G1, G2 advanced to B3
        winners = {r["game_id"]: r["winner_badge"] for r in data["results"]}
        self.assertEqual(winners["A0000001-0000-4000-A000-000000000001"], "B1")
        self.assertEqual(winners["A0000002-0000-4000-A000-000000000002"], "B3")
        # Verify no remaining conflicts
        self.assertEqual(data["conflicts"], [])

    def test_resolve_cascading_conflict_returns_new_conflicts(self):
        # B1 wins G1+G2, B2 also entered G2 and G3.
        # Resolving B1 -> keep G1 cascades G2 to B2, who now wins G2+G3.
        drawing_state = [
            {
                "game": {"id": "A0000001-0000-4000-A000-000000000001", "name": "Catan"},
                "shuffled": [
                    {"badge_id": "B1", "librarygame_id": "A0000001-0000-4000-A000-000000000001", "id": "e1", "name": "Alice"},
                ],
                "winner_index": 0,
            },
            {
                "game": {"id": "A0000002-0000-4000-A000-000000000002", "name": "Ticket to Ride"},
                "shuffled": [
                    {"badge_id": "B1", "librarygame_id": "A0000002-0000-4000-A000-000000000002", "id": "e2", "name": "Alice"},
                    {"badge_id": "B2", "librarygame_id": "A0000002-0000-4000-A000-000000000002", "id": "e3", "name": "Bob"},
                ],
                "winner_index": 0,
            },
            {
                "game": {"id": "A0000003-0000-4000-A000-000000000003", "name": "Wingspan"},
                "shuffled": [
                    {"badge_id": "B2", "librarygame_id": "A0000003-0000-4000-A000-000000000003", "id": "e4", "name": "Bob"},
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
                                    {"badge_id": "B1", "keep_game_id": "A0000001-0000-4000-A000-000000000001"}
                                ]},
                                content_type="application/json")
        data = resp.get_json()
        self.assertTrue(data["ok"])
        # B2 now has a cascading conflict
        self.assertEqual(len(data["conflicts"]), 1)
        self.assertEqual(data["conflicts"][0]["badge_id"], "B2")
        self.assertEqual(data["conflicts"][0]["winner_name"], "Bob")

    def test_drawing_has_view_tabs(self):
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["library_id"] = "10000001-0000-4000-A000-000000000001"
            sess["convention_id"] = "C0000001-0000-4000-A000-000000000001"
            sess["convention_name"] = "GameFest"
            sess["cached_games"] = [{"id": "A0000001-0000-4000-A000-000000000001", "name": "Catan"}]
            sess["cached_entries"] = [
                {"id": "e1", "badge_id": "B1", "librarygame_id": "A0000001-0000-4000-A000-000000000001", "name": "Alice"},
            ]

        resp = self.client.post("/drawing", follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"By Game", resp.data)
        self.assertIn(b"By Winner", resp.data)
        self.assertIn(b'id="tab-by-game"', resp.data)
        self.assertIn(b'id="tab-by-winner"', resp.data)
        self.assertIn(b'id="panel-by-game"', resp.data)
        self.assertIn(b'id="panel-by-winner"', resp.data)

    def test_by_game_view_shows_all_games(self):
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["library_id"] = "10000001-0000-4000-A000-000000000001"
            sess["convention_id"] = "C0000001-0000-4000-A000-000000000001"
            sess["convention_name"] = "GameFest"
            sess["cached_games"] = [
                {"id": "A0000001-0000-4000-A000-000000000001", "name": "Catan"},
                {"id": "A0000002-0000-4000-A000-000000000002", "name": "Ticket to Ride"},
            ]
            sess["cached_entries"] = [
                {"id": "e1", "badge_id": "B1", "librarygame_id": "A0000001-0000-4000-A000-000000000001", "name": "Alice"},
            ]

        resp = self.client.post("/drawing", follow_redirects=True)
        html = resp.data.decode()
        # By Game panel shows both games
        self.assertIn("Catan", html)
        self.assertIn("Ticket to Ride", html)
        # Game with no entries shows "No entries"
        self.assertIn("No entries", html)

    def test_by_winner_view_shows_winners_only(self):
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["library_id"] = "10000001-0000-4000-A000-000000000001"
            sess["convention_id"] = "C0000001-0000-4000-A000-000000000001"
            sess["convention_name"] = "GameFest"
            sess["cached_games"] = [
                {"id": "A0000001-0000-4000-A000-000000000001", "name": "Catan"},
                {"id": "A0000002-0000-4000-A000-000000000002", "name": "Ticket to Ride"},
            ]
            sess["cached_entries"] = [
                {"id": "e1", "badge_id": "B1", "librarygame_id": "A0000001-0000-4000-A000-000000000001", "name": "Alice"},
            ]

        resp = self.client.post("/drawing", follow_redirects=True)
        html = resp.data.decode()
        # The By Winner panel should have Alice once in the awaiting table
        winner_panel_start = html.index('id="panel-by-winner"')
        winner_panel = html[winner_panel_start:]
        self.assertIn("Alice", winner_panel)
        self.assertIn("Catan", winner_panel)
        # Ticket to Ride has no entries — should be in "No Winner" section, not awaiting
        awaiting_start = winner_panel.index('id="winner-awaiting-table"')
        awaiting_end = winner_panel.index('</table>', awaiting_start)
        awaiting_table = winner_panel[awaiting_start:awaiting_end]
        self.assertNotIn("Ticket to Ride", awaiting_table)

    def test_by_winner_view_highlights_premium(self):
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["library_id"] = "10000001-0000-4000-A000-000000000001"
            sess["convention_id"] = "C0000001-0000-4000-A000-000000000001"
            sess["convention_name"] = "GameFest"
            sess["premium_games"] = ["A0000001-0000-4000-A000-000000000001"]
            sess["cached_games"] = [
                {"id": "A0000001-0000-4000-A000-000000000001", "name": "Catan"},
                {"id": "A0000002-0000-4000-A000-000000000002", "name": "Ticket to Ride"},
            ]
            sess["cached_entries"] = [
                {"id": "e1", "badge_id": "B1", "librarygame_id": "A0000001-0000-4000-A000-000000000001", "name": "Alice"},
                {"id": "e2", "badge_id": "B2", "librarygame_id": "A0000002-0000-4000-A000-000000000002", "name": "Bob"},
            ]

        resp = self.client.post("/drawing", follow_redirects=True)
        html = resp.data.decode()
        # By Winner table should show Premium label for Catan
        winner_panel_start = html.index('id="panel-by-winner"')
        winner_panel = html[winner_panel_start:]
        self.assertIn("Premium", winner_panel)

    def test_drawing_shows_pickup_summary(self):
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["library_id"] = "10000001-0000-4000-A000-000000000001"
            sess["convention_id"] = "C0000001-0000-4000-A000-000000000001"
            sess["convention_name"] = "GameFest"
            sess["cached_games"] = [{"id": "A0000001-0000-4000-A000-000000000001", "name": "Catan"}]
            sess["cached_entries"] = [
                {"id": "e1", "badge_id": "B1", "librarygame_id": "A0000001-0000-4000-A000-000000000001", "name": "Alice"},
            ]

        resp = self.client.post("/drawing", follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"picked up", resp.data)
        self.assertIn(b'id="pickup-count"', resp.data)

    def test_drawing_shows_pickup_buttons(self):
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["library_id"] = "10000001-0000-4000-A000-000000000001"
            sess["convention_id"] = "C0000001-0000-4000-A000-000000000001"
            sess["convention_name"] = "GameFest"
            sess["cached_games"] = [
                {"id": "A0000001-0000-4000-A000-000000000001", "name": "Catan"},
                {"id": "A0000002-0000-4000-A000-000000000002", "name": "Ticket to Ride"},
            ]
            sess["cached_entries"] = [
                {"id": "e1", "badge_id": "B1", "librarygame_id": "A0000001-0000-4000-A000-000000000001", "name": "Alice"},
            ]

        resp = self.client.post("/drawing", follow_redirects=True)
        html = resp.data.decode()
        # Game with winner should have pickup button
        self.assertIn("Mark Picked Up", html)

    def test_pickup_requires_auth(self):
        resp = self.client.post("/drawing/pickup",
                                json={"game_id": "A0000001-0000-4000-A000-000000000001"},
                                content_type="application/json")
        self.assertEqual(resp.status_code, 401)

    def test_pickup_requires_drawing_state(self):
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"

        resp = self.client.post("/drawing/pickup",
                                json={"game_id": "A0000001-0000-4000-A000-000000000001"},
                                content_type="application/json")
        self.assertEqual(resp.status_code, 400)

    def test_pickup_requires_game_id(self):
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["drawing_state"] = [{"game": {"id": "A0000001-0000-4000-A000-000000000001"}, "shuffled": [], "winner_index": 0}]

        resp = self.client.post("/drawing/pickup",
                                json={},
                                content_type="application/json")
        self.assertEqual(resp.status_code, 400)

    def test_pickup_toggle_marks_picked_up(self):
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["drawing_state"] = [{"game": {"id": "A0000001-0000-4000-A000-000000000001"}, "shuffled": [], "winner_index": 0}]
            sess["picked_up"] = []

        resp = self.client.post("/drawing/pickup",
                                json={"game_id": "A0000001-0000-4000-A000-000000000001"},
                                content_type="application/json")
        data = resp.get_json()
        self.assertTrue(data["ok"])
        self.assertTrue(data["is_picked_up"])
        self.assertEqual(data["picked_up_count"], 1)

        # Verify session was updated
        with self.client.session_transaction() as sess:
            self.assertIn("A0000001-0000-4000-A000-000000000001", sess["picked_up"])

    def test_pickup_toggle_unmarks_picked_up(self):
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["drawing_state"] = [{"game": {"id": "A0000001-0000-4000-A000-000000000001"}, "shuffled": [], "winner_index": 0}]
            sess["picked_up"] = ["A0000001-0000-4000-A000-000000000001"]

        resp = self.client.post("/drawing/pickup",
                                json={"game_id": "A0000001-0000-4000-A000-000000000001"},
                                content_type="application/json")
        data = resp.get_json()
        self.assertTrue(data["ok"])
        self.assertFalse(data["is_picked_up"])
        self.assertEqual(data["picked_up_count"], 0)

        with self.client.session_transaction() as sess:
            self.assertNotIn("A0000001-0000-4000-A000-000000000001", sess["picked_up"])

    def test_rerun_drawing_clears_pickup(self):
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["library_id"] = "10000001-0000-4000-A000-000000000001"
            sess["convention_id"] = "C0000001-0000-4000-A000-000000000001"
            sess["convention_name"] = "GameFest"
            sess["picked_up"] = ["A0000001-0000-4000-A000-000000000001"]
            sess["cached_games"] = [{"id": "A0000001-0000-4000-A000-000000000001", "name": "Catan"}]
            sess["cached_entries"] = [
                {"id": "e1", "badge_id": "B1", "librarygame_id": "A0000001-0000-4000-A000-000000000001", "name": "Alice"},
            ]

        self.client.post("/drawing")

        with self.client.session_transaction() as sess:
            self.assertEqual(sess["picked_up"], [])

    def test_drawing_shows_redraw_button(self):
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["library_id"] = "10000001-0000-4000-A000-000000000001"
            sess["convention_id"] = "C0000001-0000-4000-A000-000000000001"
            sess["convention_name"] = "GameFest"
            sess["cached_games"] = [{"id": "A0000001-0000-4000-A000-000000000001", "name": "Catan"}]
            sess["cached_entries"] = [
                {"id": "e1", "badge_id": "B1", "librarygame_id": "A0000001-0000-4000-A000-000000000001", "name": "Alice"},
            ]

        resp = self.client.post("/drawing", follow_redirects=True)
        self.assertIn(b"Redraw All Unclaimed", resp.data)

    def test_drawing_results_has_search_filter(self):
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["library_id"] = "10000001-0000-4000-A000-000000000001"
            sess["convention_id"] = "C0000001-0000-4000-A000-000000000001"
            sess["convention_name"] = "GameFest"
            sess["cached_games"] = [{"id": "A0000001-0000-4000-A000-000000000001", "name": "Catan"}]
            sess["cached_entries"] = [
                {"id": "e1", "badge_id": "B1", "librarygame_id": "A0000001-0000-4000-A000-000000000001", "name": "Alice"},
            ]

        resp = self.client.post("/drawing", follow_redirects=True)
        self.assertIn(b'id="search-input"', resp.data)
        self.assertIn(b'id="search-count"', resp.data)
        self.assertIn(b"Filter by game name", resp.data)


class TestDismissConflictGameRoute(unittest.TestCase):

    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.app.config["TTE_API_KEY"] = "test-key"
        self.client = self.app.test_client()

    def _multi_win_state(self):
        """B1 wins G1 + G2 (conflict). G1 also has B3, G2 also has B2."""
        return [
            {
                "game": {"id": "A0000001-0000-4000-A000-000000000001", "name": "Catan"},
                "shuffled": [
                    {"badge_id": "B1", "id": "e1", "name": "Alice"},
                    {"badge_id": "B3", "id": "e3", "name": "Carol"},
                ],
                "winner_index": 0,
            },
            {
                "game": {"id": "A0000002-0000-4000-A000-000000000002", "name": "Ticket to Ride"},
                "shuffled": [
                    {"badge_id": "B1", "id": "e2", "name": "Alice"},
                    {"badge_id": "B2", "id": "e4", "name": "Bob"},
                ],
                "winner_index": 0,
            },
        ]

    def test_dismiss_requires_auth(self):
        resp = self.client.post("/drawing/dismiss-game",
                                json={"badge_id": "B1", "game_id": "A0000001-0000-4000-A000-000000000001"},
                                content_type="application/json")
        self.assertEqual(resp.status_code, 401)

    def test_dismiss_requires_drawing_state(self):
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
        resp = self.client.post("/drawing/dismiss-game",
                                json={"badge_id": "B1", "game_id": "A0000001-0000-4000-A000-000000000001"},
                                content_type="application/json")
        self.assertEqual(resp.status_code, 400)

    def test_dismiss_requires_badge_and_game(self):
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["drawing_state"] = self._multi_win_state()
        resp = self.client.post("/drawing/dismiss-game",
                                json={"badge_id": "B1"},
                                content_type="application/json")
        self.assertEqual(resp.status_code, 400)

    def test_dismiss_advances_winner_on_dismissed_game(self):
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["drawing_state"] = self._multi_win_state()
            sess["drawing_conflicts"] = [{
                "badge_id": "B1", "winner_name": "Alice",
                "game_ids": ["A0000001-0000-4000-A000-000000000001", "A0000002-0000-4000-A000-000000000002"],
                "game_names": {"A0000001-0000-4000-A000-000000000001": "Catan", "A0000002-0000-4000-A000-000000000002": "Ticket to Ride"},
                "is_premium_conflict": False,
            }]
            sess["premium_games"] = []

        resp = self.client.post("/drawing/dismiss-game",
                                json={"badge_id": "B1", "game_id": "A0000001-0000-4000-A000-000000000001"},
                                content_type="application/json")
        data = resp.get_json()
        self.assertTrue(data["ok"])

        # G1 advanced to Carol, B1 still wins G2
        winners = {r["game_id"]: r["winner_badge"] for r in data["results"]}
        self.assertEqual(winners["A0000001-0000-4000-A000-000000000001"], "B3")  # Carol
        self.assertEqual(winners["A0000002-0000-4000-A000-000000000002"], "B1")  # Alice keeps G2

        # Conflict auto-resolved (only 1 game left for B1)
        self.assertEqual(data["conflicts"], [])

    def test_dismiss_keeps_conflict_with_three_games(self):
        """If person wins 3 games and dismisses 1, still 2 remain -> still a conflict."""
        state = self._multi_win_state()
        state.append({
            "game": {"id": "A0000003-0000-4000-A000-000000000003", "name": "Wingspan"},
            "shuffled": [
                {"badge_id": "B1", "id": "e5", "name": "Alice"},
                {"badge_id": "B4", "id": "e6", "name": "Dave"},
            ],
            "winner_index": 0,
        })
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["drawing_state"] = state
            sess["drawing_conflicts"] = [{
                "badge_id": "B1", "winner_name": "Alice",
                "game_ids": ["A0000001-0000-4000-A000-000000000001", "A0000002-0000-4000-A000-000000000002", "A0000003-0000-4000-A000-000000000003"],
                "game_names": {"A0000001-0000-4000-A000-000000000001": "Catan", "A0000002-0000-4000-A000-000000000002": "Ticket to Ride", "A0000003-0000-4000-A000-000000000003": "Wingspan"},
                "is_premium_conflict": False,
            }]
            sess["premium_games"] = []

        resp = self.client.post("/drawing/dismiss-game",
                                json={"badge_id": "B1", "game_id": "A0000001-0000-4000-A000-000000000001"},
                                content_type="application/json")
        data = resp.get_json()
        self.assertTrue(data["ok"])

        # Still a conflict for B1 with G2 + G3
        self.assertEqual(len(data["conflicts"]), 1)
        self.assertEqual(set(data["conflicts"][0]["game_ids"]), {"A0000002-0000-4000-A000-000000000002", "A0000003-0000-4000-A000-000000000003"})

    def test_dismiss_solo_entrant_marks_game(self):
        """Dismissing a game where the winner was the only entrant -> solo_dismissed."""
        state = [
            {
                "game": {"id": "A0000001-0000-4000-A000-000000000001", "name": "Catan"},
                "shuffled": [
                    {"badge_id": "B1", "id": "e1", "name": "Alice"},
                ],
                "winner_index": 0,
            },
            {
                "game": {"id": "A0000002-0000-4000-A000-000000000002", "name": "Ticket to Ride"},
                "shuffled": [
                    {"badge_id": "B1", "id": "e2", "name": "Alice"},
                    {"badge_id": "B2", "id": "e3", "name": "Bob"},
                ],
                "winner_index": 0,
            },
        ]
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["drawing_state"] = state
            sess["drawing_conflicts"] = [{
                "badge_id": "B1", "winner_name": "Alice",
                "game_ids": ["A0000001-0000-4000-A000-000000000001", "A0000002-0000-4000-A000-000000000002"],
                "game_names": {"A0000001-0000-4000-A000-000000000001": "Catan", "A0000002-0000-4000-A000-000000000002": "Ticket to Ride"},
                "is_premium_conflict": False,
            }]
            sess["premium_games"] = []

        resp = self.client.post("/drawing/dismiss-game",
                                json={"badge_id": "B1", "game_id": "A0000001-0000-4000-A000-000000000001"},
                                content_type="application/json")
        data = resp.get_json()
        self.assertTrue(data["ok"])
        self.assertTrue(data["was_solo_entrant"])
        self.assertTrue(data["was_exhausted"])
        self.assertEqual(data["dismissed_game_id"], "A0000001-0000-4000-A000-000000000001")

        # Session should track the dismissal
        with self.client.session_transaction() as sess:
            self.assertIn("A0000001-0000-4000-A000-000000000001", sess["solo_dismissed_games"])

        # The results should show the game as solo-dismissed
        solo = [r for r in data["results"] if r["game_id"] == "A0000001-0000-4000-A000-000000000001"]
        self.assertTrue(solo[0]["is_solo_dismissed"])
        self.assertFalse(solo[0]["has_winner"])

    def test_dismiss_non_solo_not_exhausted(self):
        """Dismissing a game with a next candidate should NOT mark as exhausted."""
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["drawing_state"] = self._multi_win_state()
            sess["drawing_conflicts"] = [{
                "badge_id": "B1", "winner_name": "Alice",
                "game_ids": ["A0000001-0000-4000-A000-000000000001", "A0000002-0000-4000-A000-000000000002"],
                "game_names": {"A0000001-0000-4000-A000-000000000001": "Catan", "A0000002-0000-4000-A000-000000000002": "Ticket to Ride"},
                "is_premium_conflict": False,
            }]
            sess["premium_games"] = []

        resp = self.client.post("/drawing/dismiss-game",
                                json={"badge_id": "B1", "game_id": "A0000001-0000-4000-A000-000000000001"},
                                content_type="application/json")
        data = resp.get_json()
        self.assertFalse(data["was_exhausted"])
        self.assertFalse(data["was_solo_entrant"])

        with self.client.session_transaction() as sess:
            self.assertEqual(sess.get("solo_dismissed_games", []), [])

    def test_dismiss_two_entrant_both_gone(self):
        """Dismiss sole-remaining candidate from a 2-entry game -> exhausted."""
        state = [
            {
                "game": {"id": "A0000001-0000-4000-A000-000000000001", "name": "Catan"},
                "shuffled": [
                    {"badge_id": "B1", "id": "e1", "name": "Alice"},
                    {"badge_id": "B2", "id": "e2", "name": "Bob"},
                ],
                "winner_index": 1,  # B2 is current winner (B1 already skipped)
            },
            {
                "game": {"id": "A0000002-0000-4000-A000-000000000002", "name": "Ticket to Ride"},
                "shuffled": [
                    {"badge_id": "B2", "id": "e3", "name": "Bob"},
                    {"badge_id": "B3", "id": "e4", "name": "Carol"},
                ],
                "winner_index": 0,
            },
        ]
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["drawing_state"] = state
            sess["drawing_conflicts"] = [{
                "badge_id": "B2", "winner_name": "Bob",
                "game_ids": ["A0000001-0000-4000-A000-000000000001", "A0000002-0000-4000-A000-000000000002"],
                "game_names": {"A0000001-0000-4000-A000-000000000001": "Catan", "A0000002-0000-4000-A000-000000000002": "Ticket to Ride"},
                "is_premium_conflict": False,
            }]
            sess["premium_games"] = []

        # Dismiss B2 from G1 -> advance tries index 2, no more candidates
        resp = self.client.post("/drawing/dismiss-game",
                                json={"badge_id": "B2", "game_id": "A0000001-0000-4000-A000-000000000001"},
                                content_type="application/json")
        data = resp.get_json()
        self.assertTrue(data["ok"])
        self.assertTrue(data["was_exhausted"])
        self.assertFalse(data["was_solo_entrant"])  # 2 entrants, not solo

        with self.client.session_transaction() as sess:
            self.assertIn("A0000001-0000-4000-A000-000000000001", sess["solo_dismissed_games"])

        # The results should show the game as no-winner (redraw eligible)
        g1 = [r for r in data["results"] if r["game_id"] == "A0000001-0000-4000-A000-000000000001"]
        self.assertTrue(g1[0]["is_solo_dismissed"])
        self.assertFalse(g1[0]["has_winner"])

    def test_resolve_tracks_exhausted_games(self):
        """Resolve route tracks games exhausted after apply_resolution."""
        # B1 wins G1 and G2. G1 has only B1, G2 has B1+B2.
        # User keeps G2 for B1 -> G1 is relinquished and exhausted.
        state = [
            {
                "game": {"id": "A0000001-0000-4000-A000-000000000001", "name": "Catan"},
                "shuffled": [
                    {"badge_id": "B1", "id": "e1", "name": "Alice"},
                ],
                "winner_index": 0,
            },
            {
                "game": {"id": "A0000002-0000-4000-A000-000000000002", "name": "Ticket to Ride"},
                "shuffled": [
                    {"badge_id": "B1", "id": "e2", "name": "Alice"},
                    {"badge_id": "B2", "id": "e3", "name": "Bob"},
                ],
                "winner_index": 0,
            },
        ]
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["drawing_state"] = state
            sess["drawing_conflicts"] = [{
                "badge_id": "B1", "winner_name": "Alice",
                "game_ids": ["A0000001-0000-4000-A000-000000000001", "A0000002-0000-4000-A000-000000000002"],
                "game_names": {"A0000001-0000-4000-A000-000000000001": "Catan", "A0000002-0000-4000-A000-000000000002": "Ticket to Ride"},
                "is_premium_conflict": False,
            }]
            sess["premium_games"] = []

        resp = self.client.post("/drawing/resolve",
                                json={"resolutions": [{"badge_id": "B1", "keep_game_id": "A0000002-0000-4000-A000-000000000002"}]},
                                content_type="application/json")
        data = resp.get_json()
        self.assertTrue(data["ok"])

        # G1 had only B1, who kept G2; G1 is now exhausted
        with self.client.session_transaction() as sess:
            self.assertIn("A0000001-0000-4000-A000-000000000001", sess.get("solo_dismissed_games", []))

        # Results should show G1 as no-winner (redraw eligible)
        g1 = [r for r in data["results"] if r["game_id"] == "A0000001-0000-4000-A000-000000000001"]
        self.assertTrue(g1[0]["is_solo_dismissed"])
        self.assertFalse(g1[0]["has_winner"])

    def test_resolve_multi_entrant_exhausted(self):
        """Resolve exhausts a multi-entrant game (cascade scenario).

        G1 had [B1, B2]. B1 was already resolved away (winner_index=1).
        Now B2 wins G1+G3, user keeps G3 -> G1 exhausted.
        """
        state = [
            {
                "game": {"id": "A0000001-0000-4000-A000-000000000001", "name": "Catan"},
                "shuffled": [
                    {"badge_id": "B1", "id": "e1", "name": "Alice"},
                    {"badge_id": "B2", "id": "e2", "name": "Bob"},
                ],
                "winner_index": 1,  # B2 is current winner (B1 already skipped)
            },
            {
                "game": {"id": "A0000003-0000-4000-A000-000000000003", "name": "Wingspan"},
                "shuffled": [
                    {"badge_id": "B2", "id": "e4", "name": "Bob"},
                ],
                "winner_index": 0,
            },
        ]
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["drawing_state"] = state
            sess["drawing_conflicts"] = [{
                "badge_id": "B2", "winner_name": "Bob",
                "game_ids": ["A0000001-0000-4000-A000-000000000001", "A0000003-0000-4000-A000-000000000003"],
                "game_names": {"A0000001-0000-4000-A000-000000000001": "Catan", "A0000003-0000-4000-A000-000000000003": "Wingspan"},
                "is_premium_conflict": False,
            }]
            sess["premium_games"] = []

        resp = self.client.post("/drawing/resolve",
                                json={"resolutions": [
                                    {"badge_id": "B2", "keep_game_id": "A0000003-0000-4000-A000-000000000003"},
                                ]},
                                content_type="application/json")
        data = resp.get_json()
        self.assertTrue(data["ok"])

        # G1 had 2 entrants, both resolved away -> exhausted
        with self.client.session_transaction() as sess:
            self.assertIn("A0000001-0000-4000-A000-000000000001", sess.get("solo_dismissed_games", []))

        g1 = [r for r in data["results"] if r["game_id"] == "A0000001-0000-4000-A000-000000000001"]
        self.assertTrue(g1[0]["is_solo_dismissed"])
        self.assertFalse(g1[0]["has_winner"])

    def test_dismiss_cascading_conflict(self):
        """Dismissing G1 advances to B2 who already wins G3 -> new conflict."""
        state = [
            {
                "game": {"id": "A0000001-0000-4000-A000-000000000001", "name": "Catan"},
                "shuffled": [
                    {"badge_id": "B1", "id": "e1", "name": "Alice"},
                    {"badge_id": "B2", "id": "e3", "name": "Bob"},
                ],
                "winner_index": 0,
            },
            {
                "game": {"id": "A0000002-0000-4000-A000-000000000002", "name": "Ticket to Ride"},
                "shuffled": [
                    {"badge_id": "B1", "id": "e2", "name": "Alice"},
                ],
                "winner_index": 0,
            },
            {
                "game": {"id": "A0000003-0000-4000-A000-000000000003", "name": "Wingspan"},
                "shuffled": [
                    {"badge_id": "B2", "id": "e4", "name": "Bob"},
                ],
                "winner_index": 0,
            },
        ]
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["drawing_state"] = state
            sess["drawing_conflicts"] = [{
                "badge_id": "B1", "winner_name": "Alice",
                "game_ids": ["A0000001-0000-4000-A000-000000000001", "A0000002-0000-4000-A000-000000000002"],
                "game_names": {"A0000001-0000-4000-A000-000000000001": "Catan", "A0000002-0000-4000-A000-000000000002": "Ticket to Ride"},
                "is_premium_conflict": False,
            }]
            sess["premium_games"] = []

        resp = self.client.post("/drawing/dismiss-game",
                                json={"badge_id": "B1", "game_id": "A0000001-0000-4000-A000-000000000001"},
                                content_type="application/json")
        data = resp.get_json()
        self.assertTrue(data["ok"])

        # B1's conflict is resolved (only G2 left), but B2 now has G1+G3
        self.assertEqual(len(data["conflicts"]), 1)
        self.assertEqual(data["conflicts"][0]["badge_id"], "B2")
        self.assertEqual(set(data["conflicts"][0]["game_ids"]), {"A0000001-0000-4000-A000-000000000001", "A0000003-0000-4000-A000-000000000003"})

    def test_dismiss_shown_in_results_template(self):
        """Dismissed game shows 'No winner (redraw eligible)' not 'To the box!'."""
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["drawing_state"] = [
                {
                    "game": {"id": "A0000001-0000-4000-A000-000000000001", "name": "Catan"},
                    "shuffled": [
                        {"badge_id": "B1", "id": "e1", "name": "Alice"},
                    ],
                    "winner_index": 1,  # exhausted
                },
            ]
            sess["solo_dismissed_games"] = ["A0000001-0000-4000-A000-000000000001"]

        resp = self.client.get("/drawing/results")
        html = resp.data.decode()
        self.assertIn("No winner (redraw eligible)", html)
        # The no-entries table should NOT show "To the box!" for this game
        no_entries_start = html.index('id="no-entries-table"')
        no_entries_end = html.index("</table>", no_entries_start)
        no_entries_table = html[no_entries_start:no_entries_end]
        self.assertNotIn("To the box!", no_entries_table)

    def test_new_drawing_clears_solo_dismissed(self):
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["library_id"] = "10000001-0000-4000-A000-000000000001"
            sess["convention_id"] = "C0000001-0000-4000-A000-000000000001"
            sess["convention_name"] = "GameFest"
            sess["solo_dismissed_games"] = ["A0000001-0000-4000-A000-000000000001"]
            sess["cached_games"] = [{"id": "A0000001-0000-4000-A000-000000000001", "name": "Catan"}]
            sess["cached_entries"] = [
                {"id": "e1", "badge_id": "B1", "librarygame_id": "A0000001-0000-4000-A000-000000000001", "name": "Alice"},
            ]

        self.client.post("/drawing")

        with self.client.session_transaction() as sess:
            self.assertEqual(sess["solo_dismissed_games"], [])


class TestAwardNextRoute(unittest.TestCase):

    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.app.config["TTE_API_KEY"] = "test-key"
        self.client = self.app.test_client()

    def _setup_drawing_state(self, picked_up=None, not_here=None):
        drawing_state = [
            {
                "game": {"id": "A0000001-0000-4000-A000-000000000001", "name": "Catan"},
                "shuffled": [
                    {"badge_id": "B1", "librarygame_id": "A0000001-0000-4000-A000-000000000001", "id": "e1", "name": "Alice"},
                    {"badge_id": "B2", "librarygame_id": "A0000001-0000-4000-A000-000000000001", "id": "e2", "name": "Bob"},
                    {"badge_id": "B3", "librarygame_id": "A0000001-0000-4000-A000-000000000001", "id": "e3", "name": "Carol"},
                ],
                "winner_index": 0,
            },
        ]
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["drawing_state"] = drawing_state
            sess["convention_name"] = "GameFest"
            sess["picked_up"] = picked_up or []
            sess["not_here"] = not_here or []

    def test_award_next_requires_auth(self):
        resp = self.client.post("/drawing/award-next",
                                json={"game_id": "A0000001-0000-4000-A000-000000000001"},
                                content_type="application/json")
        self.assertEqual(resp.status_code, 401)

    def test_award_next_requires_drawing_state(self):
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
        resp = self.client.post("/drawing/award-next",
                                json={"game_id": "A0000001-0000-4000-A000-000000000001"},
                                content_type="application/json")
        self.assertEqual(resp.status_code, 400)

    def test_award_next_validates_input(self):
        self._setup_drawing_state()
        resp = self.client.post("/drawing/award-next",
                                json={},
                                content_type="application/json")
        self.assertEqual(resp.status_code, 400)

    def test_award_next_advances_winner(self):
        self._setup_drawing_state()
        resp = self.client.post("/drawing/award-next",
                                json={"game_id": "A0000001-0000-4000-A000-000000000001"},
                                content_type="application/json")
        data = resp.get_json()
        self.assertTrue(data["ok"])
        self.assertTrue(data["has_winner"])
        self.assertEqual(data["winner_name"], "Bob")
        self.assertEqual(data["winner_badge"], "B2")

        with self.client.session_transaction() as sess:
            self.assertEqual(sess["drawing_state"][0]["winner_index"], 1)

    def test_award_next_skips_not_here(self):
        self._setup_drawing_state(not_here=["B2"])
        resp = self.client.post("/drawing/award-next",
                                json={"game_id": "A0000001-0000-4000-A000-000000000001"},
                                content_type="application/json")
        data = resp.get_json()
        self.assertTrue(data["ok"])
        self.assertTrue(data["has_winner"])
        self.assertEqual(data["winner_name"], "Carol")
        self.assertEqual(data["winner_badge"], "B3")

    def test_award_next_exhausted(self):
        # Only one entrant
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["drawing_state"] = [{
                "game": {"id": "A0000001-0000-4000-A000-000000000001", "name": "Catan"},
                "shuffled": [{"badge_id": "B1", "librarygame_id": "A0000001-0000-4000-A000-000000000001", "id": "e1", "name": "Alice"}],
                "winner_index": 0,
            }]
            sess["not_here"] = []
        resp = self.client.post("/drawing/award-next",
                                json={"game_id": "A0000001-0000-4000-A000-000000000001"},
                                content_type="application/json")
        data = resp.get_json()
        self.assertTrue(data["ok"])
        self.assertFalse(data["has_winner"])


class TestMarkNotHereRoute(unittest.TestCase):

    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.app.config["TTE_API_KEY"] = "test-key"
        self.client = self.app.test_client()

    def _setup_drawing_state(self, picked_up=None):
        drawing_state = [
            {
                "game": {"id": "A0000001-0000-4000-A000-000000000001", "name": "Catan"},
                "shuffled": [
                    {"badge_id": "B1", "librarygame_id": "A0000001-0000-4000-A000-000000000001", "id": "e1", "name": "Alice"},
                    {"badge_id": "B2", "librarygame_id": "A0000001-0000-4000-A000-000000000001", "id": "e2", "name": "Bob"},
                ],
                "winner_index": 0,
            },
            {
                "game": {"id": "A0000002-0000-4000-A000-000000000002", "name": "Ticket to Ride"},
                "shuffled": [
                    {"badge_id": "B1", "librarygame_id": "A0000002-0000-4000-A000-000000000002", "id": "e3", "name": "Alice"},
                    {"badge_id": "B3", "librarygame_id": "A0000002-0000-4000-A000-000000000002", "id": "e4", "name": "Carol"},
                ],
                "winner_index": 0,
            },
        ]
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["drawing_state"] = drawing_state
            sess["convention_name"] = "GameFest"
            sess["picked_up"] = picked_up or []
            sess["not_here"] = []
            sess["not_here_warning_dismissed"] = False

    def test_not_here_requires_auth(self):
        resp = self.client.post("/drawing/not-here",
                                json={"badge_id": "B1"},
                                content_type="application/json")
        self.assertEqual(resp.status_code, 401)

    def test_not_here_requires_drawing_state(self):
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
        resp = self.client.post("/drawing/not-here",
                                json={"badge_id": "B1"},
                                content_type="application/json")
        self.assertEqual(resp.status_code, 400)

    def test_not_here_validates_input(self):
        self._setup_drawing_state()
        resp = self.client.post("/drawing/not-here",
                                json={},
                                content_type="application/json")
        self.assertEqual(resp.status_code, 400)

    def test_not_here_marks_badge_and_advances_games(self):
        self._setup_drawing_state()
        resp = self.client.post("/drawing/not-here",
                                json={"badge_id": "B1"},
                                content_type="application/json")
        data = resp.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["badge_id"], "B1")
        # B1 won both games, so both should be advanced
        self.assertEqual(len(data["advanced_games"]), 2)

        with self.client.session_transaction() as sess:
            self.assertIn("B1", sess["not_here"])
            # G1: B1 was winner, now B2
            self.assertEqual(sess["drawing_state"][0]["winner_index"], 1)
            # G2: B1 was winner, now B3
            self.assertEqual(sess["drawing_state"][1]["winner_index"], 1)

    def test_not_here_skips_picked_up_games(self):
        self._setup_drawing_state(picked_up=["A0000001-0000-4000-A000-000000000001"])
        resp = self.client.post("/drawing/not-here",
                                json={"badge_id": "B1"},
                                content_type="application/json")
        data = resp.get_json()
        self.assertTrue(data["ok"])
        # G1 is picked up, only G2 should be advanced
        self.assertEqual(len(data["advanced_games"]), 1)
        self.assertEqual(data["advanced_games"][0]["game_id"], "A0000002-0000-4000-A000-000000000002")

    def test_not_here_duplicate_returns_error(self):
        self._setup_drawing_state()
        self.client.post("/drawing/not-here",
                         json={"badge_id": "B1"},
                         content_type="application/json")
        resp = self.client.post("/drawing/not-here",
                                json={"badge_id": "B1"},
                                content_type="application/json")
        self.assertEqual(resp.status_code, 400)

    def test_not_here_dismiss_warning(self):
        self._setup_drawing_state()
        resp = self.client.post("/drawing/not-here",
                                json={"badge_id": "B1", "dismiss_warning": True},
                                content_type="application/json")
        self.assertTrue(resp.get_json()["ok"])
        with self.client.session_transaction() as sess:
            self.assertTrue(sess["not_here_warning_dismissed"])


class TestRedrawUnclaimedRoute(unittest.TestCase):

    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.app.config["TTE_API_KEY"] = "test-key"
        self.client = self.app.test_client()

    def _setup_drawing_state(self, picked_up=None):
        drawing_state = [
            {
                "game": {"id": "A0000001-0000-4000-A000-000000000001", "name": "Catan"},
                "shuffled": [
                    {"badge_id": "B1", "librarygame_id": "A0000001-0000-4000-A000-000000000001", "id": "e1", "name": "Alice"},
                    {"badge_id": "B2", "librarygame_id": "A0000001-0000-4000-A000-000000000001", "id": "e2", "name": "Bob"},
                    {"badge_id": "B3", "librarygame_id": "A0000001-0000-4000-A000-000000000001", "id": "e3", "name": "Carol"},
                ],
                "winner_index": 0,
            },
            {
                "game": {"id": "A0000002-0000-4000-A000-000000000002", "name": "Ticket to Ride"},
                "shuffled": [
                    {"badge_id": "B4", "librarygame_id": "A0000002-0000-4000-A000-000000000002", "id": "e4", "name": "Dave"},
                ],
                "winner_index": 0,
            },
        ]
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["drawing_state"] = drawing_state
            sess["convention_name"] = "GameFest"
            sess["picked_up"] = picked_up or []
            sess["not_here"] = []
            sess["premium_games"] = []

    def test_redraw_requires_auth(self):
        resp = self.client.post("/drawing/redraw-unclaimed",
                                json={},
                                content_type="application/json")
        self.assertEqual(resp.status_code, 401)

    def test_redraw_requires_drawing_state(self):
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
        resp = self.client.post("/drawing/redraw-unclaimed",
                                json={},
                                content_type="application/json")
        self.assertEqual(resp.status_code, 400)

    def test_redraw_all_picked_up_returns_error(self):
        self._setup_drawing_state(picked_up=["A0000001-0000-4000-A000-000000000001", "A0000002-0000-4000-A000-000000000002"])
        resp = self.client.post("/drawing/redraw-unclaimed",
                                json={},
                                content_type="application/json")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("No unclaimed", resp.get_json()["error"])

    def test_redraw_returns_results(self):
        self._setup_drawing_state(picked_up=["A0000002-0000-4000-A000-000000000002"])
        resp = self.client.post("/drawing/redraw-unclaimed",
                                json={},
                                content_type="application/json")
        data = resp.get_json()
        self.assertTrue(data["ok"])
        self.assertIn("results", data)
        self.assertIsInstance(data["conflicts"], list)

    def test_redraw_updates_session(self):
        self._setup_drawing_state(picked_up=["A0000002-0000-4000-A000-000000000002"])
        self.client.post("/drawing/redraw-unclaimed",
                         json={},
                         content_type="application/json")
        with self.client.session_transaction() as sess:
            # drawing_state should be updated (shuffled list changed)
            self.assertIsNotNone(sess["drawing_state"])

    def test_rerun_clears_not_here(self):
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["library_id"] = "10000001-0000-4000-A000-000000000001"
            sess["convention_id"] = "C0000001-0000-4000-A000-000000000001"
            sess["convention_name"] = "GameFest"
            sess["not_here"] = ["B1"]
            sess["not_here_warning_dismissed"] = True
            sess["cached_games"] = [{"id": "A0000001-0000-4000-A000-000000000001", "name": "Catan"}]
            sess["cached_entries"] = [
                {"id": "e1", "badge_id": "B1", "librarygame_id": "A0000001-0000-4000-A000-000000000001", "name": "Alice"},
            ]

        self.client.post("/drawing")

        with self.client.session_transaction() as sess:
            self.assertEqual(sess["not_here"], [])
            self.assertFalse(sess["not_here_warning_dismissed"])


class TestPushToTTE(unittest.TestCase):

    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.app.config["TTE_API_KEY"] = "test-key"
        self.client = self.app.test_client()

    def _setup_session(self, picked_up=None):
        drawing_state = [
            {
                "game": {"id": "A0000001-0000-4000-A000-000000000001", "name": "Catan"},
                "shuffled": [
                    {"badge_id": "B1", "librarygame_id": "A0000001-0000-4000-A000-000000000001", "id": "e1", "name": "Alice"},
                    {"badge_id": "B2", "librarygame_id": "A0000001-0000-4000-A000-000000000001", "id": "e2", "name": "Bob"},
                ],
                "winner_index": 0,
            },
            {
                "game": {"id": "A0000002-0000-4000-A000-000000000002", "name": "Ticket to Ride"},
                "shuffled": [
                    {"badge_id": "B3", "librarygame_id": "A0000002-0000-4000-A000-000000000002", "id": "e3", "name": "Carol"},
                ],
                "winner_index": 0,
            },
        ]
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["drawing_state"] = drawing_state
            sess["picked_up"] = picked_up or []

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

    @patch("routes.helpers.TTEClient")
    def test_push_updates_picked_up_games(self, MockClient):
        mock_instance = MagicMock()
        MockClient.return_value = mock_instance

        self._setup_session(picked_up=["A0000001-0000-4000-A000-000000000001", "A0000002-0000-4000-A000-000000000002"])
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

    @patch("routes.helpers.TTEClient")
    def test_push_uses_advanced_winner(self, MockClient):
        mock_instance = MagicMock()
        MockClient.return_value = mock_instance

        # G1 winner was advanced to index 1 (Bob), simulating award-next
        drawing_state = [
            {
                "game": {"id": "A0000001-0000-4000-A000-000000000001", "name": "Catan"},
                "shuffled": [
                    {"badge_id": "B1", "librarygame_id": "A0000001-0000-4000-A000-000000000001", "id": "e1", "name": "Alice"},
                    {"badge_id": "B2", "librarygame_id": "A0000001-0000-4000-A000-000000000001", "id": "e2", "name": "Bob"},
                ],
                "winner_index": 1,
            },
        ]
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["drawing_state"] = drawing_state
            sess["picked_up"] = ["A0000001-0000-4000-A000-000000000001"]

        resp = self.client.post("/drawing/push",
                                content_type="application/json")
        data = resp.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["successes"], 1)

        # Should update e2 (Bob's entry), not e1 (Alice's)
        mock_instance.update_playtowin.assert_called_once_with("e2", {"win": 1})

    @patch("routes.helpers.TTEClient")
    def test_push_handles_partial_failure(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.update_playtowin.side_effect = [
            None,  # first call succeeds
            TTEAPIError("Server error", 500),  # second call fails
        ]
        MockClient.return_value = mock_instance

        self._setup_session(picked_up=["A0000001-0000-4000-A000-000000000001", "A0000002-0000-4000-A000-000000000002"])
        resp = self.client.post("/drawing/push",
                                content_type="application/json")
        data = resp.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["successes"], 1)
        self.assertEqual(len(data["failures"]), 1)
        self.assertIn("Server error", data["failures"][0]["error"])

    def test_push_button_in_results(self):
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["library_id"] = "10000001-0000-4000-A000-000000000001"
            sess["convention_id"] = "C0000001-0000-4000-A000-000000000001"
            sess["convention_name"] = "GameFest"
            sess["cached_games"] = [{"id": "A0000001-0000-4000-A000-000000000001", "name": "Catan"}]
            sess["cached_entries"] = [
                {"id": "e1", "badge_id": "B1", "librarygame_id": "A0000001-0000-4000-A000-000000000001", "name": "Alice"},
            ]

        resp = self.client.post("/drawing", follow_redirects=True)
        self.assertIn(b"Push to TTE", resp.data)
        self.assertIn(b'id="push-btn"', resp.data)


class TestCSVExport(unittest.TestCase):

    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.app.config["TTE_API_KEY"] = "test-key"
        self.client = self.app.test_client()

    def _setup_session(self, picked_up=None, premium=None,
                       convention_name="PawCon 2026"):
        drawing_state = [
            {
                "game": {"id": "A0000001-0000-4000-A000-000000000001", "name": "Catan"},
                "shuffled": [
                    {"badge_id": "B1", "librarygame_id": "A0000001-0000-4000-A000-000000000001", "id": "e1", "name": "Alice"},
                    {"badge_id": "B2", "librarygame_id": "A0000001-0000-4000-A000-000000000001", "id": "e2", "name": "Bob"},
                ],
                "winner_index": 0,
            },
            {
                "game": {"id": "A0000002-0000-4000-A000-000000000002", "name": "Ticket to Ride"},
                "shuffled": [
                    {"badge_id": "B3", "librarygame_id": "A0000002-0000-4000-A000-000000000002", "id": "e3", "name": "Carol"},
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
        self.assertEqual(lines[0], "Game,Winner's Name,Winner's Badge")

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
        # Catan: winner is Alice (index 0), badge B1
        self.assertEqual(lines[1], "Catan,Alice,B1")
        # Ticket to Ride: winner is Carol, badge B3
        self.assertEqual(lines[2], "Ticket to Ride,Carol,B3")

    def test_export_has_three_columns(self):
        self._setup_session()
        resp = self.client.get("/drawing/export")
        lines = resp.data.decode().strip().split("\r\n")
        # Each data row should have exactly 3 columns
        for line in lines[1:]:
            self.assertEqual(len(line.split(",")), 3)

    def test_export_no_winner_shows_empty(self):
        drawing_state = [
            {
                "game": {"id": "A0000001-0000-4000-A000-000000000001", "name": "Catan"},
                "shuffled": [],
                "winner_index": -1,
            },
        ]
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["convention_name"] = "PawCon 2026"
            sess["drawing_state"] = drawing_state
            sess["picked_up"] = []
            sess["premium_games"] = []
        resp = self.client.get("/drawing/export")
        lines = resp.data.decode().strip().split("\r\n")
        self.assertEqual(lines[1], "Catan,,")

    def test_export_advanced_winner(self):
        # G1 winner was advanced to index 1 (Bob)
        drawing_state = [
            {
                "game": {"id": "A0000001-0000-4000-A000-000000000001", "name": "Catan"},
                "shuffled": [
                    {"badge_id": "B1", "librarygame_id": "A0000001-0000-4000-A000-000000000001", "id": "e1", "name": "Alice"},
                    {"badge_id": "B2", "librarygame_id": "A0000001-0000-4000-A000-000000000001", "id": "e2", "name": "Bob"},
                ],
                "winner_index": 1,
            },
        ]
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["convention_name"] = "PawCon 2026"
            sess["drawing_state"] = drawing_state
            sess["picked_up"] = []
            sess["premium_games"] = []
        resp = self.client.get("/drawing/export")
        lines = resp.data.decode().strip().split("\r\n")
        # Winner should be Bob instead of Alice
        self.assertEqual(lines[1], "Catan,Bob,B2")

    def test_export_button_on_results_page(self):
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["convention_id"] = "C0000001-0000-4000-A000-000000000001"
            sess["convention_name"] = "Test Con"
            sess["library_id"] = "10000001-0000-4000-A000-000000000001"
            sess["library_name"] = "P2W Library"
            sess["premium_games"] = []
            sess["cached_games"] = [{"id": "A0000001-0000-4000-A000-000000000001", "name": "Catan"}]
            sess["cached_entries"] = [
                {"librarygame_id": "A0000001-0000-4000-A000-000000000001", "badge_id": "B1", "id": "e1",
                 "name": "Alice", "gamename": "Catan"},
            ]
        resp = self.client.post("/drawing", follow_redirects=True)
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
            sess["convention_id"] = "C0000001-0000-4000-A000-000000000001"
            sess["convention_name"] = "Test Con"
            sess["library_id"] = "10000001-0000-4000-A000-000000000001"
            sess["library_name"] = "P2W Library"
            sess["premium_games"] = []

    # ── Auth expiration clears session ─────────────────────────────────

    @patch("routes.helpers.TTEClient")
    def test_convention_select_auth_error_clears_session(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.get_convention.side_effect = TTEAPIError("Unauthorized", 401)
        MockClient.return_value = mock_instance
        self._setup_session()

        resp = self.client.post("/convention/select",
                                data={"convention_id": "C0000001-0000-4000-A000-000000000001"})
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.headers["Location"])

        with self.client.session_transaction() as sess:
            self.assertNotIn("tte_session_id", sess)

    @patch("routes.helpers.TTEClient")
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

    def test_drawing_no_cache_redirects_to_games(self):
        self._setup_session()

        resp = self.client.post("/drawing")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/games", resp.headers["Location"])

    @patch("routes.helpers.TTEClient")
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

    @patch("routes.helpers.TTEClient")
    def test_push_auth_error_returns_401(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.update_playtowin.side_effect = TTEAPIError("Expired", 401)
        MockClient.return_value = mock_instance

        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["drawing_state"] = [{
                "game": {"id": "A0000001-0000-4000-A000-000000000001", "name": "Catan"},
                "shuffled": [{"badge_id": "B1", "id": "e1", "name": "Alice"}],
                "winner_index": 0,
            }]
            sess["picked_up"] = ["A0000001-0000-4000-A000-000000000001"]
            sess["redistribution_winners"] = {}

        resp = self.client.post("/drawing/push",
                                content_type="application/json")
        self.assertEqual(resp.status_code, 401)
        data = resp.get_json()
        self.assertIn("expired", data["error"].lower())

    # ── Timeout produces friendly message ──────────────────────────────

    @patch("routes.helpers.TTEClient")
    def test_games_timeout_shows_friendly_message(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.get_library_games.side_effect = TTETimeoutError()
        MockClient.return_value = mock_instance
        self._setup_session()

        resp = self.client.get("/games", follow_redirects=True)
        self.assertIn(b"timed out", resp.data)
        self.assertIn(b"try again", resp.data.lower())

    def test_drawing_no_cache_shows_flash(self):
        self._setup_session()

        resp = self.client.post("/drawing", follow_redirects=True)
        self.assertIn(b"Please load the games page first", resp.data)

    @patch("routes.helpers.TTEClient")
    def test_convention_timeout_shows_friendly_message(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.get_convention.side_effect = TTETimeoutError()
        MockClient.return_value = mock_instance
        self._setup_session()

        resp = self.client.post("/convention/select",
                                data={"convention_id": "C0000001-0000-4000-A000-000000000001"},
                                follow_redirects=True)
        self.assertIn(b"timed out", resp.data)

    @patch("routes.helpers.TTEClient")
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

    @patch("routes.helpers.TTEClient")
    def test_games_500_error_shows_action_message(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.get_library_games.side_effect = TTEAPIError("Server error", 500)
        MockClient.return_value = mock_instance
        self._setup_session()

        resp = self.client.get("/games", follow_redirects=True)
        self.assertIn(b"Could not load games", resp.data)

    @patch("routes.helpers.TTEClient")
    def test_games_entry_loading_error_shows_action(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.get_library_games.return_value = []
        mock_instance.get_convention_playtowins.side_effect = TTEAPIError("Server error", 500)
        MockClient.return_value = mock_instance
        self._setup_session()

        resp = self.client.get("/games", follow_redirects=True)
        self.assertIn(b"Could not load entries", resp.data)

    def test_drawing_partial_cache_redirects_to_games(self):
        self._setup_session()
        with self.client.session_transaction() as sess:
            sess["cached_games"] = [{"id": "A0000001-0000-4000-A000-000000000001", "name": "Catan"}]
            # cached_entries intentionally missing

        resp = self.client.post("/drawing")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/games", resp.headers["Location"])


class TestRefreshData(unittest.TestCase):

    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.app.config["TTE_API_KEY"] = "test-key"
        self.client = self.app.test_client()

    @patch("routes.helpers.TTEClient")
    def test_games_page_shows_refresh_button(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.get_library_games.return_value = [
            {"id": "A0000001-0000-4000-A000-000000000001", "name": "Catan"},
        ]
        mock_instance.get_convention_playtowins.return_value = [
            {"id": "e1", "badge_id": "B1", "librarygame_id": "A0000001-0000-4000-A000-000000000001"},
        ]
        MockClient.return_value = mock_instance

        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["library_id"] = "10000001-0000-4000-A000-000000000001"
            sess["convention_id"] = "C0000001-0000-4000-A000-000000000001"
            sess["convention_name"] = "GameFest"

        resp = self.client.get("/games")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Refresh Data", resp.data)
        self.assertIn(b"loading-overlay", resp.data)

    @patch("routes.helpers.TTEClient")
    def test_games_page_shows_loaded_timestamp(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.get_library_games.return_value = []
        mock_instance.get_convention_playtowins.return_value = []
        MockClient.return_value = mock_instance

        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["library_id"] = "10000001-0000-4000-A000-000000000001"
            sess["convention_id"] = "C0000001-0000-4000-A000-000000000001"
            sess["convention_name"] = "GameFest"

        resp = self.client.get("/games")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Loaded", resp.data)

    @patch("routes.helpers.TTEClient")
    def test_refresh_preserves_premium_selections(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.get_library_games.return_value = [
            {"id": "A0000001-0000-4000-A000-000000000001", "name": "Catan"},
            {"id": "A0000002-0000-4000-A000-000000000002", "name": "Wingspan"},
        ]
        mock_instance.get_convention_playtowins.return_value = [
            {"id": "e1", "badge_id": "B1", "librarygame_id": "A0000001-0000-4000-A000-000000000001"},
            {"id": "e2", "badge_id": "B2", "librarygame_id": "A0000002-0000-4000-A000-000000000002"},
        ]
        MockClient.return_value = mock_instance

        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["library_id"] = "10000001-0000-4000-A000-000000000001"
            sess["convention_id"] = "C0000001-0000-4000-A000-000000000001"
            sess["convention_name"] = "GameFest"
            sess["premium_games"] = ["A0000001-0000-4000-A000-000000000001"]

        resp = self.client.get("/games")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'checked', resp.data)
        self.assertIn(b'Premium', resp.data)

        # Premium selections still in session after refresh
        with self.client.session_transaction() as sess:
            self.assertEqual(sess["premium_games"], ["A0000001-0000-4000-A000-000000000001"])

    @patch("routes.helpers.TTEClient")
    def test_refresh_fetches_fresh_data(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.get_library_games.return_value = [
            {"id": "A0000001-0000-4000-A000-000000000001", "name": "Catan"},
        ]
        mock_instance.get_convention_playtowins.return_value = []
        MockClient.return_value = mock_instance

        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["library_id"] = "10000001-0000-4000-A000-000000000001"
            sess["convention_id"] = "C0000001-0000-4000-A000-000000000001"
            sess["convention_name"] = "GameFest"

        # First load — fetches from API
        self.client.get("/games")
        self.assertEqual(mock_instance.get_library_games.call_count, 1)
        # Second load without refresh — uses cache
        self.client.get("/games")
        self.assertEqual(mock_instance.get_library_games.call_count, 1)
        # Third load with refresh=1 — fetches fresh data
        self.client.get("/games?refresh=1")
        self.assertEqual(mock_instance.get_library_games.call_count, 2)

    def test_drawing_results_shows_timestamp(self):
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["library_id"] = "10000001-0000-4000-A000-000000000001"
            sess["convention_id"] = "C0000001-0000-4000-A000-000000000001"
            sess["convention_name"] = "GameFest"
            sess["cached_games"] = [{"id": "A0000001-0000-4000-A000-000000000001", "name": "Catan"}]
            sess["cached_entries"] = [
                {"id": "e1", "badge_id": "B1", "librarygame_id": "A0000001-0000-4000-A000-000000000001", "name": "Alice"},
            ]

        resp = self.client.post("/drawing", follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Data from", resp.data)

    def test_drawing_stores_timestamp_in_session(self):
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["library_id"] = "10000001-0000-4000-A000-000000000001"
            sess["convention_id"] = "C0000001-0000-4000-A000-000000000001"
            sess["convention_name"] = "GameFest"
            sess["cached_games"] = [{"id": "A0000001-0000-4000-A000-000000000001", "name": "Catan"}]
            sess["cached_entries"] = [
                {"id": "e1", "badge_id": "B1", "librarygame_id": "A0000001-0000-4000-A000-000000000001", "name": "Alice"},
            ]

        self.client.post("/drawing")

        with self.client.session_transaction() as sess:
            self.assertIn("drawing_timestamp", sess)
            self.assertTrue(len(sess["drawing_timestamp"]) > 0)

    @patch("routes.helpers.TTEClient")
    def test_games_page_has_sortable_headers(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.get_library_games.return_value = [
            {"id": "A0000001-0000-4000-A000-000000000001", "name": "Catan"},
        ]
        mock_instance.get_convention_playtowins.return_value = [
            {"id": "e1", "badge_id": "B1", "librarygame_id": "A0000001-0000-4000-A000-000000000001"},
        ]
        MockClient.return_value = mock_instance

        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["library_id"] = "10000001-0000-4000-A000-000000000001"
            sess["convention_id"] = "C0000001-0000-4000-A000-000000000001"
            sess["convention_name"] = "GameFest"

        resp = self.client.get("/games")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'data-sort="name"', resp.data)
        self.assertIn(b'data-sort="entries"', resp.data)
        self.assertIn(b'data-sort="premium"', resp.data)
        self.assertIn(b'sortable', resp.data)

    @patch("routes.helpers.TTEClient")
    def test_games_page_has_search(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.get_library_games.return_value = [
            {"id": "A0000001-0000-4000-A000-000000000001", "name": "Catan"},
        ]
        mock_instance.get_convention_playtowins.return_value = [
            {"id": "e1", "badge_id": "B1", "librarygame_id": "A0000001-0000-4000-A000-000000000001"},
        ]
        MockClient.return_value = mock_instance

        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["library_id"] = "10000001-0000-4000-A000-000000000001"
            sess["convention_id"] = "C0000001-0000-4000-A000-000000000001"
            sess["convention_name"] = "GameFest"

        resp = self.client.get("/games")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'game-search-input', resp.data)
        self.assertIn(b'Search games', resp.data)

    @patch("routes.helpers.TTEClient")
    def test_games_page_has_sort_data_attributes(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.get_library_games.return_value = [
            {"id": "A0000001-0000-4000-A000-000000000001", "name": "Catan"},
            {"id": "A0000002-0000-4000-A000-000000000002", "name": "Wingspan"},
        ]
        mock_instance.get_convention_playtowins.return_value = [
            {"id": "e1", "badge_id": "B1", "librarygame_id": "A0000001-0000-4000-A000-000000000001"},
            {"id": "e2", "badge_id": "B2", "librarygame_id": "A0000002-0000-4000-A000-000000000002"},
        ]
        MockClient.return_value = mock_instance

        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["library_id"] = "10000001-0000-4000-A000-000000000001"
            sess["convention_id"] = "C0000001-0000-4000-A000-000000000001"
            sess["convention_name"] = "GameFest"

        resp = self.client.get("/games")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'data-game-name="catan"', resp.data)
        self.assertIn(b'data-entrant-count="1"', resp.data)
        self.assertIn(b'data-is-premium=', resp.data)


class TestEjectPlayerRoute(unittest.TestCase):

    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.app.config["TTE_API_KEY"] = "test-key"
        self.client = self.app.test_client()

    def _auth(self, **extra):
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["tte_username"] = "admin"
            for k, v in extra.items():
                sess[k] = v

    def test_eject_requires_auth(self):
        resp = self.client.post("/games/eject", json={"badge_id": "B1"})
        self.assertEqual(resp.status_code, 401)

    def test_eject_requires_badge_id(self):
        self._auth()
        resp = self.client.post("/games/eject", json={})
        self.assertEqual(resp.status_code, 400)

    def test_eject_adds_to_session(self):
        self._auth()
        resp = self.client.post("/games/eject", json={"badge_id": "B1"})
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["ok"])
        with self.client.session_transaction() as sess:
            self.assertEqual(sess["ejected_entries"], [["B1", "*"]])

    def test_eject_specific_game(self):
        self._auth()
        resp = self.client.post("/games/eject", json={"badge_id": "B1", "game_id": "A0000001-0000-4000-A000-000000000001"})
        self.assertEqual(resp.status_code, 200)
        with self.client.session_transaction() as sess:
            self.assertEqual(sess["ejected_entries"], [["B1", "A0000001-0000-4000-A000-000000000001"]])

    def test_eject_duplicate_returns_409(self):
        self._auth(ejected_entries=[["B1", "*"]])
        resp = self.client.post("/games/eject", json={"badge_id": "B1"})
        self.assertEqual(resp.status_code, 409)

    def test_eject_all_removes_per_game(self):
        self._auth(ejected_entries=[["B1", "A0000001-0000-4000-A000-000000000001"], ["B1", "A0000002-0000-4000-A000-000000000002"]])
        resp = self.client.post("/games/eject", json={"badge_id": "B1"})
        self.assertEqual(resp.status_code, 200)
        with self.client.session_transaction() as sess:
            # Per-game ejections replaced with wildcard
            self.assertEqual(sess["ejected_entries"], [["B1", "*"]])

    def test_eject_name_with_spaces(self):
        """Badge IDs can be player names (fallback in process_entries)."""
        self._auth()
        resp = self.client.post("/games/eject", json={"badge_id": "John Smith"})
        self.assertEqual(resp.status_code, 200)
        with self.client.session_transaction() as sess:
            self.assertEqual(sess["ejected_entries"], [["John Smith", "*"]])


class TestUnejectPlayerRoute(unittest.TestCase):

    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.app.config["TTE_API_KEY"] = "test-key"
        self.client = self.app.test_client()

    def _auth(self, **extra):
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["tte_username"] = "admin"
            for k, v in extra.items():
                sess[k] = v

    def test_uneject_requires_auth(self):
        resp = self.client.post("/games/uneject", json={"badge_id": "B1"})
        self.assertEqual(resp.status_code, 401)

    def test_uneject_removes_from_session(self):
        self._auth(ejected_entries=[["B1", "*"]])
        resp = self.client.post("/games/uneject", json={"badge_id": "B1"})
        self.assertEqual(resp.status_code, 200)
        with self.client.session_transaction() as sess:
            self.assertEqual(sess["ejected_entries"], [])

    def test_uneject_not_found(self):
        self._auth(ejected_entries=[])
        resp = self.client.post("/games/uneject", json={"badge_id": "B1"})
        self.assertEqual(resp.status_code, 404)

    def test_uneject_specific_game(self):
        self._auth(ejected_entries=[["B1", "A0000001-0000-4000-A000-000000000001"], ["B1", "A0000002-0000-4000-A000-000000000002"]])
        resp = self.client.post("/games/uneject", json={"badge_id": "B1", "game_id": "A0000001-0000-4000-A000-000000000001"})
        self.assertEqual(resp.status_code, 200)
        with self.client.session_transaction() as sess:
            self.assertEqual(sess["ejected_entries"], [["B1", "A0000002-0000-4000-A000-000000000002"]])


class TestGetEntrantsRoute(unittest.TestCase):

    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.app.config["TTE_API_KEY"] = "test-key"
        self.client = self.app.test_client()

    def test_entrants_requires_auth(self):
        resp = self.client.get("/games/entrants/A0000001-0000-4000-A000-000000000001")
        self.assertEqual(resp.status_code, 401)

    @patch("routes.helpers.TTEClient")
    def test_entrants_returns_filtered_list(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.get_library_game_playtowins.return_value = [
            {"badge_id": "B1", "librarygame_id": "A0000001-0000-4000-A000-000000000001", "name": "Alice"},
            {"badge_id": "B2", "librarygame_id": "A0000001-0000-4000-A000-000000000001", "name": "Bob"},
        ]
        MockClient.return_value = mock_instance

        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["library_id"] = "10000001-0000-4000-A000-000000000001"
            sess["ejected_entries"] = [["B1", "*"]]

        resp = self.client.get("/games/entrants/A0000001-0000-4000-A000-000000000001")
        data = resp.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(len(data["entrants"]), 2)
        # B1 should be marked ejected
        b1 = next(e for e in data["entrants"] if e["badge_id"] == "B1")
        self.assertTrue(b1["ejected"])
        b2 = next(e for e in data["entrants"] if e["badge_id"] == "B2")
        self.assertFalse(b2["ejected"])

    @patch("routes.helpers.TTEClient")
    def test_entrants_per_game_ejection(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.get_library_game_playtowins.return_value = [
            {"badge_id": "B1", "librarygame_id": "A0000001-0000-4000-A000-000000000001", "name": "Alice"},
        ]
        MockClient.return_value = mock_instance

        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["library_id"] = "10000001-0000-4000-A000-000000000001"
            sess["ejected_entries"] = [["B1", "A0000001-0000-4000-A000-000000000001"]]

        resp = self.client.get("/games/entrants/A0000001-0000-4000-A000-000000000001")
        data = resp.get_json()
        self.assertTrue(data["entrants"][0]["ejected"])


class TestEjectionClearedOnSourceChange(unittest.TestCase):

    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.app.config["TTE_API_KEY"] = "test-key"
        self.client = self.app.test_client()

    @patch("routes.helpers.TTEClient")
    def test_convention_confirm_clears_ejections(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.get_convention.return_value = {
            "id": "C0000001-0000-4000-A000-000000000001",
            "name": "GameFest",
            "library": {"id": "10000001-0000-4000-A000-000000000001", "name": "Main Library"},
        }
        MockClient.return_value = mock_instance

        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["tte_username"] = "admin"
            sess["ejected_entries"] = [["B1", "*"]]

        self.client.post("/convention/select", data={"convention_id": "C0000001-0000-4000-A000-000000000001"})

        with self.client.session_transaction() as sess:
            self.assertNotIn("ejected_entries", sess)

    @patch("routes.helpers.TTEClient")
    def test_library_confirm_clears_ejections(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.get_library.return_value = {
            "id": "10000001-0000-4000-A000-000000000001",
            "name": "Main Library",
        }
        MockClient.return_value = mock_instance

        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["tte_username"] = "admin"
            sess["ejected_entries"] = [["B1", "*"]]

        self.client.post("/library/select", data={"library_id": "10000001-0000-4000-A000-000000000001"})

        with self.client.session_transaction() as sess:
            self.assertNotIn("ejected_entries", sess)

    @patch("routes.helpers.TTEClient")
    def test_library_select_clears_cached_games(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.get_library.return_value = {
            "id": "10000001-0000-4000-A000-000000000001",
            "name": "New Library",
        }
        MockClient.return_value = mock_instance

        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["tte_username"] = "admin"
            sess["cached_games"] = [{"id": "old-game"}]
            sess["cached_entries"] = [{"id": "old-entry"}]
            sess["drawing_state"] = {"some": "state"}
            sess["premium_games"] = ["A0000001-0000-4000-A000-000000000001"]
            sess["picked_up"] = {"A0000001-0000-4000-A000-000000000001": True}

        self.client.post("/library/select", data={"library_id": "10000001-0000-4000-A000-000000000001"})

        with self.client.session_transaction() as sess:
            self.assertNotIn("cached_games", sess)
            self.assertNotIn("cached_entries", sess)
            self.assertNotIn("drawing_state", sess)
            self.assertNotIn("premium_games", sess)
            self.assertNotIn("picked_up", sess)

    @patch("routes.helpers.TTEClient")
    def test_convention_select_clears_cached_games(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.get_convention.return_value = {
            "id": "C0000001-0000-4000-A000-000000000001",
            "name": "GameFest",
            "library": {"id": "10000001-0000-4000-A000-000000000001", "name": "Main Library"},
        }
        MockClient.return_value = mock_instance

        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["tte_username"] = "admin"
            sess["cached_games"] = [{"id": "old-game"}]
            sess["cached_entries"] = [{"id": "old-entry"}]
            sess["drawing_state"] = {"some": "state"}
            sess["not_here"] = {"B1": True}

        self.client.post("/convention/select", data={"convention_id": "C0000001-0000-4000-A000-000000000001"})

        with self.client.session_transaction() as sess:
            self.assertNotIn("cached_games", sess)
            self.assertNotIn("cached_entries", sess)
            self.assertNotIn("drawing_state", sess)
            self.assertNotIn("not_here", sess)


class TestPlayersRoute(unittest.TestCase):

    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.app.config["TTE_API_KEY"] = "test-key"
        self.client = self.app.test_client()

    def test_players_requires_login(self):
        resp = self.client.get("/games/players")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.headers["Location"])

    def test_players_requires_convention(self):
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
        resp = self.client.get("/games/players")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/convention", resp.headers["Location"])

    def test_players_lists_all_players(self):
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["library_id"] = "10000001-0000-4000-A000-000000000001"
            sess["convention_id"] = "C0000001-0000-4000-A000-000000000001"
            sess["convention_name"] = "GameFest"
            sess["cached_games"] = [
                {"id": "A0000001-0000-4000-A000-000000000001", "name": "Catan"},
                {"id": "A0000002-0000-4000-A000-000000000002", "name": "Wingspan"},
            ]
            sess["cached_entries"] = [
                {"badge_id": "B1", "librarygame_id": "A0000001-0000-4000-A000-000000000001", "id": "e1",
                 "name": "Alice"},
                {"badge_id": "B2", "librarygame_id": "A0000001-0000-4000-A000-000000000001", "id": "e2",
                 "name": "Bob"},
                {"badge_id": "B1", "librarygame_id": "A0000002-0000-4000-A000-000000000002", "id": "e3",
                 "name": "Alice"},
            ]

        resp = self.client.get("/games/players")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Alice", resp.data)
        self.assertIn(b"Bob", resp.data)
        self.assertIn(b"Player Management", resp.data)

    def test_players_shows_game_count(self):
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["library_id"] = "10000001-0000-4000-A000-000000000001"
            sess["convention_id"] = "C0000001-0000-4000-A000-000000000001"
            sess["convention_name"] = "GameFest"
            sess["cached_games"] = [
                {"id": "A0000001-0000-4000-A000-000000000001", "name": "Catan"},
                {"id": "A0000002-0000-4000-A000-000000000002", "name": "Wingspan"},
            ]
            sess["cached_entries"] = [
                {"badge_id": "B1", "librarygame_id": "A0000001-0000-4000-A000-000000000001", "id": "e1",
                 "name": "Alice"},
                {"badge_id": "B1", "librarygame_id": "A0000002-0000-4000-A000-000000000002", "id": "e2",
                 "name": "Alice"},
            ]

        resp = self.client.get("/games/players")
        self.assertEqual(resp.status_code, 200)
        # Alice is in 2 games
        self.assertIn(b"Catan", resp.data)
        self.assertIn(b"Wingspan", resp.data)

    def test_players_shows_removed_badge(self):
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["library_id"] = "10000001-0000-4000-A000-000000000001"
            sess["convention_id"] = "C0000001-0000-4000-A000-000000000001"
            sess["convention_name"] = "GameFest"
            sess["cached_games"] = [
                {"id": "A0000001-0000-4000-A000-000000000001", "name": "Catan"},
            ]
            sess["cached_entries"] = [
                {"badge_id": "B1", "librarygame_id": "A0000001-0000-4000-A000-000000000001", "id": "e1",
                 "name": "Alice"},
            ]
            sess["ejected_entries"] = [["B1", "*"]]

        resp = self.client.get("/games/players")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Removed", resp.data)
        self.assertIn(b"Restore to Drawing", resp.data)

    def test_players_shows_partial_removal(self):
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["library_id"] = "10000001-0000-4000-A000-000000000001"
            sess["convention_id"] = "C0000001-0000-4000-A000-000000000001"
            sess["convention_name"] = "GameFest"
            sess["cached_games"] = [
                {"id": "A0000001-0000-4000-A000-000000000001", "name": "Catan"},
                {"id": "A0000002-0000-4000-A000-000000000002", "name": "Wingspan"},
            ]
            sess["cached_entries"] = [
                {"badge_id": "B1", "librarygame_id": "A0000001-0000-4000-A000-000000000001", "id": "e1",
                 "name": "Alice"},
                {"badge_id": "B1", "librarygame_id": "A0000002-0000-4000-A000-000000000002", "id": "e2",
                 "name": "Alice"},
            ]
            sess["ejected_entries"] = [["B1", "A0000001-0000-4000-A000-000000000001"]]

        resp = self.client.get("/games/players")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Partial", resp.data)

    def test_players_library_only_mode(self):
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["library_id"] = "10000001-0000-4000-A000-000000000001"
            sess["library_name"] = "My Library"
            sess["cached_games"] = [
                {"id": "A0000001-0000-4000-A000-000000000001", "name": "Catan"},
            ]
            sess["cached_entries"] = [
                {"badge_id": "B1", "librarygame_id": "A0000001-0000-4000-A000-000000000001", "id": "e1",
                 "name": "Alice"},
            ]

        resp = self.client.get("/games/players")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Alice", resp.data)
        self.assertIn(b"My Library", resp.data)

    def test_players_empty_list(self):
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["library_id"] = "10000001-0000-4000-A000-000000000001"
            sess["convention_id"] = "C0000001-0000-4000-A000-000000000001"
            sess["convention_name"] = "GameFest"
            sess["cached_games"] = [
                {"id": "A0000001-0000-4000-A000-000000000001", "name": "Catan"},
            ]
            sess["cached_entries"] = []

        resp = self.client.get("/games/players")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"No players found", resp.data)

    def test_players_redirects_without_cache(self):
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["library_id"] = "10000001-0000-4000-A000-000000000001"
            sess["convention_id"] = "C0000001-0000-4000-A000-000000000001"
            sess["convention_name"] = "GameFest"

        resp = self.client.get("/games/players")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/games", resp.headers["Location"])

    @patch("routes.helpers.TTEClient")
    def test_players_has_manage_players_link_from_games(self, MockClient):
        """Games page links to the player management page."""
        mock_instance = MagicMock()
        mock_instance.get_library_games.return_value = [
            {"id": "A0000001-0000-4000-A000-000000000001", "name": "Catan"},
        ]
        mock_instance.get_convention_playtowins.return_value = [
            {"badge_id": "B1", "librarygame_id": "A0000001-0000-4000-A000-000000000001", "id": "e1",
             "name": "Alice"},
        ]
        MockClient.return_value = mock_instance

        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["library_id"] = "10000001-0000-4000-A000-000000000001"
            sess["convention_id"] = "C0000001-0000-4000-A000-000000000001"
            sess["convention_name"] = "GameFest"

        resp = self.client.get("/games")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Manage Players", resp.data)


class TestHealthRoute(unittest.TestCase):

    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def test_health_returns_ok(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"status": "ok"})


class TestIDValidationHelpers(unittest.TestCase):
    """Unit tests for is_valid_tte_id and is_valid_badge_id."""

    def test_valid_tte_id(self):
        from routes.helpers import is_valid_tte_id
        self.assertTrue(is_valid_tte_id("150C7270-24C1-11F1-A9DF-B92257809274"))
        self.assertTrue(is_valid_tte_id("abcdef01-2345-6789-abcd-ef0123456789"))

    def test_invalid_tte_id(self):
        from routes.helpers import is_valid_tte_id
        self.assertFalse(is_valid_tte_id("not-a-uuid"))
        self.assertFalse(is_valid_tte_id(""))
        self.assertFalse(is_valid_tte_id(None))
        self.assertFalse(is_valid_tte_id(123))
        self.assertFalse(is_valid_tte_id("ZZZZZZZZ-ZZZZ-ZZZZ-ZZZZ-ZZZZZZZZZZZZ"))
        self.assertFalse(is_valid_tte_id("150C7270-24C1-11F1-A9DF-B92257809274; DROP TABLE"))

    def test_valid_badge_id(self):
        from routes.helpers import is_valid_badge_id
        self.assertTrue(is_valid_badge_id("B1"))
        self.assertTrue(is_valid_badge_id("badge-123"))
        self.assertTrue(is_valid_badge_id("badge_456"))
        self.assertTrue(is_valid_badge_id("John Smith"))
        self.assertTrue(is_valid_badge_id("O'Brien"))

    def test_invalid_badge_id(self):
        from routes.helpers import is_valid_badge_id
        self.assertFalse(is_valid_badge_id(""))
        self.assertFalse(is_valid_badge_id("   "))
        self.assertFalse(is_valid_badge_id(None))
        self.assertFalse(is_valid_badge_id(123))
        self.assertFalse(is_valid_badge_id("x" * 201))


class TestIDValidationRoutes(unittest.TestCase):
    """Integration tests verifying routes reject invalid IDs."""

    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.app.config["TTE_API_KEY"] = "test-key"
        self.client = self.app.test_client()

    def _login(self):
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["library_id"] = "10000001-0000-4000-A000-000000000001"

    @patch("routes.helpers.TTEClient")
    def test_library_select_rejects_invalid_id(self, MockClient):
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
        resp = self.client.post("/library/select",
                                data={"library_id": "not-valid"})
        self.assertEqual(resp.status_code, 302)

    @patch("routes.helpers.TTEClient")
    def test_convention_select_rejects_invalid_id(self, MockClient):
        with self.client.session_transaction() as sess:
            sess["tte_session_id"] = "session-123"
            sess["library_id"] = "10000001-0000-4000-A000-000000000001"
        resp = self.client.post("/convention/select",
                                data={"convention_id": "<script>alert(1)</script>"})
        self.assertEqual(resp.status_code, 302)

    @patch("routes.helpers.TTEClient")
    def test_toggle_pickup_rejects_invalid_game_id(self, MockClient):
        self._login()
        resp = self.client.post("/drawing/pickup",
                                json={"game_id": "DROP TABLE"})
        self.assertEqual(resp.status_code, 400)

    @patch("routes.helpers.TTEClient")
    def test_get_entrants_rejects_invalid_game_id(self, MockClient):
        self._login()
        resp = self.client.get("/games/entrants/not-a-uuid")
        self.assertEqual(resp.status_code, 400)


if __name__ == "__main__":
    unittest.main()
