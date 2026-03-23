import csv
import io
from datetime import date, datetime

from flask import Blueprint, flash, jsonify, redirect, render_template, request, session, url_for, Response

from data_processing import group_entries_by_game, process_entries
from drawing import (
    advance_winner,
    apply_resolution,
    detect_conflicts,
    get_current_winners,
    redraw_unclaimed,
    run_drawing,
)
from tte_client import TTEAPIError, TTEClient, TTETimeoutError

main_bp = Blueprint("main", __name__)


def _get_client():
    """Create a TTEClient with the current user's session."""
    client = TTEClient()
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
        session["tte_user_id"] = client.user_id
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


@main_bp.route("/library/browse")
def library_browse():
    """AJAX endpoint: list libraries owned by the logged-in user."""
    if not session.get("tte_session_id"):
        return jsonify({"error": "Not authenticated"}), 401

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
def library_confirm():
    """Fetch library details and store in session (no convention)."""
    if not session.get("tte_session_id"):
        flash("Please log in first.", "error")
        return redirect(url_for("main.login"))

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

    return render_template(
        "library_confirm.html",
        library_name=library_name,
    )


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
        if getattr(exc, 'status_code', None) in (401, 403):
            session.clear()
            return jsonify({"error": "Session expired — please log in again."}), 401
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
        return _handle_api_error(exc, url_for("main.convention_select"), "load games")

    try:
        if convention_id:
            raw_entries = client.get_convention_playtowins(convention_id)
        else:
            raw_entries = []
            for game in all_games:
                game_id = game.get("id")
                if game_id:
                    raw_entries.extend(client.get_library_game_playtowins(game_id))
    except TTEAPIError as exc:
        return _handle_api_error(exc, url_for("main.convention_select"), "load entries")

    entries = process_entries(raw_entries)
    game_data = group_entries_by_game(entries, all_games)
    game_data.sort(key=lambda g: g["game"].get("name", ""))

    premium_games = session.get("premium_games", [])

    data_loaded_at = datetime.now().strftime("%-I:%M %p")

    return render_template(
        "games.html",
        game_data=game_data,
        total_games=len(all_games),
        total_entries=len(entries),
        convention_name=session.get("convention_name") or session.get("library_name", ""),
        premium_games=premium_games,
        data_loaded_at=data_loaded_at,
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


def _build_results_from_session():
    """Build display-friendly results list from session drawing_state."""
    drawing_state = session.get("drawing_state", [])
    premium_games = session.get("premium_games", [])
    picked_up = set(session.get("picked_up", []))
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
            "is_picked_up": game_id in picked_up,
            "has_winner": winner is not None,
            "has_entries": len(item["shuffled"]) > 0,
        })

    results.sort(key=lambda r: r["game_name"])
    return results


@main_bp.route("/drawing", methods=["POST"])
def run_drawing_route():
    """Execute the drawing algorithm and redirect to results."""
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
        return _handle_api_error(exc, url_for("main.games"), "load games")

    try:
        if convention_id:
            raw_entries = client.get_convention_playtowins(convention_id)
        else:
            raw_entries = []
            for game in all_games:
                game_id = game.get("id")
                if game_id:
                    raw_entries.extend(client.get_library_game_playtowins(game_id))
    except TTEAPIError as exc:
        return _handle_api_error(exc, url_for("main.games"), "load entries")

    entries = process_entries(raw_entries)
    game_data = group_entries_by_game(entries, all_games)
    premium_games = session.get("premium_games", [])

    drawing_state, conflicts, auto_resolved = run_drawing(game_data, premium_games)

    # Store drawing state in session for conflict resolution
    session["drawing_state"] = drawing_state
    session["drawing_conflicts"] = conflicts
    session["auto_resolved"] = auto_resolved
    session["picked_up"] = []
    session["not_here"] = []
    session["not_here_warning_dismissed"] = False
    session["drawing_timestamp"] = datetime.now().strftime("%-I:%M %p")

    return redirect(url_for("main.drawing_results"))


@main_bp.route("/drawing/results")
def drawing_results():
    """Display drawing results from session state."""
    if not session.get("tte_session_id"):
        flash("Please log in first.", "error")
        return redirect(url_for("main.login"))

    drawing_state = session.get("drawing_state")
    if drawing_state is None:
        flash("No drawing results to display.", "error")
        return redirect(url_for("main.games"))

    results = _build_results_from_session()
    conflicts = session.get("drawing_conflicts", [])

    conflicted_game_ids = set()
    for conflict in conflicts:
        conflicted_game_ids.update(conflict["game_ids"])

    # Categorize results into three groups
    awaiting = [r for r in results if r["has_winner"] and not r["is_picked_up"]]
    picked_up_list = [r for r in results if r["has_winner"] and r["is_picked_up"]]
    no_entries = [r for r in results if not r["has_entries"]]

    return render_template(
        "drawing_results.html",
        results=results,
        awaiting=awaiting,
        picked_up_list=picked_up_list,
        no_entries=no_entries,
        conflicts=conflicts,
        auto_resolved=session.get("auto_resolved", []),
        conflicted_game_ids=conflicted_game_ids,
        convention_name=session.get("convention_name") or session.get("library_name", ""),
        picked_up=set(session.get("picked_up", [])),
        not_here=session.get("not_here", []),
        not_here_warning_dismissed=session.get("not_here_warning_dismissed", False),
        drawing_timestamp=session.get("drawing_timestamp", ""),
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
            winner_name = "Unknown"
            for gid in game_ids:
                w = winners.get(gid)
                if w and w.get("name"):
                    winner_name = w["name"]
                    break
            conflicts_out.append({
                "badge_id": badge_id,
                "winner_name": winner_name,
                "game_ids": game_ids,
                "game_names": {gid: game_name_map.get(gid, "Unknown") for gid in game_ids},
                "is_premium_conflict": len(premium_wins) > 1,
            })

    return jsonify({
        "ok": True,
        "results": results,
        "conflicts": conflicts_out,
    })


@main_bp.route("/drawing/pickup", methods=["POST"])
def toggle_pickup():
    """Toggle the picked-up status of a game."""
    if not session.get("tte_session_id"):
        return jsonify({"error": "Not authenticated"}), 401

    if not session.get("drawing_state"):
        return jsonify({"error": "No active drawing"}), 400

    data = request.get_json(silent=True)
    if not data or "game_id" not in data:
        return jsonify({"error": "Invalid request"}), 400

    game_id = data["game_id"]
    picked_up = session.get("picked_up", [])

    if game_id in picked_up:
        picked_up.remove(game_id)
        is_picked_up = False
    else:
        picked_up.append(game_id)
        is_picked_up = True

    session["picked_up"] = picked_up

    return jsonify({
        "ok": True,
        "game_id": game_id,
        "is_picked_up": is_picked_up,
        "picked_up_count": len(picked_up),
    })


@main_bp.route("/drawing/award-next", methods=["POST"])
def award_next():
    """Advance a game to the next entrant in the shuffled list."""
    if not session.get("tte_session_id"):
        return jsonify({"error": "Not authenticated"}), 401

    drawing_state = session.get("drawing_state")
    if not drawing_state:
        return jsonify({"error": "No active drawing"}), 400

    data = request.get_json(silent=True)
    if not data or "game_id" not in data:
        return jsonify({"error": "Invalid request"}), 400

    game_id = data["game_id"]
    not_here = set(session.get("not_here", []))

    found = advance_winner(drawing_state, game_id, not_here=not_here)
    session["drawing_state"] = drawing_state

    winners = get_current_winners(drawing_state)
    winner = winners.get(game_id)

    return jsonify({
        "ok": True,
        "game_id": game_id,
        "has_winner": found,
        "winner_name": winner.get("name", "Unknown") if winner else None,
        "winner_badge": winner.get("badge_id", "") if winner else None,
    })


@main_bp.route("/drawing/not-here", methods=["POST"])
def mark_not_here():
    """Mark a person as 'not here' — permanently absent for this drawing."""
    if not session.get("tte_session_id"):
        return jsonify({"error": "Not authenticated"}), 401

    drawing_state = session.get("drawing_state")
    if not drawing_state:
        return jsonify({"error": "No active drawing"}), 400

    data = request.get_json(silent=True)
    if not data or "badge_id" not in data:
        return jsonify({"error": "Invalid request"}), 400

    badge_id = data["badge_id"]
    not_here = session.get("not_here", [])

    if badge_id in not_here:
        return jsonify({"error": "Already marked as not here"}), 400

    not_here.append(badge_id)
    session["not_here"] = not_here

    # Dismiss warning if requested
    if data.get("dismiss_warning"):
        session["not_here_warning_dismissed"] = True

    # Auto-advance all unpicked-up games won by this person
    picked_up = set(session.get("picked_up", []))
    not_here_set = set(not_here)
    winners = get_current_winners(drawing_state)
    advanced_games = []

    for game_id, winner in winners.items():
        if winner and winner.get("badge_id") == badge_id and game_id not in picked_up:
            advance_winner(drawing_state, game_id, not_here=not_here_set)
            new_winner = get_current_winners(drawing_state).get(game_id)
            advanced_games.append({
                "game_id": game_id,
                "winner_name": new_winner.get("name", "Unknown") if new_winner else None,
                "winner_badge": new_winner.get("badge_id", "") if new_winner else None,
                "has_winner": new_winner is not None,
            })

    session["drawing_state"] = drawing_state

    return jsonify({
        "ok": True,
        "badge_id": badge_id,
        "advanced_games": advanced_games,
    })


@main_bp.route("/drawing/redraw-unclaimed", methods=["POST"])
def redraw_all_unclaimed():
    """Redraw all unclaimed games with fresh shuffle."""
    if not session.get("tte_session_id"):
        return jsonify({"error": "Not authenticated"}), 401

    drawing_state = session.get("drawing_state")
    if not drawing_state:
        return jsonify({"error": "No active drawing"}), 400

    data = request.get_json(silent=True) or {}
    same_rules = data.get("same_rules", False)

    picked_up = set(session.get("picked_up", []))
    not_here_set = set(session.get("not_here", []))
    premium_games = session.get("premium_games", [])

    # Determine unclaimed game IDs (have a winner or had one, not picked up)
    winners = get_current_winners(drawing_state)
    unclaimed_ids = set()
    original_winner_badges = set()
    for item in drawing_state:
        game_id = item["game"]["id"]
        if game_id not in picked_up and item["shuffled"]:
            unclaimed_ids.add(game_id)
            # Collect original first-draw winners for exclusion
            if 0 <= item["winner_index"] < len(item["shuffled"]):
                badge = item["shuffled"][item["winner_index"]].get("badge_id")
                if badge:
                    original_winner_badges.add(badge)

    if not unclaimed_ids:
        return jsonify({"error": "No unclaimed games to redraw"}), 400

    conflicts, auto_resolved = redraw_unclaimed(
        drawing_state, unclaimed_ids, not_here_set, original_winner_badges,
        same_rules=same_rules, premium_game_ids=premium_games,
    )

    session["drawing_state"] = drawing_state
    if conflicts:
        session["drawing_conflicts"] = conflicts
    else:
        session["drawing_conflicts"] = []
    if auto_resolved:
        session["auto_resolved"] = auto_resolved
    else:
        session["auto_resolved"] = []

    # Build fresh results
    results = _build_results_from_session()

    conflicted_game_ids = []
    for conflict in conflicts:
        conflicted_game_ids.extend(conflict["game_ids"])

    return jsonify({
        "ok": True,
        "results": results,
        "conflicts": conflicts,
        "auto_resolved": auto_resolved,
        "conflicted_game_ids": conflicted_game_ids,
    })


@main_bp.route("/drawing/push", methods=["POST"])
def push_to_tte():
    """Push win flags to TTE for all picked-up games."""
    if not session.get("tte_session_id"):
        return jsonify({"error": "Not authenticated"}), 401

    drawing_state = session.get("drawing_state")
    if not drawing_state:
        return jsonify({"error": "No active drawing"}), 400

    picked_up = set(session.get("picked_up", []))
    if not picked_up:
        return jsonify({"error": "No games marked as picked up"}), 400

    winners = get_current_winners(drawing_state)

    # Collect PlayToWin entry IDs for picked-up games
    entries_to_update = []
    for game_id in picked_up:
        winner = winners.get(game_id)
        if winner:
            entries_to_update.append({
                "playtowin_id": winner["id"],
                "game_id": game_id,
            })

    client = _get_client()
    successes = []
    failures = []

    for entry in entries_to_update:
        try:
            client.update_playtowin(entry["playtowin_id"], {"win": 1})
            successes.append(entry["game_id"])
        except TTEAPIError as exc:
            if getattr(exc, 'status_code', None) in (401, 403):
                session.clear()
                return jsonify({"error": "Session expired — please log in again."}), 401
            failures.append({
                "game_id": entry["game_id"],
                "error": str(exc),
            })

    return jsonify({
        "ok": True,
        "total": len(entries_to_update),
        "successes": len(successes),
        "failures": failures,
    })


@main_bp.route("/drawing/export")
def export_csv():
    """Export drawing results as a CSV file."""
    if not session.get("tte_session_id"):
        flash("Please log in first.", "error")
        return redirect(url_for("main.login"))

    drawing_state = session.get("drawing_state")
    if not drawing_state:
        flash("No active drawing to export.", "error")
        return redirect(url_for("main.games"))

    picked_up = set(session.get("picked_up", []))
    premium_games = set(session.get("premium_games", []))
    winners = get_current_winners(drawing_state)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Game", "Premium", "Entries", "Winner", "Badge", "Picked Up"])

    rows = []
    for item in drawing_state:
        game = item["game"]
        game_id = game["id"]
        winner = winners.get(game_id)
        is_premium = game_id in premium_games

        rows.append({
            "game_name": game.get("name", "Unknown"),
            "is_premium": is_premium,
            "total_entries": len(item["shuffled"]),
            "winner_name": winner.get("name", "Unknown") if winner else "",
            "winner_badge": winner.get("badge_id", "") if winner else "",
            "picked_up": game_id in picked_up,
        })

    rows.sort(key=lambda r: r["game_name"])

    for row in rows:
        writer.writerow([
            row["game_name"],
            "Yes" if row["is_premium"] else "No",
            row["total_entries"],
            row["winner_name"],
            row["winner_badge"],
            "Yes" if row["picked_up"] else "No",
        ])

    convention_name = session.get("convention_name", "Drawing")
    safe_name = "".join(c if c.isalnum() or c in " -_" else "" for c in convention_name).strip().replace(" ", "_")
    filename = f"PawDrawing_{safe_name}_{date.today().isoformat()}.csv"

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
