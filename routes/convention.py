from flask import flash, jsonify, redirect, render_template, request, session, url_for

from tte_client import TTEAPIError

from . import main_bp
from .helpers import _get_client, _handle_api_error, login_required


@main_bp.route("/convention")
@login_required
def convention_select():
    return render_template("convention_select.html")


@main_bp.route("/library/browse")
@login_required(api=True)
def library_browse():
    """AJAX endpoint: list libraries owned by the logged-in user."""
    user_id = session.get("tte_user_id")
    if not user_id:
        return jsonify({"error": "No user ID available"}), 400

    client = _get_client()
    try:
        libraries = client.get_user_libraries(user_id)
    except TTEAPIError as exc:
        if getattr(exc, 'status_code', None) in (401, 403):
            session.clear()
            return jsonify({"error": "Session expired \u2014 please log in again."}), 401
        return jsonify({"error": str(exc)}), 502

    results = [{"id": lib.get("id"), "name": lib.get("name", "Unnamed")} for lib in libraries]
    return jsonify({"results": results})


@main_bp.route("/library/select", methods=["POST"])
@login_required
def library_select_route():
    """Fetch library details and store in session (no convention)."""
    library_id = request.form.get("library_id", "").strip()
    if not library_id:
        flash("Please enter or select a library.", "error")
        return redirect(url_for("main.convention_select"))

    client = _get_client()
    try:
        library = client.get_library(library_id)
    except TTEAPIError as exc:
        return _handle_api_error(exc, url_for("main.convention_select"), "load library")

    library_name = library.get("name", "Unknown")

    session.pop("convention_id", None)
    session.pop("convention_name", None)
    session["library_id"] = library_id
    session["library_name"] = library_name
    session.pop("ejected_entries", None)

    return redirect(url_for("main.library_confirm"))


@main_bp.route("/library/confirm")
@login_required
def library_confirm():
    """Show library confirmation page (GET-safe after PRG redirect)."""
    library_name = session.get("library_name")
    if not library_name:
        flash("Please select a library.", "error")
        return redirect(url_for("main.convention_select"))
    return render_template("library_confirm.html", library_name=library_name)


@main_bp.route("/convention/search")
@login_required(api=True)
def convention_search():
    """AJAX endpoint: search conventions by name."""
    query = request.args.get("q", "").strip()
    if len(query) < 2:
        return jsonify({"results": []})

    client = _get_client()
    try:
        conventions = client.search_conventions(query)
    except TTEAPIError as exc:
        if getattr(exc, 'status_code', None) in (401, 403):
            session.clear()
            return jsonify({"error": "Session expired — please log in again."}), 401
        return jsonify({"error": str(exc)}), 502

    results = [{"id": c.get("id"), "name": c.get("name", "Unnamed")} for c in conventions]
    return jsonify({"results": results})


@main_bp.route("/convention/select", methods=["POST"])
@login_required
def convention_select_route():
    """Fetch convention details and store selection in session."""
    convention_id = request.form.get("convention_id", "").strip()
    if not convention_id:
        flash("Please enter or select a convention.", "error")
        return redirect(url_for("main.convention_select"))

    client = _get_client()
    try:
        convention = client.get_convention(convention_id, include_library=True)
    except TTEAPIError as exc:
        return _handle_api_error(exc, url_for("main.convention_select"), "load convention")

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
    session.pop("ejected_entries", None)

    return redirect(url_for("main.convention_confirm"))


@main_bp.route("/convention/confirm")
@login_required
def convention_confirm():
    """Show convention confirmation page (GET-safe after PRG redirect)."""
    convention_name = session.get("convention_name")
    library_name = session.get("library_name")
    if not convention_name or not library_name:
        flash("Please select a convention.", "error")
        return redirect(url_for("main.convention_select"))
    return render_template(
        "convention_confirm.html",
        convention_name=convention_name,
        library_name=library_name,
    )
