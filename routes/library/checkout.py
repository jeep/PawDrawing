"""Library Management checkout and check-in routes."""

import logging
import time

from flask import flash, jsonify, redirect, render_template, request, session, url_for

from session_keys import SK
from tte_client import TTEAPIError

from . import library_bp
from routes.helpers import (
    _get_client,
    _handle_api_error,
    is_valid_badge_id,
    is_valid_tte_id,
    login_required,
)

logger = logging.getLogger(__name__)


def _handle_api_json_error(exc, action="complete this request"):
    """Handle TTEAPIError for JSON/AJAX endpoints."""
    status = getattr(exc, "status_code", None)
    if status in (401, 403):
        logger.warning("API auth error during '%s': session cleared", action)
        session.clear()
        return jsonify({"error": "Session expired — please log in again."}), 401
    if status == 429:
        logger.warning("Rate limited during '%s'", action)
        return jsonify({"error": "Rate limit reached — please wait a moment and try again."}), 429
    logger.error("API error during '%s': %s", action, exc)
    return jsonify({"error": f"Could not {action}: {exc}"}), 500


def _update_game_cache(game_id, **updates):
    """Update a single game's fields in the cached game list."""
    games = session.get(SK.CACHED_GAMES, [])
    for game in games:
        if game.get("id") == game_id:
            game.update(updates)
            break
    session[SK.CACHED_GAMES] = games


def _get_person_name(badge_number):
    """Look up a person's name from the local badge cache."""
    cache = session.get(SK.PERSON_CACHE, {})
    entry = cache.get(str(badge_number))
    return entry.get("name") if entry else None


def _cache_person(badge_number, name, badge_id=None, user_id=None):
    """Store a badge-number-to-person mapping in the session cache."""
    cache = session.get(SK.PERSON_CACHE) or {}
    cache[str(badge_number)] = {
        "name": name,
        "badge_id": badge_id,
        "user_id": user_id,
    }
    session[SK.PERSON_CACHE] = cache


@library_bp.route("/badge-lookup")
@login_required(api=True)
def badge_lookup():
    """AJAX: look up a person by badge number."""
    badge_number = request.args.get("badge_number", "").strip()
    if not badge_number:
        return jsonify({"error": "Badge number is required"}), 400

    # Check local cache first
    cached_name = _get_person_name(badge_number)
    if cached_name:
        cache = session.get(SK.PERSON_CACHE, {})
        entry = cache[str(badge_number)]
        return jsonify({
            "name": cached_name,
            "badge_id": entry.get("badge_id"),
            "source": "cache",
        })

    # Look up via TTE convention badge API
    convention_id = session.get(SK.CONVENTION_ID)
    if not convention_id:
        return jsonify({"error": "No convention selected — enter name manually"}), 400

    client = _get_client()
    try:
        badges = client.search_badges(
            convention_id, badge_number, query_field="badge_number"
        )
    except TTEAPIError as exc:
        return _handle_api_json_error(exc, "look up badge")

    if not badges:
        return jsonify({"error": "Badge not found"}), 404

    badge = badges[0]
    name = badge.get("name_full", badge.get("name", "Unknown"))
    badge_id = badge.get("id")
    user_id = badge.get("user_id")

    _cache_person(badge_number, name, badge_id, user_id)

    return jsonify({
        "name": name,
        "badge_id": badge_id,
        "source": "tte",
    })


@library_bp.route("/active-checkout")
@login_required(api=True)
def active_checkout():
    """AJAX: get the active checkout for a game (for check-in flow)."""
    game_id = request.args.get("game_id", "").strip()
    if not game_id or not is_valid_tte_id(game_id):
        return jsonify({"error": "Invalid game ID"}), 400

    client = _get_client()
    try:
        checkouts = client.get_library_game_checkouts(game_id, checked_in=False)
    except TTEAPIError as exc:
        return _handle_api_json_error(exc, "look up active checkout")

    if not checkouts:
        return jsonify({"error": "No active checkout for this game"}), 404

    checkout = checkouts[0]
    return jsonify({
        "checkout_id": checkout.get("id"),
        "renter_name": checkout.get("renter_name"),
        "date_created": checkout.get("date_created"),
        "game_id": game_id,
    })


@library_bp.route("/checkout", methods=["POST"])
@login_required(api=True)
def create_checkout():
    """AJAX: create a game checkout."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid request"}), 400

    game_id = data.get("game_id", "").strip()
    renter_name = data.get("renter_name", "").strip()
    badge_number = data.get("badge_number", "").strip()

    if not game_id or not is_valid_tte_id(game_id):
        return jsonify({"error": "Invalid game ID"}), 400
    if not renter_name:
        return jsonify({"error": "Renter name is required"}), 400

    library_id = session.get(SK.LIBRARY_ID)
    if not library_id:
        return jsonify({"error": "No library selected"}), 400

    convention_id = session.get(SK.CONVENTION_ID)

    # Get badge_id from person cache if available
    badge_id = None
    if badge_number:
        cache = session.get(SK.PERSON_CACHE, {})
        entry = cache.get(str(badge_number))
        if entry:
            badge_id = entry.get("badge_id")

    # Verify game is available before checkout (FR-CAT-04)
    client = _get_client()
    try:
        fresh_game = client.get_library_game(game_id)
    except TTEAPIError as exc:
        return _handle_api_json_error(exc, "verify game availability")

    if fresh_game.get("is_checked_out"):
        _update_game_cache(game_id, is_checked_out=1)
        return jsonify({"error": "This game is already checked out."}), 409
    if not fresh_game.get("is_in_circulation"):
        return jsonify({"error": "This game is not in circulation."}), 409

    try:
        result = client.create_checkout(
            library_id, game_id, renter_name,
            convention_id=convention_id, badge_id=badge_id,
        )
    except TTEAPIError as exc:
        return _handle_api_json_error(exc, "create checkout")

    # Update local cache
    _update_game_cache(game_id, is_checked_out=1)

    # Cache the person for future lookups
    if badge_number and renter_name:
        _cache_person(badge_number, renter_name, badge_id)

    # Check if P2W game — return flag so UI can prompt for entry
    games = session.get(SK.CACHED_GAMES, [])
    is_p2w = False
    for game in games:
        if game.get("id") == game_id:
            is_p2w = bool(game.get("is_play_to_win"))
            break

    logger.info("Checkout created: game=%s renter=%s", game_id, renter_name)
    return jsonify({
        "success": True,
        "checkout_id": result.get("id"),
        "is_play_to_win": is_p2w,
    })


@library_bp.route("/checkin", methods=["POST"])
@login_required(api=True)
def checkin():
    """AJAX: check in a game (return to library)."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid request"}), 400

    checkout_id = data.get("checkout_id", "").strip()
    if not checkout_id or not is_valid_tte_id(checkout_id):
        return jsonify({"error": "Invalid checkout ID"}), 400

    game_id = data.get("game_id", "").strip()

    client = _get_client()
    try:
        client.checkin_game(checkout_id)
    except TTEAPIError as exc:
        return _handle_api_json_error(exc, "check in game")

    # Update local cache
    if game_id and is_valid_tte_id(game_id):
        _update_game_cache(game_id, is_checked_out=0)

    # Check if P2W game
    is_p2w = False
    if game_id:
        games = session.get(SK.CACHED_GAMES, [])
        for game in games:
            if game.get("id") == game_id:
                is_p2w = bool(game.get("is_play_to_win"))
                break

    logger.info("Game checked in: checkout=%s game=%s", checkout_id, game_id)
    return jsonify({
        "success": True,
        "is_play_to_win": is_p2w,
    })


@library_bp.route("/p2w-entry", methods=["POST"])
@login_required(api=True)
def create_p2w_entry():
    """AJAX: create Play-to-Win drawing entries for one or more people."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid request"}), 400

    game_id = data.get("game_id", "").strip()
    entrants = data.get("entrants", [])

    if not game_id or not is_valid_tte_id(game_id):
        return jsonify({"error": "Invalid game ID"}), 400
    if not entrants:
        return jsonify({"error": "At least one entrant is required"}), 400

    library_id = session.get(SK.LIBRARY_ID)
    convention_id = session.get(SK.CONVENTION_ID)
    if not library_id:
        return jsonify({"error": "No library selected"}), 400

    client = _get_client()

    # Check for existing P2W entries to prevent duplicates (FR-P2W-06)
    try:
        existing_entries = client.get_library_game_playtowins(game_id)
    except TTEAPIError:
        existing_entries = []
    existing_names = {
        (e.get("name") or e.get("renter_name") or "").lower()
        for e in existing_entries
    }

    created = []
    skipped = []
    errors = []

    for entrant in entrants:
        name = entrant.get("name", "").strip()
        badge_id = entrant.get("badge_id")
        if not name:
            continue
        if name.lower() in existing_names:
            skipped.append({"name": name, "reason": "already entered"})
            continue
        try:
            result = client.create_playtowin_entry(
                library_id, game_id, name,
                convention_id=convention_id, badge_id=badge_id,
            )
            created.append({"name": name, "id": result.get("id")})
            existing_names.add(name.lower())
        except TTEAPIError as exc:
            logger.warning("Failed P2W entry for %s on game %s: %s", name, game_id, exc)
            errors.append({"name": name, "error": str(exc)})

    # Update play group associations
    if len(created) > 1:
        _update_play_groups(created)

    logger.info("P2W entries created: %d success, %d skipped, %d failed for game %s",
                len(created), len(skipped), len(errors), game_id)
    return jsonify({
        "success": True,
        "created": created,
        "skipped": skipped,
        "errors": errors,
    })


def _update_play_groups(entrants):
    """Record co-entry associations for smart suggestions."""
    groups = session.get(SK.PLAY_GROUPS) or {}
    names = [e["name"] for e in entrants]
    for name in names:
        existing = set(groups.get(name, []))
        for other in names:
            if other != name:
                existing.add(other)
        groups[name] = list(existing)
    session[SK.PLAY_GROUPS] = groups


@library_bp.route("/p2w-suggestions")
@login_required(api=True)
def p2w_suggestions():
    """AJAX: get smart P2W entry suggestions for a person."""
    name = request.args.get("name", "").strip()
    if not name:
        return jsonify({"suggestions": []})

    groups = session.get(SK.PLAY_GROUPS, {})
    suggestions = groups.get(name, [])

    # Enrich with cached badge info
    person_cache = session.get(SK.PERSON_CACHE, {})
    enriched = []
    for suggestion_name in suggestions:
        badge_id = None
        for badge_num, info in person_cache.items():
            if info.get("name") == suggestion_name:
                badge_id = info.get("badge_id")
                break
        enriched.append({"name": suggestion_name, "badge_id": badge_id})

    return jsonify({"suggestions": enriched})


@library_bp.route("/reset-checkout-time", methods=["POST"])
@login_required(api=True)
def reset_checkout_time():
    """AJAX: reset a checkout's timestamp (§12 Q1)."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid request"}), 400

    checkout_id = data.get("checkout_id", "").strip()
    if not checkout_id or not is_valid_tte_id(checkout_id):
        return jsonify({"error": "Invalid checkout ID"}), 400

    client = _get_client()
    try:
        client.reset_checkout_time(checkout_id)
    except TTEAPIError as exc:
        return _handle_api_json_error(exc, "reset checkout time")

    logger.info("Checkout time reset: %s", checkout_id)
    return jsonify({"success": True})
