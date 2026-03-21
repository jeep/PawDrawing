"""Unit tests for the TTE API client."""

import time
import unittest
from unittest.mock import MagicMock, patch

import requests

from app import create_app
from tte_client import TTEAPIError, TTEClient


class TTEClientTestBase(unittest.TestCase):
    """Base class that provides a Flask app context for tests."""

    def setUp(self):
        self.app = create_app()
        self.app.config["TTE_API_KEY"] = "test-api-key"
        self.app.config["TTE_BASE_URL"] = "https://tabletop.events/api"
        self.ctx = self.app.app_context()
        self.ctx.push()
        self.client = TTEClient()

    def tearDown(self):
        self.ctx.pop()


class TestRateLimiting(TTEClientTestBase):

    @patch("tte_client.requests.request")
    @patch("tte_client.time.sleep")
    def test_throttle_enforces_one_second_gap(self, mock_sleep, mock_request):
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"result": {"id": "1"}}
        mock_request.return_value = mock_resp

        # First request — no sleep needed
        self.client._request("GET", "/test")
        # Second request — should trigger sleep
        self.client._request("GET", "/test")

        mock_sleep.assert_called()
        delay = mock_sleep.call_args[0][0]
        self.assertGreater(delay, 0)
        self.assertLessEqual(delay, 1.0)


class TestAuthentication(TTEClientTestBase):

    @patch("tte_client.requests.request")
    def test_login_stores_session_id(self, mock_request):
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"result": {"id": "session-abc-123"}}
        mock_request.return_value = mock_resp

        self.client.login("user", "pass")

        self.assertEqual(self.client.session_id, "session-abc-123")
        self.assertTrue(self.client.is_authenticated)

        # Verify the request was made with correct body
        call_kwargs = mock_request.call_args
        self.assertEqual(call_kwargs.kwargs["json"]["username"], "user")
        self.assertEqual(call_kwargs.kwargs["json"]["password"], "pass")
        self.assertEqual(call_kwargs.kwargs["json"]["api_key_id"], "test-api-key")

    @patch("tte_client.requests.request")
    def test_login_missing_session_id_raises(self, mock_request):
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"result": {}}
        mock_request.return_value = mock_resp

        with self.assertRaises(TTEAPIError) as ctx:
            self.client.login("user", "pass")
        self.assertIn("no session ID", str(ctx.exception))

    @patch("tte_client.requests.request")
    def test_logout_clears_session_id(self, mock_request):
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"result": {}}
        mock_request.return_value = mock_resp

        self.client.session_id = "session-abc-123"
        self.client.logout()

        self.assertIsNone(self.client.session_id)
        self.assertFalse(self.client.is_authenticated)

    def test_logout_without_session_is_safe(self):
        self.client.session_id = None
        self.client.logout()  # Should not raise
        self.assertIsNone(self.client.session_id)

    @patch("tte_client.requests.request")
    def test_session_id_sent_as_query_param(self, mock_request):
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"result": {"name": "test"}}
        mock_request.return_value = mock_resp

        self.client.session_id = "session-xyz"
        self.client._request("GET", "/convention/123")

        call_kwargs = mock_request.call_args
        self.assertIn("session_id", call_kwargs.kwargs["params"])
        self.assertEqual(call_kwargs.kwargs["params"]["session_id"], "session-xyz")


class TestErrorHandling(TTEClientTestBase):

    @patch("tte_client.requests.request")
    def test_401_clears_session_and_raises(self, mock_request):
        mock_resp = MagicMock()
        mock_resp.ok = False
        mock_resp.status_code = 401
        mock_request.return_value = mock_resp

        self.client.session_id = "old-session"

        with self.assertRaises(TTEAPIError) as ctx:
            self.client._request("GET", "/test")
        self.assertIn("expired", str(ctx.exception).lower())
        self.assertIsNone(self.client.session_id)

    @patch("tte_client.requests.request")
    def test_403_clears_session_and_raises(self, mock_request):
        mock_resp = MagicMock()
        mock_resp.ok = False
        mock_resp.status_code = 403
        mock_request.return_value = mock_resp

        self.client.session_id = "old-session"

        with self.assertRaises(TTEAPIError) as ctx:
            self.client._request("GET", "/test")
        self.assertIsNone(self.client.session_id)

    @patch("tte_client.requests.request")
    def test_500_raises_api_error(self, mock_request):
        mock_resp = MagicMock()
        mock_resp.ok = False
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"
        mock_request.return_value = mock_resp

        with self.assertRaises(TTEAPIError) as ctx:
            self.client._request("GET", "/test")
        self.assertEqual(ctx.exception.status_code, 500)

    @patch("tte_client.requests.request")
    def test_invalid_json_raises(self, mock_request):
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.status_code = 200
        mock_resp.json.side_effect = ValueError("bad json")
        mock_request.return_value = mock_resp

        with self.assertRaises(TTEAPIError) as ctx:
            self.client._request("GET", "/test")
        self.assertIn("Invalid JSON", str(ctx.exception))

    @patch("tte_client.requests.request")
    def test_missing_result_key_raises(self, mock_request):
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"error": "something"}
        mock_request.return_value = mock_resp

        with self.assertRaises(TTEAPIError) as ctx:
            self.client._request("GET", "/test")
        self.assertIn("missing 'result'", str(ctx.exception))

    @patch("tte_client.requests.request", side_effect=requests.ConnectionError("Connection refused"))
    def test_network_error_raises(self, mock_request):
        with self.assertRaises(TTEAPIError) as ctx:
            self.client._request("GET", "/test")
        self.assertIn("Network error", str(ctx.exception))


class TestPagination(TTEClientTestBase):

    @patch("tte_client.requests.request")
    def test_single_page(self, mock_request):
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "result": {
                "paging": {"total_pages": 1},
                "items": [{"id": "a"}, {"id": "b"}],
            }
        }
        mock_request.return_value = mock_resp

        items = self.client._get_all_pages("/library/1/games")

        self.assertEqual(len(items), 2)
        self.assertEqual(mock_request.call_count, 1)

    @patch("tte_client.requests.request")
    def test_multiple_pages(self, mock_request):
        page1_resp = MagicMock()
        page1_resp.ok = True
        page1_resp.status_code = 200
        page1_resp.json.return_value = {
            "result": {
                "paging": {"total_pages": 3},
                "items": [{"id": "1"}, {"id": "2"}],
            }
        }
        page2_resp = MagicMock()
        page2_resp.ok = True
        page2_resp.status_code = 200
        page2_resp.json.return_value = {
            "result": {
                "paging": {"total_pages": 3},
                "items": [{"id": "3"}, {"id": "4"}],
            }
        }
        page3_resp = MagicMock()
        page3_resp.ok = True
        page3_resp.status_code = 200
        page3_resp.json.return_value = {
            "result": {
                "paging": {"total_pages": 3},
                "items": [{"id": "5"}],
            }
        }
        mock_request.side_effect = [page1_resp, page2_resp, page3_resp]

        items = self.client._get_all_pages("/library/1/playtowins")

        self.assertEqual(len(items), 5)
        self.assertEqual(mock_request.call_count, 3)

    @patch("tte_client.requests.request")
    def test_empty_result(self, mock_request):
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "result": {
                "paging": {"total_pages": 1},
                "items": [],
            }
        }
        mock_request.return_value = mock_resp

        items = self.client._get_all_pages("/library/1/games")
        self.assertEqual(items, [])


class TestEndpoints(TTEClientTestBase):

    @patch("tte_client.requests.request")
    def test_get_convention(self, mock_request):
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"result": {"id": "conv-1", "name": "ConFest"}}
        mock_request.return_value = mock_resp

        result = self.client.get_convention("conv-1")
        self.assertEqual(result["name"], "ConFest")

    @patch("tte_client.requests.request")
    def test_get_convention_with_library(self, mock_request):
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"result": {"id": "conv-1", "library": {"id": "lib-1"}}}
        mock_request.return_value = mock_resp

        result = self.client.get_convention("conv-1", include_library=True)
        call_kwargs = mock_request.call_args
        self.assertEqual(call_kwargs.kwargs["params"]["_include_related_objects"], "library")

    @patch("tte_client.requests.request")
    def test_update_playtowin_win(self, mock_request):
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"result": {"id": "ptw-1", "win": 1}}
        mock_request.return_value = mock_resp

        result = self.client.update_playtowin("ptw-1", {"win": 1})

        self.assertEqual(result["win"], 1)
        call_args = mock_request.call_args
        self.assertEqual(call_args[0][0], "PUT")


if __name__ == "__main__":
    unittest.main()
