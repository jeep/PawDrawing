import logging
import re
from functools import wraps

from flask import flash, jsonify, redirect, request, session, url_for

from session_keys import SK
from tte_client import TTEAPIError, TTEClient

logger = logging.getLogger(__name__)

_UUID_RE = re.compile(
    r"^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$"
)
_BADGE_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def is_valid_tte_id(value):
    """Check that a TTE entity ID matches UUID format."""
    return isinstance(value, str) and _UUID_RE.match(value) is not None


def is_valid_badge_id(value):
    """Check that a badge ID is a non-empty alphanumeric string."""
    return isinstance(value, str) and _BADGE_RE.match(value) is not None


def login_required(f=None, *, api=False):
    def decorator(func):
        @wraps(func)
        def decorated(*args, **kwargs):
            if not session.get(SK.TTE_SESSION_ID):
                logger.warning("Unauthenticated request to %s", request.endpoint)
                if api or request.is_json:
                    return jsonify({"error": "Not authenticated"}), 401
                flash("Please log in first.", "error")
                return redirect(url_for("main.login"))
            return func(*args, **kwargs)
        return decorated
    if f is not None:
        return decorator(f)
    return decorator


def _get_client():
    """Create a TTEClient with the current user's session."""
    client = TTEClient(api_key_id=session.get(SK.TTE_API_KEY))
    client.session_id = session.get(SK.TTE_SESSION_ID)
    return client


def _handle_api_error(exc, fallback_url, action="complete this request"):
    """Handle TTEAPIError with appropriate flash message and redirect.

    Clears the Flask session on auth errors (401/403) so the user
    is prompted to log in again.
    """
    if getattr(exc, "status_code", None) in (401, 403):
        logger.warning("API auth error during '%s': session cleared", action)
        session.clear()
        flash("Session expired \u2014 please log in again.", "error")
        return redirect(url_for("main.login"))

    logger.error("API error during '%s': %s", action, exc)
    flash(f"Could not {action}: {exc}", "error")
    return redirect(fallback_url)


def _require_active_drawing():
    """Return drawing_state or a JSON 400 response if no drawing is active."""
    drawing_state = session.get(SK.DRAWING_STATE)
    if not drawing_state:
        return jsonify({"error": "No active drawing"}), 400
    return drawing_state


def _parse_eject_payload():
    """Parse and validate the badge_id/game_id payload for eject endpoints.

    Returns (badge_id, game_id) on success or a (jsonify-response, status)
    tuple on validation failure.
    """
    data = request.get_json(silent=True)
    if not data or "badge_id" not in data:
        return jsonify({"error": "badge_id is required"}), 400

    badge_id = str(data["badge_id"]).strip()
    game_id = str(data.get("game_id", "*")).strip()
    if not badge_id:
        return jsonify({"error": "badge_id is required"}), 400
    if not is_valid_badge_id(badge_id):
        return jsonify({"error": "Invalid badge ID format"}), 400
    if game_id != "*" and not is_valid_tte_id(game_id):
        return jsonify({"error": "Invalid game ID format"}), 400

    return badge_id, game_id


def _handle_api_json_error(exc, action="complete this request"):
    """Handle TTEAPIError for JSON/AJAX endpoints.

    Returns a JSON error response.  Clears the Flask session on auth
    errors (401/403) so subsequent requests prompt a fresh login.
    """
    if getattr(exc, "status_code", None) in (401, 403):
        logger.warning("API auth error during '%s': session cleared", action)
        session.clear()
        return jsonify({"error": "Session expired \u2014 please log in again."}), 401

    logger.error("API error during '%s': %s", action, exc)
    return jsonify({"error": str(exc)}), 502
