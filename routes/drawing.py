from datetime import datetime

from flask import flash, jsonify, redirect, render_template, request, session, url_for

from data_processing import apply_ejections, group_entries_by_game
from drawing import (
    advance_winner,
    apply_resolution,
    detect_conflicts,
    get_current_winners,
    run_drawing,
)

from . import main_bp


def _build_results_from_session():
    """Build display-friendly results list from session drawing_state."""
    drawing_state = session.get("drawing_state", [])
    premium_games = session.get("premium_games", [])
    picked_up = set(session.get("picked_up", []))
    solo_dismissed = set(session.get("solo_dismissed_games", []))
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
            "is_solo_dismissed": game_id in solo_dismissed,
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
    if not library_id:
        flash("Please select a convention first.", "error")
        return redirect(url_for("main.convention_select"))

    # Use cached data from the games page to avoid redundant API calls
    all_games = session.get("cached_games")
    entries = session.get("cached_entries")

    if all_games is None or entries is None:
        flash("Please load the games page first.", "info")
        return redirect(url_for("main.games"))

    ejected_entries = session.get("ejected_entries", [])
    filtered = apply_ejections(entries, ejected_entries)
    game_data = group_entries_by_game(filtered, all_games)
    premium_games = session.get("premium_games", [])

    drawing_state, conflicts, auto_resolved = run_drawing(game_data, premium_games)

    # Store drawing state in session for conflict resolution
    session["drawing_state"] = drawing_state
    session["drawing_conflicts"] = conflicts
    session["auto_resolved"] = auto_resolved
    session["picked_up"] = []
    session["not_here"] = []
    session["not_here_warning_dismissed"] = False
    session["solo_dismissed_games"] = []
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
    no_entries = [r for r in results if not r["has_entries"] or (r["has_entries"] and not r["has_winner"] and not r["is_picked_up"])]

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
    advanced = apply_resolution(drawing_state, keep_map, premium_games)

    # Track any games that exhausted their entrant list during resolution
    winners = get_current_winners(drawing_state)
    solo_dismissed = session.get("solo_dismissed_games", [])
    for game_id in advanced:
        if winners.get(game_id) is None and game_id not in solo_dismissed:
            solo_dismissed.append(game_id)
    session["solo_dismissed_games"] = solo_dismissed

    # Check for new conflicts from cascading
    new_conflicts = detect_conflicts(drawing_state)

    session["drawing_state"] = drawing_state

    # Remove resolved badges from stored conflicts, add any new cascading ones
    remaining_conflicts = [
        c for c in session.get("drawing_conflicts", [])
        if c["badge_id"] not in keep_map
    ]

    # Build conflict info for any new cascading conflicts
    conflicts_out = list(remaining_conflicts)
    if new_conflicts:
        existing_badge_ids = {c["badge_id"] for c in conflicts_out}
        winners = get_current_winners(drawing_state)
        game_name_map = {
            item["game"]["id"]: item["game"].get("name", "Unknown")
            for item in drawing_state
        }
        for badge_id, game_ids in new_conflicts.items():
            if badge_id in existing_badge_ids:
                continue
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

    session["drawing_conflicts"] = conflicts_out

    results = _build_results_from_session()

    return jsonify({
        "ok": True,
        "results": results,
        "conflicts": conflicts_out,
    })


@main_bp.route("/drawing/dismiss-game", methods=["POST"])
def dismiss_conflict_game():
    """Dismiss a single game from a multi-win conflict.

    Advances the winner on the dismissed game. If only one game remains
    for that person, auto-resolves the conflict. Tracks single-entrant
    dismissed games so they aren't shown as "To the box".
    """
    if not session.get("tte_session_id"):
        return jsonify({"error": "Not authenticated"}), 401

    drawing_state = session.get("drawing_state")
    if not drawing_state:
        return jsonify({"error": "No active drawing"}), 400

    data = request.get_json(silent=True)
    if not data or "badge_id" not in data or "game_id" not in data:
        return jsonify({"error": "Invalid request"}), 400

    badge_id = data["badge_id"]
    game_id = data["game_id"]

    # Find how many entrants this game has
    total_entrants = 0
    for item in drawing_state:
        if item["game"]["id"] == game_id:
            total_entrants = len(item["shuffled"])
            break

    not_here = set(session.get("not_here", []))
    found = advance_winner(drawing_state, game_id, not_here=not_here)

    # If the game is now exhausted (no more candidates), track it so it
    # shows as "No winner (redraw eligible)" instead of "To the box!"
    if not found:
        solo_dismissed = session.get("solo_dismissed_games", [])
        if game_id not in solo_dismissed:
            solo_dismissed.append(game_id)
        session["solo_dismissed_games"] = solo_dismissed

    session["drawing_state"] = drawing_state

    # Update conflicts: remove the dismissed game from the badge's conflict
    conflicts = session.get("drawing_conflicts", [])
    updated_conflicts = []
    for c in conflicts:
        if c["badge_id"] == badge_id:
            remaining_games = [gid for gid in c["game_ids"] if gid != game_id]
            remaining_names = {gid: c["game_names"][gid] for gid in remaining_games}
            if len(remaining_games) > 1:
                # Still a conflict — update in place
                premium_games = set(session.get("premium_games", []))
                premium_wins = [gid for gid in remaining_games if gid in premium_games]
                updated_conflicts.append({
                    "badge_id": c["badge_id"],
                    "winner_name": c["winner_name"],
                    "game_ids": remaining_games,
                    "game_names": remaining_names,
                    "is_premium_conflict": len(premium_wins) > 1,
                })
            # If only 1 game left, conflict is auto-resolved (no action needed)
        else:
            updated_conflicts.append(c)

    # Check for new cascading conflicts (the advanced winner might conflict)
    new_conflicts = detect_conflicts(drawing_state)
    if new_conflicts:
        existing_badge_ids = {c["badge_id"] for c in updated_conflicts}
        winners = get_current_winners(drawing_state)
        game_name_map = {
            item["game"]["id"]: item["game"].get("name", "Unknown")
            for item in drawing_state
        }
        premium_games = set(session.get("premium_games", []))
        for cbid, game_ids in new_conflicts.items():
            if cbid in existing_badge_ids:
                continue
            premium_wins = [gid for gid in game_ids if gid in premium_games]
            winner_name = "Unknown"
            for gid in game_ids:
                w = winners.get(gid)
                if w and w.get("name"):
                    winner_name = w["name"]
                    break
            updated_conflicts.append({
                "badge_id": cbid,
                "winner_name": winner_name,
                "game_ids": game_ids,
                "game_names": {gid: game_name_map.get(gid, "Unknown") for gid in game_ids},
                "is_premium_conflict": len(premium_wins) > 1,
            })

    session["drawing_conflicts"] = updated_conflicts

    results = _build_results_from_session()

    return jsonify({
        "ok": True,
        "results": results,
        "conflicts": updated_conflicts,
        "dismissed_game_id": game_id,
        "was_exhausted": not found,
        "was_solo_entrant": not found and total_entrants == 1,
    })
