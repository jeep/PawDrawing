import logging
from datetime import datetime

from flask import flash, jsonify, redirect, render_template, request, session, url_for

from data_processing import apply_ejections, group_entries_by_game
from drawing import (
    advance_winner,
    apply_resolution,
    build_conflict_info,
    detect_conflicts,
    get_current_winners,
    run_drawing,
)

from session_keys import SK

from . import main_bp
from .helpers import _require_active_drawing, is_valid_badge_id, is_valid_tte_id, login_required

logger = logging.getLogger(__name__)


def _build_results_from_session():
    """Build display-friendly results list from session drawing_state."""
    drawing_state = session.get(SK.DRAWING_STATE, [])
    premium_games = session.get(SK.PREMIUM_GAMES, [])
    picked_up = set(session.get(SK.PICKED_UP, []))
    solo_dismissed = set(session.get(SK.SOLO_DISMISSED_GAMES, []))
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
@login_required
def run_drawing_route():
    """Execute the drawing algorithm and redirect to results."""
    library_id = session.get(SK.LIBRARY_ID)
    if not library_id:
        flash("Please select a convention first.", "error")
        return redirect(url_for("main.convention_select"))

    # Use cached data from the games page to avoid redundant API calls
    all_games = session.get(SK.CACHED_GAMES)
    entries = session.get(SK.CACHED_ENTRIES)

    if all_games is None or entries is None:
        flash("Please load the games page first.", "info")
        return redirect(url_for("main.games"))

    ejected_entries = session.get(SK.EJECTED_ENTRIES, [])
    filtered = apply_ejections(entries, ejected_entries)
    game_data = group_entries_by_game(filtered, all_games)
    premium_games = session.get(SK.PREMIUM_GAMES, [])

    drawing_state, conflicts, auto_resolved = run_drawing(game_data, premium_games)

    logger.info("Drawing executed for library %s: %d games, %d conflicts, %d auto-resolved",
                library_id, len(drawing_state), len(conflicts), len(auto_resolved))

    # Store drawing state in session for conflict resolution
    session[SK.DRAWING_STATE] = drawing_state
    session[SK.DRAWING_CONFLICTS] = conflicts
    session[SK.AUTO_RESOLVED] = auto_resolved
    session[SK.PICKED_UP] = []
    session[SK.NOT_HERE] = []
    session[SK.NOT_HERE_WARNING_DISMISSED] = False
    session[SK.SOLO_DISMISSED_GAMES] = []
    session[SK.DRAWING_TIMESTAMP] = datetime.now().strftime("%-I:%M %p")

    return redirect(url_for("main.drawing_results"))


@main_bp.route("/drawing/results")
@login_required
def drawing_results():
    """Display drawing results from session state."""
    drawing_state = session.get(SK.DRAWING_STATE)
    if drawing_state is None:
        flash("No drawing results to display.", "error")
        return redirect(url_for("main.games"))

    results = _build_results_from_session()
    conflicts = session.get(SK.DRAWING_CONFLICTS, [])

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
        auto_resolved=session.get(SK.AUTO_RESOLVED, []),
        conflicted_game_ids=conflicted_game_ids,
        convention_name=session.get(SK.CONVENTION_NAME) or session.get(SK.LIBRARY_NAME, ""),
        picked_up=set(session.get(SK.PICKED_UP, [])),
        not_here=session.get(SK.NOT_HERE, []),
        not_here_warning_dismissed=session.get(SK.NOT_HERE_WARNING_DISMISSED, False),
        drawing_timestamp=session.get(SK.DRAWING_TIMESTAMP, ""),
    )


@main_bp.route("/drawing/resolve", methods=["POST"])
@login_required
def resolve_conflicts():
    """Apply admin conflict resolution choices."""
    drawing_state = _require_active_drawing()
    if isinstance(drawing_state, tuple):
        return drawing_state

    data = request.get_json(silent=True)
    if not data or "resolutions" not in data:
        return jsonify({"error": "Invalid request"}), 400

    # resolutions: list of {badge_id: str, keep_game_id: str}
    keep_map = {}
    for res in data["resolutions"]:
        badge_id = res.get("badge_id")
        keep_game_id = res.get("keep_game_id")
        if not badge_id or not keep_game_id:
            continue
        if not is_valid_badge_id(badge_id) or not is_valid_tte_id(keep_game_id):
            logger.warning("Invalid ID format in conflict resolution payload")
            return jsonify({"error": "Invalid ID format in resolutions"}), 400
        keep_map[badge_id] = keep_game_id

    premium_games = set(session.get(SK.PREMIUM_GAMES, []))
    advanced = apply_resolution(drawing_state, keep_map, premium_games)

    # Track any games that exhausted their entrant list during resolution
    winners = get_current_winners(drawing_state)
    solo_dismissed = session.get(SK.SOLO_DISMISSED_GAMES, [])
    for game_id in advanced:
        if winners.get(game_id) is None and game_id not in solo_dismissed:
            solo_dismissed.append(game_id)
    session[SK.SOLO_DISMISSED_GAMES] = solo_dismissed

    # Check for new conflicts from cascading
    new_conflicts = detect_conflicts(drawing_state)

    session[SK.DRAWING_STATE] = drawing_state

    # Remove resolved badges from stored conflicts, add any new cascading ones
    remaining_conflicts = [
        c for c in session.get(SK.DRAWING_CONFLICTS, [])
        if c["badge_id"] not in keep_map
    ]

    # Build conflict info for any new cascading conflicts
    conflicts_out = list(remaining_conflicts)
    if new_conflicts:
        existing_badge_ids = {c["badge_id"] for c in conflicts_out}
        new_only = {bid: gids for bid, gids in new_conflicts.items()
                    if bid not in existing_badge_ids}
        conflicts_out.extend(build_conflict_info(drawing_state, new_only, premium_games))

    session[SK.DRAWING_CONFLICTS] = conflicts_out

    logger.info("Conflict resolution applied: %d badges resolved, %d remaining conflicts",
                len(keep_map), len(conflicts_out))

    results = _build_results_from_session()

    return jsonify({
        "ok": True,
        "results": results,
        "conflicts": conflicts_out,
    })


@main_bp.route("/drawing/dismiss-game", methods=["POST"])
@login_required
def dismiss_conflict_game():
    """Dismiss a single game from a multi-win conflict.

    Advances the winner on the dismissed game. If only one game remains
    for that person, auto-resolves the conflict. Tracks single-entrant
    dismissed games so they aren't shown as "To the box".
    """
    drawing_state = _require_active_drawing()
    if isinstance(drawing_state, tuple):
        return drawing_state

    data = request.get_json(silent=True)
    if not data or "badge_id" not in data or "game_id" not in data:
        return jsonify({"error": "Invalid request"}), 400

    badge_id = data["badge_id"]
    game_id = data["game_id"]
    if not is_valid_badge_id(badge_id):
        logger.warning("Invalid badge ID in dismiss request: %s", badge_id)
        return jsonify({"error": "Invalid badge ID format"}), 400
    if not is_valid_tte_id(game_id):
        logger.warning("Invalid game ID in dismiss request: %s", game_id)
        return jsonify({"error": "Invalid game ID format"}), 400

    # Find how many entrants this game has
    total_entrants = 0
    for item in drawing_state:
        if item["game"]["id"] == game_id:
            total_entrants = len(item["shuffled"])
            break

    not_here = set(session.get(SK.NOT_HERE, []))
    found = advance_winner(drawing_state, game_id, not_here=not_here)

    # If the game is now exhausted (no more candidates), track it so it
    # shows as "No winner (redraw eligible)" instead of "To the box!"
    if not found:
        solo_dismissed = session.get(SK.SOLO_DISMISSED_GAMES, [])
        if game_id not in solo_dismissed:
            solo_dismissed.append(game_id)
        session[SK.SOLO_DISMISSED_GAMES] = solo_dismissed

    session[SK.DRAWING_STATE] = drawing_state

    # Update conflicts: remove the dismissed game from the badge's conflict
    conflicts = session.get(SK.DRAWING_CONFLICTS, [])
    updated_conflicts = []
    for c in conflicts:
        if c["badge_id"] == badge_id:
            remaining_games = [gid for gid in c["game_ids"] if gid != game_id]
            remaining_names = {gid: c["game_names"][gid] for gid in remaining_games}
            if len(remaining_games) > 1:
                # Still a conflict — update in place
                premium_games = set(session.get(SK.PREMIUM_GAMES, []))
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
        new_only = {bid: gids for bid, gids in new_conflicts.items()
                    if bid not in existing_badge_ids}
        updated_conflicts.extend(build_conflict_info(drawing_state, new_only,
                                                     set(session.get(SK.PREMIUM_GAMES, []))))

    session[SK.DRAWING_CONFLICTS] = updated_conflicts

    logger.info("Game %s dismissed from conflict for badge %s (exhausted=%s)",
                game_id, badge_id, not found)

    results = _build_results_from_session()

    return jsonify({
        "ok": True,
        "results": results,
        "conflicts": updated_conflicts,
        "dismissed_game_id": game_id,
        "was_exhausted": not found,
        "was_solo_entrant": not found and total_entrants == 1,
    })
