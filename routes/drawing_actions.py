import csv
import io
import logging
from datetime import date

from flask import Response, flash, jsonify, redirect, request, session, url_for

from drawing import advance_winner, get_current_winners, redraw_unclaimed
from session_keys import SK
from tte_client import TTEAPIError

from . import main_bp
from .drawing import _build_results_from_session
from .helpers import (
    _get_client,
    _handle_api_json_error,
    _require_active_drawing,
    is_valid_badge_id,
    is_valid_tte_id,
    login_required,
)

logger = logging.getLogger(__name__)


@main_bp.route("/drawing/pickup", methods=["POST"])
@login_required
def toggle_pickup():
    """Toggle the picked-up status of a game."""
    result = _require_active_drawing()
    if isinstance(result, tuple):
        return result

    data = request.get_json(silent=True)
    if not data or "game_id" not in data:
        return jsonify({"error": "Invalid request"}), 400

    game_id = data["game_id"]
    if not is_valid_tte_id(game_id):
        return jsonify({"error": "Invalid game ID format"}), 400
    picked_up = session.get(SK.PICKED_UP, [])

    if game_id in picked_up:
        picked_up.remove(game_id)
        is_picked_up = False
    else:
        picked_up.append(game_id)
        is_picked_up = True

    session[SK.PICKED_UP] = picked_up

    return jsonify({
        "ok": True,
        "game_id": game_id,
        "is_picked_up": is_picked_up,
        "picked_up_count": len(picked_up),
    })


@main_bp.route("/drawing/award-next", methods=["POST"])
@login_required
def award_next():
    """Advance a game to the next entrant in the shuffled list."""
    drawing_state = _require_active_drawing()
    if isinstance(drawing_state, tuple):
        return drawing_state

    data = request.get_json(silent=True)
    if not data or "game_id" not in data:
        return jsonify({"error": "Invalid request"}), 400

    game_id = data["game_id"]
    if not is_valid_tte_id(game_id):
        return jsonify({"error": "Invalid game ID format"}), 400
    not_here = set(session.get(SK.NOT_HERE, []))

    found = advance_winner(drawing_state, game_id, not_here=not_here)
    session[SK.DRAWING_STATE] = drawing_state

    winners = get_current_winners(drawing_state)
    winner = winners.get(game_id)

    # Look up game name for the response
    game_name = None
    for item in drawing_state:
        if item["game"]["id"] == game_id:
            game_name = item["game"].get("name", "Unknown")
            break

    return jsonify({
        "ok": True,
        "game_id": game_id,
        "has_winner": found,
        "game_name": game_name,
        "winner_name": winner.get("name", "Unknown") if winner else None,
        "winner_badge": winner.get("badge_id", "") if winner else None,
    })


@main_bp.route("/drawing/entrants/<game_id>")
@login_required(api=True)
def drawing_entrants(game_id):
    """AJAX endpoint: return the shuffled entrant list for a game from drawing state."""
    if not is_valid_tte_id(game_id):
        return jsonify({"error": "Invalid game ID format"}), 400
    drawing_state = session.get(SK.DRAWING_STATE, [])
    not_here = set(session.get(SK.NOT_HERE, []))

    for item in drawing_state:
        if item["game"]["id"] == game_id:
            winner_index = item["winner_index"]
            entrants = []
            for i, entry in enumerate(item["shuffled"]):
                entrants.append({
                    "name": entry.get("name", entry.get("badge_id", "Unknown")),
                    "badge_id": entry.get("badge_id", ""),
                    "is_winner": i == winner_index,
                    "is_not_here": entry.get("badge_id", "") in not_here,
                    "position": i + 1,
                })
            return jsonify({"ok": True, "entrants": entrants})

    return jsonify({"error": "Game not found in drawing state"}), 404


@main_bp.route("/drawing/not-here", methods=["POST"])
@login_required
def mark_not_here():
    """Mark a person as 'not here' — permanently absent for this drawing."""
    drawing_state = _require_active_drawing()
    if isinstance(drawing_state, tuple):
        return drawing_state

    data = request.get_json(silent=True)
    if not data or "badge_id" not in data:
        return jsonify({"error": "Invalid request"}), 400

    badge_id = data["badge_id"]
    if not is_valid_badge_id(badge_id):
        return jsonify({"error": "Invalid badge ID format"}), 400
    not_here = session.get(SK.NOT_HERE, [])

    if badge_id in not_here:
        return jsonify({"error": "Already marked as not here"}), 400

    not_here.append(badge_id)
    session[SK.NOT_HERE] = not_here

    logger.info("Badge %s marked not-here", badge_id)

    # Dismiss warning if requested
    if data.get("dismiss_warning"):
        session[SK.NOT_HERE_WARNING_DISMISSED] = True

    # Auto-advance all unpicked-up games won by this person
    picked_up = set(session.get(SK.PICKED_UP, []))
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

    session[SK.DRAWING_STATE] = drawing_state

    return jsonify({
        "ok": True,
        "badge_id": badge_id,
        "advanced_games": advanced_games,
    })


@main_bp.route("/drawing/redraw-unclaimed", methods=["POST"])
@login_required
def redraw_all_unclaimed():
    """Redraw all unclaimed games with fresh shuffle."""
    drawing_state = session.get(SK.DRAWING_STATE)
    if not drawing_state:
        return jsonify({"error": "No active drawing"}), 400

    data = request.get_json(silent=True) or {}
    same_rules = data.get("same_rules", False)

    picked_up = set(session.get(SK.PICKED_UP, []))
    not_here_set = set(session.get(SK.NOT_HERE, []))
    premium_games = session.get(SK.PREMIUM_GAMES, [])

    # Determine unclaimed game IDs (have a winner or had one, not picked up)
    winners = get_current_winners(drawing_state)
    unclaimed_ids = set()
    original_winner_badges = set()
    for item in drawing_state:
        game_id = item["game"]["id"]
        if game_id not in picked_up and item["shuffled"]:
            unclaimed_ids.add(game_id)
            # Collect original first-draw winners (index 0) for exclusion
            if item["shuffled"]:
                badge = item["shuffled"][0].get("badge_id")
                if badge:
                    original_winner_badges.add(badge)

    if not unclaimed_ids:
        return jsonify({"error": "No unclaimed games to redraw"}), 400

    logger.info("Redrawing %d unclaimed games (same_rules=%s)", len(unclaimed_ids), same_rules)

    conflicts, auto_resolved = redraw_unclaimed(
        drawing_state, unclaimed_ids, not_here_set, original_winner_badges,
        same_rules=same_rules, premium_game_ids=premium_games,
    )

    session[SK.DRAWING_STATE] = drawing_state
    session[SK.SOLO_DISMISSED_GAMES] = []
    if conflicts:
        session[SK.DRAWING_CONFLICTS] = conflicts
    else:
        session[SK.DRAWING_CONFLICTS] = []
    if auto_resolved:
        session[SK.AUTO_RESOLVED] = auto_resolved
    else:
        session[SK.AUTO_RESOLVED] = []

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
@login_required
def push_to_tte():
    """Push win flags to TTE for all picked-up games."""
    drawing_state = session.get(SK.DRAWING_STATE)
    if not drawing_state:
        return jsonify({"error": "No active drawing"}), 400

    picked_up = set(session.get(SK.PICKED_UP, []))
    if not picked_up:
        return jsonify({"error": "No games marked as picked up"}), 400

    winners = get_current_winners(drawing_state)

    # Collect PlayToWin entry IDs for picked-up games
    entries_to_update = []
    for game_id in picked_up:
        winner = winners.get(game_id)
        if winner and winner.get("id"):
            entries_to_update.append({
                "playtowin_id": winner["id"],
                "game_id": game_id,
            })

    logger.info("Pushing %d winners to TTE", len(entries_to_update))
    client = _get_client()
    successes = []
    failures = []

    for entry in entries_to_update:
        try:
            client.update_playtowin(entry["playtowin_id"], {"win": 1})
            successes.append(entry["game_id"])
        except TTEAPIError as exc:
            if getattr(exc, 'status_code', None) in (401, 403):
                return _handle_api_json_error(exc, "push wins to TTE")
            logger.error("Failed to push win for game %s: %s", entry["game_id"], exc)
            failures.append({
                "game_id": entry["game_id"],
                "error": str(exc),
            })

    logger.info("TTE push complete: %d succeeded, %d failed", len(successes), len(failures))

    return jsonify({
        "ok": True,
        "total": len(entries_to_update),
        "successes": len(successes),
        "failures": failures,
    })


@main_bp.route("/drawing/export")
@login_required
def export_csv():
    """Export drawing results as a CSV file."""
    drawing_state = session.get(SK.DRAWING_STATE)
    if not drawing_state:
        flash("No active drawing to export.", "error")
        return redirect(url_for("main.games"))

    winners = get_current_winners(drawing_state)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Game", "Winner's Name", "Winner's Badge"])

    rows = []
    for item in drawing_state:
        game = item["game"]
        game_id = game["id"]
        winner = winners.get(game_id)

        rows.append({
            "game_name": game.get("name", "Unknown"),
            "winner_name": winner.get("name", "Unknown") if winner else "",
            "winner_badge": winner.get("badge_id", "") if winner else "",
        })

    rows.sort(key=lambda r: r["game_name"])

    for row in rows:
        writer.writerow([
            row["game_name"],
            row["winner_name"],
            row["winner_badge"],
        ])

    convention_name = session.get(SK.CONVENTION_NAME, "Drawing")
    safe_name = "".join(c if c.isalnum() or c in " -_" else "" for c in convention_name).strip().replace(" ", "_")
    filename = f"PawDrawing_{safe_name}_{date.today().isoformat()}.csv"

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
