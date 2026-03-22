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
            raw_entries = client.get_library_playtowins(library_id)
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
        convention_name=session.get("convention_name", ""),
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
        return _handle_api_error(exc, url_for("main.games"), "load games")

    try:
        if convention_id:
            raw_entries = client.get_convention_playtowins(convention_id)
        else:
            raw_entries = client.get_library_playtowins(library_id)
    except TTEAPIError as exc:
        return _handle_api_error(exc, url_for("main.games"), "load entries")

    entries = process_entries(raw_entries)
    game_data = group_entries_by_game(entries, all_games)
    premium_games = session.get("premium_games", [])

    drawing_state, conflicts, auto_resolved = run_drawing(game_data, premium_games)

    # Store drawing state in session for conflict resolution
    session["drawing_state"] = drawing_state
    session["auto_resolved"] = auto_resolved
    session["picked_up"] = []
    session["redistribution_declined"] = {}
    session["redistribution_winners"] = {}
    session["drawing_timestamp"] = datetime.now().strftime("%-I:%M %p")

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

    # Build a set of game IDs that are in conflict for highlighting
    conflicted_game_ids = set()
    for conflict in conflicts:
        conflicted_game_ids.update(conflict["game_ids"])

    return render_template(
        "drawing_results.html",
        results=results,
        conflicts=conflicts,
        auto_resolved=auto_resolved,
        conflicted_game_ids=conflicted_game_ids,
        convention_name=session.get("convention_name", ""),
        picked_up=set(),
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


@main_bp.route("/drawing/redistribute")
def redistribute():
    """Show redistribution page for unclaimed games."""
    if not session.get("tte_session_id"):
        flash("Please log in first.", "error")
        return redirect(url_for("main.login"))

    drawing_state = session.get("drawing_state")
    if not drawing_state:
        flash("No active drawing to redistribute.", "error")
        return redirect(url_for("main.games"))

    picked_up = set(session.get("picked_up", []))
    winners = get_current_winners(drawing_state)
    declined = session.get("redistribution_declined", {})

    unclaimed_games = []
    for item in drawing_state:
        game = item["game"]
        game_id = game["id"]
        winner = winners.get(game_id)

        # Only include games that have a winner but were not picked up
        if winner and game_id not in picked_up:
            # Build the full entrant list in shuffled order
            game_declined = set(declined.get(game_id, []))
            entrants = []
            new_winner_badge = session.get("redistribution_winners", {}).get(game_id)
            for i, entry in enumerate(item["shuffled"]):
                badge_id = entry.get("badge_id", "")
                entrants.append({
                    "name": entry.get("name", "Unknown"),
                    "badge_id": badge_id,
                    "position": i + 1,
                    "is_original_winner": i == item["winner_index"],
                    "is_declined": badge_id in game_declined,
                    "is_new_winner": badge_id == new_winner_badge,
                })

            unclaimed_games.append({
                "game_name": game.get("name", "Unknown"),
                "game_id": game_id,
                "entrants": entrants,
                "has_new_winner": new_winner_badge is not None,
            })

    unclaimed_games.sort(key=lambda g: g["game_name"])

    return render_template(
        "redistribute.html",
        unclaimed_games=unclaimed_games,
        convention_name=session.get("convention_name", ""),
    )


@main_bp.route("/drawing/redistribute/claim", methods=["POST"])
def redistribute_claim():
    """Mark an entrant as claimed (new winner) or declined for a game."""
    if not session.get("tte_session_id"):
        return jsonify({"error": "Not authenticated"}), 401

    drawing_state = session.get("drawing_state")
    if not drawing_state:
        return jsonify({"error": "No active drawing"}), 400

    data = request.get_json(silent=True)
    if not data or "game_id" not in data or "badge_id" not in data or "action" not in data:
        return jsonify({"error": "Invalid request"}), 400

    game_id = data["game_id"]
    badge_id = data["badge_id"]
    action = data["action"]

    if action not in ("claim", "decline"):
        return jsonify({"error": "Invalid action"}), 400

    declined = session.get("redistribution_declined", {})
    redistribution_winners = session.get("redistribution_winners", {})

    if action == "decline":
        if game_id not in declined:
            declined[game_id] = []
        if badge_id not in declined[game_id]:
            declined[game_id].append(badge_id)
        # If this person was the new winner, remove them
        if redistribution_winners.get(game_id) == badge_id:
            del redistribution_winners[game_id]
    elif action == "claim":
        redistribution_winners[game_id] = badge_id

    session["redistribution_declined"] = declined
    session["redistribution_winners"] = redistribution_winners

    return jsonify({
        "ok": True,
        "game_id": game_id,
        "badge_id": badge_id,
        "action": action,
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
    redistribution_winners = session.get("redistribution_winners", {})

    # Build a map of game_id -> shuffled entries for redistribution lookups
    game_entries_map = {}
    for item in drawing_state:
        game_entries_map[item["game"]["id"]] = item["shuffled"]

    # Collect PlayToWin entry IDs for picked-up games
    entries_to_update = []
    for game_id in picked_up:
        redist_badge = redistribution_winners.get(game_id)
        if redist_badge:
            # Redistribution winner: find entry by badge_id
            for entry in game_entries_map.get(game_id, []):
                if entry.get("badge_id") == redist_badge:
                    entries_to_update.append({
                        "playtowin_id": entry["id"],
                        "game_id": game_id,
                    })
                    break
        else:
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
    redistribution_winners = session.get("redistribution_winners", {})

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Game", "Premium", "Entries", "Winner", "Badge", "Picked Up"])

    rows = []
    for item in drawing_state:
        game = item["game"]
        game_id = game["id"]
        winner = winners.get(game_id)
        is_premium = game_id in premium_games

        # Check for redistribution winner
        redist_badge = redistribution_winners.get(game_id)
        if redist_badge:
            for entry in item["shuffled"]:
                if entry.get("badge_id") == redist_badge:
                    winner = entry
                    break

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
