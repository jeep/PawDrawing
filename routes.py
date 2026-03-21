from flask import Blueprint, flash, jsonify, redirect, render_template, request, session, url_for

from tte_client import TTEAPIError, TTEClient

main_bp = Blueprint("main", __name__)


def _get_client():
    """Create a TTEClient with the current user's session."""
    client = TTEClient()
    client.session_id = session.get("tte_session_id")
    return client


@main_bp.route("/")
def index():
    if session.get("tte_session_id"):
        return redirect(url_for("main.convention_select"))
    return redirect(url_for("main.login"))


@main_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not username or not password:
            flash("Username and password are required.", "error")
            return render_template("login.html"), 400

        client = TTEClient()
        try:
            client.login(username, password)
        except TTEAPIError as exc:
            flash(f"Login failed: {exc}", "error")
            return render_template("login.html"), 401

        session["tte_session_id"] = client.session_id
        session["tte_username"] = username
        return redirect(url_for("main.convention_select"))

    return render_template("login.html")


@main_bp.route("/logout", methods=["POST"])
def logout():
    tte_session_id = session.pop("tte_session_id", None)
    session.pop("tte_username", None)

    if tte_session_id:
        client = TTEClient()
        client.session_id = tte_session_id
        client.logout()

    flash("You have been logged out.", "info")
    return redirect(url_for("main.login"))


@main_bp.route("/convention")
def convention_select():
    if not session.get("tte_session_id"):
        flash("Please log in first.", "error")
        return redirect(url_for("main.login"))
    return render_template("convention_select.html")


@main_bp.route("/convention/search")
def convention_search():
    """AJAX endpoint: search conventions by name."""
    if not session.get("tte_session_id"):
        return jsonify({"error": "Not authenticated"}), 401

    query = request.args.get("q", "").strip()
    if len(query) < 2:
        return jsonify({"results": []})

    client = _get_client()
    try:
        conventions = client.search_conventions(query)
    except TTEAPIError as exc:
        return jsonify({"error": str(exc)}), 502

    results = [{"id": c.get("id"), "name": c.get("name", "Unnamed")} for c in conventions]
    return jsonify({"results": results})


@main_bp.route("/convention/select", methods=["POST"])
def convention_confirm():
    """Fetch convention details and store selection in session."""
    if not session.get("tte_session_id"):
        flash("Please log in first.", "error")
        return redirect(url_for("main.login"))

    convention_id = request.form.get("convention_id", "").strip()
    if not convention_id:
        flash("Please enter or select a convention.", "error")
        return redirect(url_for("main.convention_select"))

    client = _get_client()
    try:
        convention = client.get_convention(convention_id, include_library=True)
    except TTEAPIError as exc:
        flash(f"Could not load convention: {exc}", "error")
        return redirect(url_for("main.convention_select"))

    convention_name = convention.get("name", "Unknown")
    library = convention.get("library")
    if not library:
        flash("No library found for this convention.", "error")
        return redirect(url_for("main.convention_select"))

    library_id = library.get("id")
    library_name = library.get("name", "Unknown")

    session["convention_id"] = convention_id
    session["convention_name"] = convention_name
    session["library_id"] = library_id
    session["library_name"] = library_name

    return render_template(
        "convention_confirm.html",
        convention_name=convention_name,
        library_name=library_name,
    )
