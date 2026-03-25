"""Library Management game and person lookup routes."""

import logging

from flask import jsonify, render_template, request, session, url_for

from session_keys import SK
from tte_client import TTEAPIError

from . import library_bp
from routes.helpers import (
    _get_client,
    is_valid_tte_id,
    login_required,
)

logger = logging.getLogger(__name__)


def _handle_api_json_error(exc, action="complete this request"):
    """Handle TTEAPIError for JSON/AJAX endpoints."""
    if getattr(exc, "status_code", None) in (401, 403):
        logger.warning("API auth error during '%s': session cleared", action)
        session.clear()
        return jsonify({"error": "Session expired — please log in again."}), 401
    logger.error("API error during '%s': %s", action, exc)
    return jsonify({"error": f"Could not {action}: {exc}"}), 500


@library_bp.route("/game/<game_id>")
@login_required
def game_detail(game_id):
    """Game detail view — fresh data from TTE."""
    if not is_valid_tte_id(game_id):
        return jsonify({"error": "Invalid game ID"}), 400

    client = _get_client()
    try:
        game = client.get_library_game(game_id)
        checkouts = client.get_library_game_checkouts(game_id)
    except TTEAPIError as exc:
        return _handle_api_json_error(exc, "load game details")

    active_checkouts = [c for c in checkouts if not c.get("is_checked_in")]
    checkout_history = [c for c in checkouts if c.get("is_checked_in")]
    checkout_history.sort(key=lambda c: c.get("checkin_date", ""), reverse=True)

    # Get P2W entries if applicable
    p2w_entries = []
    if game.get("is_play_to_win"):
        try:
            p2w_entries = client.get_library_game_playtowins(game_id)
        except TTEAPIError:
            logger.warning("Failed to load P2W entries for game %s", game_id)

    return render_template(
        "library/game_detail.html",
        game=game,
        active_checkouts=active_checkouts,
        checkout_history=checkout_history[:20],
        p2w_entries=p2w_entries,
        p2w_entry_count=len(p2w_entries),
    )


@library_bp.route("/game-search")
@login_required(api=True)
def game_search():
    """AJAX: search games in the cached catalog."""
    query = request.args.get("q", "").strip().lower()
    if not query:
        return jsonify({"results": []})

    games = session.get(SK.CACHED_GAMES, [])
    results = []
    for game in games:
        name = (game.get("name") or "").lower()
        catalog = (game.get("catalog_number") or "").lower()
        if query in name or query in catalog:
            results.append({
                "id": game.get("id"),
                "name": game.get("name"),
                "catalog_number": game.get("catalog_number"),
                "is_checked_out": game.get("is_checked_out"),
                "is_play_to_win": game.get("is_play_to_win"),
                "is_in_circulation": game.get("is_in_circulation"),
            })
    results.sort(key=lambda g: g.get("name", ""))
    return jsonify({"results": results[:50]})


@library_bp.route("/person/<badge_number>")
@login_required
def person_detail(badge_number):
    """Person detail view — current checkouts and history."""
    if not badge_number or not badge_number.strip():
        return jsonify({"error": "Badge number is required"}), 400

    badge_number = badge_number.strip()
    library_id = session.get(SK.LIBRARY_ID)
    convention_id = session.get(SK.CONVENTION_ID)
    if not library_id:
        return jsonify({"error": "No library selected"}), 400

    # Get person name from cache
    person_cache = session.get(SK.PERSON_CACHE, {})
    person_info = person_cache.get(badge_number, {})
    person_name = person_info.get("name", badge_number)

    client = _get_client()

    # Fetch current checkouts (not checked in) for this person
    try:
        all_active = client.get_library_checkouts(library_id, checked_in=False)
    except TTEAPIError as exc:
        return _handle_api_json_error(exc, "load person checkouts")

    # Filter to this person's checkouts
    current_checkouts = [
        c for c in all_active
        if c.get("renter_name", "").lower() == person_name.lower()
        or c.get("badge_id") == person_info.get("badge_id")
    ]

    # Fetch checkout history
    try:
        all_checkouts = client.get_library_checkouts(library_id, checked_in=True)
    except TTEAPIError as exc:
        return _handle_api_json_error(exc, "load person history")

    checkout_history = [
        c for c in all_checkouts
        if c.get("renter_name", "").lower() == person_name.lower()
        or c.get("badge_id") == person_info.get("badge_id")
    ]
    checkout_history.sort(key=lambda c: c.get("checkin_date", ""), reverse=True)

    return render_template(
        "library/person_detail.html",
        person_name=person_name,
        badge_number=badge_number,
        current_checkouts=current_checkouts,
        checkout_history=checkout_history[:20],
    )


@library_bp.route("/person-search")
@login_required(api=True)
def person_search():
    """AJAX: search people in the local badge cache."""
    query = request.args.get("q", "").strip().lower()
    if not query:
        return jsonify({"results": []})

    person_cache = session.get(SK.PERSON_CACHE, {})
    results = []
    for badge_number, info in person_cache.items():
        name = (info.get("name") or "").lower()
        if query in name or query in badge_number.lower():
            results.append({
                "badge_number": badge_number,
                "name": info.get("name"),
                "badge_id": info.get("badge_id"),
            })
    results.sort(key=lambda p: p.get("name", ""))
    return jsonify({"results": results[:50]})
