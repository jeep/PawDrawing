"""Library Management volunteer auth routes."""

from flask import flash, redirect, render_template, request, session, url_for

from session_keys import SK
from tte_client import TTEAPIError, TTEClient

from . import library_bp
from routes.helpers import login_required


@library_bp.route("/volunteer-login", methods=["GET", "POST"])
def volunteer_login():
    library_id = session.get(SK.LIBRARY_ID)
    library_name = session.get(SK.LIBRARY_NAME)
    if not library_id:
        return redirect(url_for("main.login"))

    if request.method == "GET":
        return render_template("library/volunteer_login.html", library_name=library_name)

    username = (request.form.get("username") or "").strip()
    password = (request.form.get("password") or "").strip()
    api_key = (request.form.get("api_key") or "").strip()

    if not username or not password or not api_key:
        return "Missing credentials", 400

    try:
        client = TTEClient(api_key_id=api_key)
        client.login(username, password)
    except TTEAPIError:
        return "Login failed", 401

    try:
        privileges = client.get_library_privileges(library_id)
    except TTEAPIError:
        return "Could not verify checkout privilege", 403

    user_id = getattr(client, "user_id", None)
    can_checkout = any(
        str(p.get("user_id")) == str(user_id) and bool(p.get("checkouts"))
        for p in (privileges or [])
    )
    if not can_checkout:
        return "Account lacks checkout privilege", 403

    session[SK.TTE_SESSION_ID] = client.session_id
    session[SK.TTE_USERNAME] = username
    session[SK.TTE_USER_ID] = user_id
    session[SK.TTE_API_KEY] = api_key
    session[SK.AUTH_MODE] = "volunteer"
    session[SK.VOLUNTEER_NAME] = username
    session[SK.HAS_CHECKOUT_PRIVILEGE] = True
    session[SK.APP_MODE] = "library"

    flash("Volunteer logged in.", "success")
    return redirect(url_for("library.dashboard"))


@library_bp.route("/volunteer-logout", methods=["POST"])
@login_required
def volunteer_logout():
    # Preserve selected library context and caches for next volunteer.
    keep = {
        SK.LIBRARY_ID: session.get(SK.LIBRARY_ID),
        SK.LIBRARY_NAME: session.get(SK.LIBRARY_NAME),
        SK.CONVENTION_ID: session.get(SK.CONVENTION_ID),
        SK.CONVENTION_NAME: session.get(SK.CONVENTION_NAME),
        SK.CACHED_GAMES: session.get(SK.CACHED_GAMES),
        SK.CACHED_ENTRIES: session.get(SK.CACHED_ENTRIES),
        SK.CHECKOUT_MAP: session.get(SK.CHECKOUT_MAP),
        SK.NOTIFICATIONS: session.get(SK.NOTIFICATIONS),
        SK.PERSON_CACHE: session.get(SK.PERSON_CACHE),
    }

    session.clear()
    for key, value in keep.items():
        if value is not None:
            session[key] = value

    return redirect(url_for("library.volunteer_login"))
