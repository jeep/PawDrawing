import re
from functools import wraps

from flask import flash, jsonify, redirect, request, session, url_for

from session_keys import SK
from tte_client import TTEAPIError, TTEClient

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
        session.clear()
        flash("Session expired — please log in again.", "error")
        return redirect(url_for("main.login"))

    flash(f"Could not {action}: {exc}", "error")
    return redirect(fallback_url)
