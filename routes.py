from flask import Blueprint, flash, jsonify, redirect, render_template, request, session, url_for

from data_processing import group_entries_by_game, process_entries
from drawing import (
    advance_winner,
    apply_resolution,
    detect_conflicts,
    get_current_winners,
    run_drawing,
)
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


@main_bp.route("/games")
def games():
    """Load P2W games and entries, process, and display."""
    if not session.get("tte_session_id"):
        flash("Please log in first.", "error")
        return redirect(url_for("main.login"))

    library_id = session.get("library_id")
    convention_id = session.get("convention_id")
    if not library_id:
        flash("Please select a convention first.", "error")
        return redirect(url_for("main.convention_select"))

    client = _get_client()

    try:
        all_games = client.get_library_games(library_id, play_to_win_only=True)
    except TTEAPIError as exc:
        flash(f"Could not load games: {exc}", "error")
        return redirect(url_for("main.convention_select"))

    try:
        if convention_id:
            raw_entries = client.get_convention_playtowins(convention_id)
        else:
            raw_entries = client.get_library_playtowins(library_id)
    except TTEAPIError as exc:
        flash(f"Could not load entries: {exc}", "error")
        return redirect(url_for("main.convention_select"))

    entries = process_entries(raw_entries)
    game_data = group_entries_by_game(entries, all_games)
    game_data.sort(key=lambda g: g["game"].get("name", ""))

    premium_games = session.get("premium_games", [])

    return render_template(
        "games.html",
        game_data=game_data,
        total_games=len(all_games),
        total_entries=len(entries),
        convention_name=session.get("convention_name", ""),
        premium_games=premium_games,
    )


@main_bp.route("/games/premium", methods=["POST"])
def set_premium_games():
    """AJAX endpoint: save premium game designations to session."""
    if not session.get("tte_session_id"):
        return jsonify({"error": "Not authenticated"}), 401

    data = request.get_json(silent=True)
    if data is None or "premium_games" not in data:
        return jsonify({"error": "Invalid request"}), 400

    game_ids = data["premium_games"]
    if not isinstance(game_ids, list):
        return jsonify({"error": "premium_games must be a list"}), 400

    session["premium_games"] = game_ids
    return jsonify({"ok": True, "count": len(game_ids)})


@main_bp.route("/drawing", methods=["POST"])
def run_drawing_route():
    """Execute the drawing algorithm and display results."""
    if not session.get("tte_session_id"):
        flash("Please log in first.", "error")
        return redirect(url_for("main.login"))

    library_id = session.get("library_id")
    convention_id = session.get("convention_id")
    if not library_id:
        flash("Please select a convention first.", "error")
        return redirect(url_for("main.convention_select"))

    client = _get_client()

    try:
        all_games = client.get_library_games(library_id, play_to_win_only=True)
    except TTEAPIError as exc:
        flash(f"Could not load games: {exc}", "error")
        return redirect(url_for("main.games"))

    try:
        if convention_id:
            raw_entries = client.get_convention_playtowins(convention_id)
        else:
            raw_entries = client.get_library_playtowins(library_id)
    except TTEAPIError as exc:
        flash(f"Could not load entries: {exc}", "error")
        return redirect(url_for("main.games"))

    entries = process_entries(raw_entries)
    game_data = group_entries_by_game(entries, all_games)
    premium_games = session.get("premium_games", [])

    drawing_state, conflicts, auto_resolved = run_drawing(game_data, premium_games)

    # Store drawing state in session for conflict resolution
    session["drawing_state"] = drawing_state
    session["auto_resolved"] = auto_resolved

    winners = get_current_winners(drawing_state)

    # Build display-friendly results
    results = []
    for item in drawing_state:
        game = item["game"]
        game_id = game["id"]
        winner = winners.get(game_id)
        results.append({
            "game_name": game.get("name", "Unknown"),
            "game_id": game_id,
            "is_premium": game_id in premium_games,
            "winner_name": winner.get("name", "Unknown") if winner else None,
            "winner_badge": winner.get("badge_id", "") if winner else None,
            "total_entries": len(item["shuffled"]),
            "winner_index": item["winner_index"],
        })

    results.sort(key=lambda r: r["game_name"])

    return render_template(
        "drawing_results.html",
        results=results,
        conflicts=conflicts,
        auto_resolved=auto_resolved,
        convention_name=session.get("convention_name", ""),
    )


@main_bp.route("/drawing/resolve", methods=["POST"])
def resolve_conflicts():
    """Apply admin conflict resolution choices."""
    if not session.get("tte_session_id"):
        return jsonify({"error": "Not authenticated"}), 401

    drawing_state = session.get("drawing_state")
    if not drawing_state:
        return jsonify({"error": "No active drawing"}), 400

    data = request.get_json(silent=True)
    if not data or "resolutions" not in data:
        return jsonify({"error": "Invalid request"}), 400

    # resolutions: list of {badge_id: str, keep_game_id: str}
    keep_map = {}
    for res in data["resolutions"]:
        badge_id = res.get("badge_id")
        keep_game_id = res.get("keep_game_id")
        if badge_id and keep_game_id:
            keep_map[badge_id] = keep_game_id

    premium_games = set(session.get("premium_games", []))
    apply_resolution(drawing_state, keep_map, premium_games)

    # Check for new conflicts from cascading
    new_conflicts = detect_conflicts(drawing_state)

    session["drawing_state"] = drawing_state

    winners = get_current_winners(drawing_state)

    results = []
    for item in drawing_state:
        game = item["game"]
        game_id = game["id"]
        winner = winners.get(game_id)
        results.append({
            "game_name": game.get("name", "Unknown"),
            "game_id": game_id,
            "is_premium": game_id in premium_games,
            "winner_name": winner.get("name", "Unknown") if winner else None,
            "winner_badge": winner.get("badge_id", "") if winner else None,
            "total_entries": len(item["shuffled"]),
            "winner_index": item["winner_index"],
        })

    results.sort(key=lambda r: r["game_name"])

    # Build conflict info for any new cascading conflicts
    conflicts_out = []
    if new_conflicts:
        game_name_map = {
            item["game"]["id"]: item["game"].get("name", "Unknown")
            for item in drawing_state
        }
        for badge_id, game_ids in new_conflicts.items():
            premium_wins = [gid for gid in game_ids if gid in premium_games]
            conflicts_out.append({
                "badge_id": badge_id,
                "game_ids": game_ids,
                "game_names": {gid: game_name_map.get(gid, "Unknown") for gid in game_ids},
                "is_premium_conflict": len(premium_wins) > 1,
            })

    return jsonify({
        "ok": True,
        "results": results,
        "conflicts": conflicts_out,
    })
