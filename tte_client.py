"""TTE (tabletop.events) API client with session management, rate limiting, and pagination."""

import logging
import time

import requests

logger = logging.getLogger(__name__)
from flask import current_app, has_request_context, session as flask_session


class TTEAPIError(Exception):
    """Raised when the TTE API returns an error or unexpected response."""

    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code


class TTETimeoutError(TTEAPIError):
    """Raised when a TTE API request times out."""

    def __init__(self):
        super().__init__(
            "Request timed out. The server may be busy — please try again."
        )


class TTEClient:
    """Client for the tabletop.events API.

    Handles authentication, rate limiting (1 req/sec), automatic pagination,
    and error handling. Session ID is stored server-side only.
    """

    def __init__(self, base_url=None, api_key_id=None):
        self.base_url = (base_url or current_app.config["TTE_BASE_URL"]).rstrip("/")
        self.api_key_id = api_key_id or current_app.config["TTE_API_KEY"]
        self.session_id = None
        self.user_id = None
        self._last_request_time = 0.0
        self._http = requests.Session()

    # ── Rate limiting ──────────────────────────────────────────────────

    def _throttle(self):
        """Enforce minimum 1-second gap between requests.

        When called inside a Flask request, stores the timestamp in the
        Flask session so the throttle persists across TTEClient instances.
        Falls back to instance-level tracking outside a request context.
        Uses time.time() (wall-clock) for cross-process compatibility.
        """
        if has_request_context():
            last = flask_session.get("_tte_last_request", 0.0)
            elapsed = time.time() - last
            if elapsed < 1.0:
                time.sleep(1.0 - elapsed)
            flask_session["_tte_last_request"] = time.time()
        else:
            elapsed = time.time() - self._last_request_time
            if elapsed < 1.0:
                time.sleep(1.0 - elapsed)
            self._last_request_time = time.time()

    # ── Low-level request ──────────────────────────────────────────────

    def _request(self, method, path, params=None, json_body=None):
        """Make a rate-limited request to the TTE API.

        Returns the parsed 'result' dict from the response.
        Raises TTEAPIError on failure.
        """
        self._throttle()

        url = f"{self.base_url}/{path.lstrip('/')}"

        if params is None:
            params = {}
        if self.session_id:
            params["session_id"] = self.session_id

        try:
            resp = self._http.request(
                method,
                url,
                params=params,
                json=json_body,
                timeout=30,
            )
        except requests.Timeout as exc:
            logger.warning("Request timed out: %s %s", method, url)
            raise TTETimeoutError() from exc
        except requests.RequestException as exc:
            logger.error("Network error on %s %s: %s", method, url, exc)
            raise TTEAPIError(f"Network error: {exc}") from exc

        if resp.status_code in (401, 403):
            logger.warning("API auth failure on %s %s (status=%d)", method, url, resp.status_code)
            self.session_id = None
            raise TTEAPIError("Session expired or unauthorized. Please log in again.", resp.status_code)

        if not resp.ok:
            logger.error("API error %d on %s %s: %s", resp.status_code, method, url, resp.text[:200])
            raise TTEAPIError(
                f"API error {resp.status_code}: {resp.text[:200]}",
                resp.status_code,
            )

        try:
            data = resp.json()
        except ValueError as exc:
            raise TTEAPIError("Invalid JSON in API response") from exc

        if "result" not in data:
            raise TTEAPIError("Unexpected API response format (missing 'result')")

        return data["result"]

    # ── Pagination ─────────────────────────────────────────────────────

    def _get_all_pages(self, path, params=None):
        """Fetch all pages from a paginated endpoint. Returns a flat list of items."""
        if params is None:
            params = {}
        params["_items_per_page"] = 100
        params["_page_number"] = 1

        all_items = []

        while True:
            result = self._request("GET", path, params=dict(params))
            items = result.get("items", [])
            all_items.extend(items)

            paging = result.get("paging", {})
            total_pages = int(paging.get("total_pages", 1))

            if params["_page_number"] >= total_pages:
                break
            params["_page_number"] += 1

        return all_items

    # ── Authentication ─────────────────────────────────────────────────

    def login(self, username, password):
        """Create a session with the TTE API. Stores session_id and user_id internally."""
        result = self._request("POST", "/session", json_body={
            "username": username,
            "password": password,
            "api_key_id": self.api_key_id,
        })
        self.session_id = result.get("id")
        if not self.session_id:
            logger.error("TTE login returned no session ID")
            raise TTEAPIError("Login succeeded but no session ID returned")
        self.user_id = result.get("user_id")
        logger.info("TTE login successful (user_id=%s)", self.user_id)
        return result

    def logout(self):
        """Delete the current session."""
        if not self.session_id:
            return
        try:
            self._request("DELETE", f"/session/{self.session_id}")
        except TTEAPIError as exc:
            logger.warning("Logout failed for session %s: %s", self.session_id, exc)
        finally:
            self.session_id = None

    @property
    def is_authenticated(self):
        return self.session_id is not None

    # ── Convention ─────────────────────────────────────────────────────

    def search_conventions(self, query):
        """Search conventions by name. Returns a list of matching conventions."""
        return self._get_all_pages("/convention", params={"query": query})

    def get_convention(self, convention_id, include_library=False):
        """Fetch a convention by ID."""
        params = {}
        if include_library:
            params["_include_related_objects"] = "library"
        return self._request("GET", f"/convention/{convention_id}", params=params)

    # ── User ─────────────────────────────────────────────────────────

    def get_user_libraries(self, user_id):
        """Fetch all libraries owned by a user."""
        return self._get_all_pages(f"/user/{user_id}/libraries")

    # ── Library ────────────────────────────────────────────────────────

    def get_library(self, library_id):
        """Fetch a library by ID."""
        return self._request("GET", f"/library/{library_id}")

    def get_library_games(self, library_id, play_to_win_only=True):
        """Fetch all games in a library. Returns flat list across all pages."""
        params = {}
        if play_to_win_only:
            params["is_play_to_win"] = 1
        return self._get_all_pages(f"/library/{library_id}/games", params)

    def get_library_playtowins(self, library_id):
        """Fetch all PlayToWin entries for a library."""
        return self._get_all_pages(f"/library/{library_id}/playtowins")

    # ── LibraryGame ────────────────────────────────────────────────────

    def get_library_game(self, game_id):
        """Fetch a specific library game."""
        return self._request("GET", f"/librarygame/{game_id}")

    def get_library_game_playtowins(self, game_id):
        """Fetch all PlayToWin entries for a specific game."""
        return self._get_all_pages(f"/librarygame/{game_id}/playtowins")

    # ── PlayToWin ──────────────────────────────────────────────────────

    def get_convention_playtowins(self, convention_id):
        """Fetch all PlayToWin entries for a convention."""
        return self._get_all_pages(f"/convention/{convention_id}/playtowins")

    def get_playtowin(self, playtowin_id):
        """Fetch a specific PlayToWin entry."""
        return self._request("GET", f"/playtowin/{playtowin_id}")

    def update_playtowin(self, playtowin_id, data):
        """Update a PlayToWin entry (e.g., set win flag)."""
        return self._request("PUT", f"/playtowin/{playtowin_id}", json_body=data)

    # ── Library Management: Checkouts ──────────────────────────────────

    def get_library_checkouts(self, library_id, checked_in=None):
        """Fetch checkouts for a library. Filter by checked-in status if provided."""
        params = {}
        if checked_in is not None:
            params["is_checked_in"] = 1 if checked_in else 0
        return self._get_all_pages(f"/library/{library_id}/checkouts", params)

    def get_library_game_checkouts(self, game_id, checked_in=None):
        """Fetch checkouts for a specific game."""
        params = {}
        if checked_in is not None:
            params["is_checked_in"] = 1 if checked_in else 0
        return self._get_all_pages(f"/librarygame/{game_id}/checkouts", params)

    def search_checkouts(self, query):
        """Search checkouts across libraries by renter name."""
        return self._get_all_pages("/librarygamecheckout", params={"query": query})

    def create_checkout(self, library_id, game_id, renter_name,
                        convention_id=None, badge_id=None):
        """Create a new game checkout."""
        body = {
            "library_id": library_id,
            "librarygame_id": game_id,
            "renter_name": renter_name,
        }
        if convention_id:
            body["convention_id"] = convention_id
        if badge_id:
            body["badge_id"] = badge_id
        return self._request("POST", "/librarygamecheckout", json_body=body)

    def checkin_game(self, checkout_id):
        """Check in a game (return to library)."""
        return self._request("POST", f"/librarygamecheckout/{checkout_id}/checkin")

    def get_checkout(self, checkout_id):
        """Fetch a specific checkout."""
        return self._request("GET", f"/librarygamecheckout/{checkout_id}")

    def delete_checkout(self, checkout_id):
        """Delete a checkout."""
        return self._request("DELETE", f"/librarygamecheckout/{checkout_id}")

    # ── Library Management: P2W Entries ────────────────────────────────

    def create_playtowin_entry(self, library_id, game_id, renter_name,
                               convention_id=None, badge_id=None):
        """Create a Play-to-Win drawing entry."""
        body = {
            "library_id": library_id,
            "librarygame_id": game_id,
            "name": renter_name,
        }
        if convention_id:
            body["convention_id"] = convention_id
        if badge_id:
            body["badge_id"] = badge_id
        return self._request("POST", "/playtowin", json_body=body)

    # ── Library Management: Game Updates ───────────────────────────────

    def update_library_game(self, game_id, data):
        """Update a library game (e.g., set is_play_to_win)."""
        return self._request("PUT", f"/librarygame/{game_id}", json_body=data)

    # ── Library Management: Badge Lookup ───────────────────────────────

    def search_badges(self, convention_id, query, query_field=None):
        """Search convention badges by name, email, or badge number."""
        params = {"query": query}
        if query_field:
            params["query_field"] = query_field
        return self._get_all_pages(
            f"/convention/{convention_id}/badges", params
        )

    # ── Library Management: Privileges ─────────────────────────────────

    def get_library_privileges(self, library_id):
        """Fetch privileges for a library."""
        return self._get_all_pages(f"/library/{library_id}/privileges")

    def create_library_privilege(self, library_id, user_id):
        """Grant a user privilege on a library."""
        body = {"library_id": library_id, "user_id": user_id}
        return self._request("POST", "/libraryprivilege", json_body=body)

    # ── Library Management: Checkout Time Reset ────────────────────────

    def reset_checkout_time(self, checkout_id):
        """Reset checkout time (re-timestamps the checkout)."""
        return self._request(
            "POST", f"/librarygamecheckout/{checkout_id}/reset-checkout-time"
        )
