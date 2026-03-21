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


if __name__ == "__main__":
    unittest.main()
