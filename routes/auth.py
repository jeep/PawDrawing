import logging

from flask import flash, jsonify, redirect, render_template, request, session, url_for

from session_keys import SK
from tte_client import TTEAPIError

from . import main_bp
from .helpers import TTEClient

logger = logging.getLogger(__name__)


@main_bp.route("/health")
def health():
    return jsonify(status="ok")


@main_bp.route("/")
def index():
    if session.get(SK.TTE_SESSION_ID):
        return redirect(url_for("main.convention_select"))
    return redirect(url_for("main.login"))


@main_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        api_key = request.form.get("api_key", "").strip()

        if not username or not password or not api_key:
            logger.warning("Login attempt with missing credentials")
            flash("Username, password, and API key are required.", "error")
            return render_template("login.html"), 400

        client = TTEClient(api_key_id=api_key)
        try:
            client.login(username, password)
        except TTEAPIError as exc:
            logger.warning("Login failed for user '%s': %s", username, exc)
            flash(f"Login failed: {exc}", "error")
            return render_template("login.html"), 401

        logger.info("User '%s' logged in (user_id=%s)", username, client.user_id)
        session[SK.TTE_SESSION_ID] = client.session_id
        session[SK.TTE_USERNAME] = username
        session[SK.TTE_USER_ID] = client.user_id
        session[SK.TTE_API_KEY] = api_key
        return redirect(url_for("main.convention_select"))

    return render_template("login.html")


@main_bp.route("/logout", methods=["POST"])
def logout():
    logger.info("User '%s' logged out", session.get(SK.TTE_USERNAME, "unknown"))
    tte_session_id = session.pop(SK.TTE_SESSION_ID, None)
    tte_api_key = session.pop(SK.TTE_API_KEY, None)
    session.pop(SK.TTE_USERNAME, None)

    # Only call TTE logout if we have both session ID and API key
    if tte_session_id and tte_api_key:
        client = TTEClient(api_key_id=tte_api_key)
        client.session_id = tte_session_id
        client.logout()

    flash("You have been logged out.", "info")
    return redirect(url_for("main.login"))
