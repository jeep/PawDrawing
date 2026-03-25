"""Library Management volunteer login and privilege routes (FR-AUTH-04/05)."""

import logging

from flask import flash, jsonify, redirect, render_template, request, session, url_for

from session_keys import SK
from tte_client import TTEAPIError, TTEClient

from . import library_bp
from routes.helpers import login_required

logger = logging.getLogger(__name__)


@library_bp.route("/volunteer-login", methods=["GET", "POST"])
def volunteer_login():
    """Volunteer login page — authenticates with volunteer's own TTE credentials.

    Requires a library to already be selected (owner must set up session first).
    """
    library_id = session.get(SK.LIBRARY_ID)
    library_name = session.get(SK.LIBRARY_NAME)

    if not library_id:
        flash("A library must be selected before volunteers can log in.", "error")
        return redirect(url_for("main.login"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        api_key = request.form.get("api_key", "").strip()

        if not username or not password or not api_key:
            flash("Username, password, and API key are required.", "error")
            return render_template(
                "library/volunteer_login.html",
                library_name=library_name,
            ), 400

        # Authenticate the volunteer against TTE
        client = TTEClient(api_key_id=api_key)
        try:
            client.login(username, password)
        except TTEAPIError as exc:
            logger.warning("Volunteer login failed for '%s': %s", username, exc)
            flash(f"Login failed: {exc}", "error")
            return render_template(
                "library/volunteer_login.html",
                library_name=library_name,
            ), 401

        # Verify the volunteer has checkout privilege on this library
        has_checkout = False
        try:
            privileges = client.get_library_privileges(library_id)
            for priv in privileges:
                if priv.get("user_id") == client.user_id:
                    has_checkout = bool(priv.get("checkouts"))
                    break
        except TTEAPIError as exc:
            logger.warning(
                "Could not verify privileges for volunteer '%s': %s",
                username, exc,
            )
            flash(
                "Could not verify your library privileges. "
                "Please ask the library owner to grant you access.",
                "error",
            )
            # Log the volunteer out of TTE since we can't verify
            try:
                client.logout()
            except TTEAPIError:
                pass
            return render_template(
                "library/volunteer_login.html",
                library_name=library_name,
            ), 403

        if not has_checkout:
            logger.warning(
                "Volunteer '%s' lacks checkout privilege on library %s",
                username, library_id,
            )
            flash(
                "Your account does not have checkout privileges on this library. "
                "Please ask the library owner to grant you access.",
                "error",
            )
            try:
                client.logout()
            except TTEAPIError:
                pass
            return render_template(
                "library/volunteer_login.html",
                library_name=library_name,
            ), 403

        # Store volunteer session — replaces owner TTE session for this browser
        session[SK.TTE_SESSION_ID] = client.session_id
        session[SK.TTE_USERNAME] = username
        session[SK.TTE_USER_ID] = client.user_id
        session[SK.TTE_API_KEY] = api_key
        session[SK.AUTH_MODE] = "volunteer"
        session[SK.VOLUNTEER_NAME] = username
        session[SK.HAS_CHECKOUT_PRIVILEGE] = has_checkout
        session[SK.APP_MODE] = "library"

        logger.info(
            "Volunteer '%s' logged in for library '%s'",
            username, library_name,
        )
        flash(f"Welcome, {username}! You are logged in as a volunteer.", "success")
        return redirect(url_for("library.dashboard"))

    return render_template(
        "library/volunteer_login.html",
        library_name=library_name,
    )


@library_bp.route("/volunteer-logout", methods=["POST"])
@login_required
def volunteer_logout():
    """Log out a volunteer — returns to the volunteer login page.

    Does NOT destroy the underlying library session (owner's library selection
    stays intact so other volunteers can still log in).
    """
    username = session.get(SK.TTE_USERNAME, "unknown")
    tte_session_id = session.get(SK.TTE_SESSION_ID)
    tte_api_key = session.get(SK.TTE_API_KEY)

    # Log out of TTE
    if tte_session_id:
        client = TTEClient(api_key_id=tte_api_key)
        client.session_id = tte_session_id
        try:
            client.logout()
        except TTEAPIError:
            pass

    # Clear volunteer-specific keys but preserve library selection
    library_id = session.get(SK.LIBRARY_ID)
    library_name = session.get(SK.LIBRARY_NAME)
    convention_id = session.get(SK.CONVENTION_ID)
    convention_name = session.get(SK.CONVENTION_NAME)
    cached_games = session.get(SK.CACHED_GAMES)

    session.clear()

    # Restore library context so next volunteer can log in
    if library_id:
        session[SK.LIBRARY_ID] = library_id
    if library_name:
        session[SK.LIBRARY_NAME] = library_name
    if convention_id:
        session[SK.CONVENTION_ID] = convention_id
    if convention_name:
        session[SK.CONVENTION_NAME] = convention_name
    if cached_games is not None:
        session[SK.CACHED_GAMES] = cached_games

    logger.info("Volunteer '%s' logged out", username)
    flash("You have been logged out.", "info")
    return redirect(url_for("library.volunteer_login"))
