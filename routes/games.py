from datetime import datetime

from flask import flash, jsonify, redirect, render_template, request, session, url_for

from data_processing import apply_ejections, group_entries_by_game, process_entries
from tte_client import TTEAPIError

from . import main_bp
from .helpers import _get_client, _handle_api_error, login_required


@main_bp.route("/games")
@login_required
def games():
    """Load P2W games and entries, process, and display."""
    library_id = session.get("library_id")
    convention_id = session.get("convention_id")
    if not library_id:
        flash("Please select a convention first.", "error")
        return redirect(url_for("main.convention_select"))

    refresh = request.args.get("refresh") == "1"
    all_games = session.get("cached_games")
    entries = session.get("cached_entries")

    if refresh or all_games is None or entries is None:
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

        # Cache games and entries in session for reuse
        session["cached_games"] = all_games
        session["cached_entries"] = entries

    ejected_entries = session.get("ejected_entries", [])
    filtered = apply_ejections(entries, ejected_entries)
    game_data = group_entries_by_game(filtered, all_games)
    game_data.sort(key=lambda g: g["game"].get("name", ""))

    # Build ejected badge_ids set for display
    ejected_badges = set()
    for badge_id, game_id in ejected_entries:
        if game_id == "*":
            ejected_badges.add(badge_id)

    # Build per-game ejected set
    ejected_per_game = {}
    for badge_id, game_id in ejected_entries:
        if game_id != "*":
            ejected_per_game.setdefault(game_id, set()).add(badge_id)

    premium_games = session.get("premium_games", [])

    data_loaded_at = datetime.now().strftime("%-I:%M %p")

    return render_template(
        "games.html",
        game_data=game_data,
        total_games=len(all_games),
        total_entries=len(filtered),
        convention_name=session.get("convention_name") or session.get("library_name", ""),
        premium_games=premium_games,
        ejected_entries=ejected_entries,
        ejected_badges=ejected_badges,
        ejected_per_game=ejected_per_game,
        data_loaded_at=data_loaded_at,
    )


@main_bp.route("/games/players")
@login_required
def players():
    """Player management page — lists all players with game counts and removal controls."""
    library_id = session.get("library_id")
    if not library_id:
        flash("Please select a convention first.", "error")
        return redirect(url_for("main.convention_select"))

    # Use cached data from the games page to avoid redundant API calls
    all_games = session.get("cached_games")
    entries = session.get("cached_entries")

    if all_games is None or entries is None:
        flash("Please load the games page first.", "info")
        return redirect(url_for("main.games"))

    # Build game name lookup
    game_names = {g.get("id"): g.get("name", "Unknown") for g in all_games}

    # Aggregate by player (badge_id)
    players_map = {}
    for entry in entries:
        badge_id = entry.get("badge_id")
        if not badge_id:
            continue
        if badge_id not in players_map:
            players_map[badge_id] = {
                "badge_id": badge_id,
                "name": entry.get("name", badge_id),
                "games": [],
            }
        game_id = entry.get("librarygame_id")
        players_map[badge_id]["games"].append({
            "game_id": game_id,
            "game_name": game_names.get(game_id, "Unknown"),
        })

    player_list = sorted(players_map.values(), key=lambda p: p["name"].lower())

    # Build removed set from session
    ejected_entries = session.get("ejected_entries", [])
    removed_all = set()
    removed_per_game = {}
    for badge_id, game_id in ejected_entries:
        if game_id == "*":
            removed_all.add(badge_id)
        else:
            removed_per_game.setdefault(badge_id, set()).add(game_id)

    return render_template(
        "players.html",
        player_list=player_list,
        total_players=len(player_list),
        total_entries=len(entries),
        total_games=len(all_games),
        convention_name=session.get("convention_name") or session.get("library_name", ""),
        removed_all=removed_all,
        removed_per_game=removed_per_game,
    )


@main_bp.route("/games/premium", methods=["POST"])
@login_required
def set_premium_games():
    """AJAX endpoint: save premium game designations to session."""
    data = request.get_json(silent=True)
    if data is None or "premium_games" not in data:
        return jsonify({"error": "Invalid request"}), 400

    game_ids = data["premium_games"]
    if not isinstance(game_ids, list):
        return jsonify({"error": "premium_games must be a list"}), 400

    session["premium_games"] = game_ids
    return jsonify({"ok": True, "count": len(game_ids)})


@main_bp.route("/games/eject", methods=["POST"])
@login_required
def eject_player():
    """AJAX endpoint: eject a player from the drawing."""
    data = request.get_json(silent=True)
    if not data or "badge_id" not in data:
        return jsonify({"error": "badge_id is required"}), 400

    badge_id = str(data["badge_id"]).strip()
    game_id = str(data.get("game_id", "*")).strip()
    if not badge_id:
        return jsonify({"error": "badge_id is required"}), 400

    ejected = session.get("ejected_entries", [])

    # Check for duplicates
    for b, g in ejected:
        if b == badge_id and g == game_id:
            return jsonify({"error": "Already ejected"}), 409

    # If ejecting from all games, remove any per-game ejections for this badge
    if game_id == "*":
        ejected = [[b, g] for b, g in ejected if b != badge_id]

    ejected.append([badge_id, game_id])
    session["ejected_entries"] = ejected
    return jsonify({"ok": True, "count": len(ejected)})


@main_bp.route("/games/uneject", methods=["POST"])
@login_required
def uneject_player():
    """AJAX endpoint: undo an ejection."""
    data = request.get_json(silent=True)
    if not data or "badge_id" not in data:
        return jsonify({"error": "badge_id is required"}), 400

    badge_id = str(data["badge_id"]).strip()
    game_id = str(data.get("game_id", "*")).strip()

    ejected = session.get("ejected_entries", [])
    updated = [[b, g] for b, g in ejected if not (b == badge_id and g == game_id)]

    if len(updated) == len(ejected):
        return jsonify({"error": "Ejection not found"}), 404

    session["ejected_entries"] = updated
    return jsonify({"ok": True, "count": len(updated)})


@main_bp.route("/games/entrants/<game_id>")
@login_required(api=True)
def get_entrants(game_id):
    """AJAX endpoint: return entrants for a specific game."""
    library_id = session.get("library_id")
    if not library_id:
        return jsonify({"error": "No library selected"}), 400

    client = _get_client()
    try:
        raw_entries = client.get_library_game_playtowins(game_id)
    except TTEAPIError as exc:
        if getattr(exc, 'status_code', None) in (401, 403):
            session.clear()
            return jsonify({"error": "Session expired — please log in again."}), 401
        return jsonify({"error": str(exc)}), 502

    entries = process_entries(raw_entries)
    ejected_entries = session.get("ejected_entries", [])

    # Build ejection lookup for this game
    ejected_set = set()
    for badge_id, gid in ejected_entries:
        if gid == "*" or gid == game_id:
            ejected_set.add(badge_id)

    entrants = []
    for entry in entries:
        if entry.get("librarygame_id") != game_id:
            continue
        badge_id = entry.get("badge_id", "")
        entrants.append({
            "badge_id": badge_id,
            "name": entry.get("name", badge_id),
            "ejected": badge_id in ejected_set,
        })

    entrants.sort(key=lambda e: e["name"])
    return jsonify({"ok": True, "entrants": entrants})
