from flask import flash, redirect, session, url_for

from tte_client import TTEAPIError, TTEClient


def _get_client():
    """Create a TTEClient with the current user's session."""
    client = TTEClient(api_key_id=session.get("tte_api_key"))
    client.session_id = session.get("tte_session_id")
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
