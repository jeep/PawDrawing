import logging
import time
import uuid
from datetime import datetime, timezone

from flask import flash, jsonify, redirect, render_template, request, session, url_for

import shared_state
from data_processing import apply_ejections, group_entries_by_game, process_entries
from routes.suspicious import (
    check_long_checkouts,
    check_partner_patterns,
    flag_suspicious_games,
)
from session_keys import SK
from tte_client import TTEAPIError

from . import main_bp
from .helpers import (
    _get_client,
    _handle_api_error,
    _handle_api_json_error,
    _parse_eject_payload,
    check_checkout_privilege,
    is_valid_badge_id,
    is_valid_tte_id,
    login_required,
)

logger = logging.getLogger(__name__)

# Keys stored in library-scoped shared state (visible across all devices)
_SHARED_KEYS = (
    SK.EJECTED_ENTRIES,
    SK.NOTIFICATIONS,
    SK.LIBRARY_SETTINGS,
    SK.PERSON_CACHE,
    SK.PLAY_GROUPS,
    SK.CHECKOUT_MAP,
    SK.MANUAL_ENTRY_IDS,
)

# Dict-type keys that use merge semantics to avoid losing concurrent writes
_MERGE_KEYS = {SK.PERSON_CACHE, SK.PLAY_GROUPS, SK.CHECKOUT_MAP}


# ── Shared state helpers ──────────────────────────────────────────────

def _load_shared_state():
    """Load library-scoped shared state into the session.

    Called on page loads to pick up changes from other devices.
    Overwrites session values for shared keys with the authoritative
    shared state.  Keys not present in the shared file are left
    untouched (preserves test setups that inject session data directly).
    """
    library_id = session.get(SK.LIBRARY_ID)
    if not library_id:
        return
    state = shared_state.load(library_id)
    for key in _SHARED_KEYS:
        if key in state:
            session[key] = state[key]


def _save_shared(key, value):
    """Write a value to both session and library-scoped shared state.

    For dict-type keys (person_cache, play_groups), uses merge semantics
    to avoid overwriting entries added concurrently by other devices.
    """
    session[key] = value
    library_id = session.get(SK.LIBRARY_ID)
    if not library_id:
        return
    if key in _MERGE_KEYS and isinstance(value, dict):
        shared_state.merge_dict(library_id, key, value)
    else:
        shared_state.update(library_id, key, value)


# ── Game cache helpers ────────────────────────────────────────────────

def _update_game_cache(game_id, **updates):
    """Update a game in the session cache and broadcast checkout changes."""
    games = session.get(SK.CACHED_GAMES, [])
    for game in games:
        if game.get("id") == game_id:
            game.update(updates)
            break
    session[SK.CACHED_GAMES] = games

    # Broadcast checkout status changes via shared state
    if "is_checked_out" in updates:
        checkout_map = session.get(SK.CHECKOUT_MAP) or {}
        if updates.get("is_checked_out"):
            checkout_map[game_id] = {
                "renter": updates.get("_renter_name", ""),
                "checkout_id": updates.get("_checkout_id", ""),
            }
        else:
            checkout_map[game_id] = None  # marks as available
        _save_shared(SK.CHECKOUT_MAP, checkout_map)


def _get_person_name(badge_number):
    """Look up a person's name from the session cache."""
    cache = session.get(SK.PERSON_CACHE, {})
    entry = cache.get(str(badge_number))
    return entry.get("name") if entry else None


def _cache_person(badge_number, name, badge_id, user_id=None):
    """Cache a person's info for future lookups."""
    cache = session.get(SK.PERSON_CACHE) or {}
    cache[str(badge_number)] = {
        "name": name,
        "badge_id": badge_id,
        "user_id": user_id,
    }
    _save_shared(SK.PERSON_CACHE, cache)


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
    _save_shared(SK.PLAY_GROUPS, groups)


def _add_notification(ntype, message, details=None):
    """Add a notification to the session."""
    notifications = session.get(SK.NOTIFICATIONS) or []
    notifications.append({
        "id": str(uuid.uuid4()),
        "type": ntype,
        "message": message,
        "dismissed": False,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "details": details,
    })
    _save_shared(SK.NOTIFICATIONS, notifications)


def _detect_non_p2w_games():
    """Check for non-P2W games and create notification (FR-CAT-07)."""
    games = session.get(SK.CACHED_GAMES, [])
    non_p2w = [
        g for g in games
        if not g.get("is_play_to_win") and g.get("is_in_circulation")
    ]
    if not non_p2w:
        return
    names = [g.get("name", "Unknown") for g in non_p2w]
    count = len(non_p2w)
    word = "game" if count == 1 else "games"
    verb = "is" if count == 1 else "are"
    _add_notification("non_p2w",
                      f"{count} {word} in this library {verb} not marked Play-to-Win.",
                      details=names)


def _run_suspicious_check(client, library_id):
    """Run suspicious checkout detection and generate notifications."""
    games = session.get(SK.CACHED_GAMES, [])
    lib_settings = session.get(SK.LIBRARY_SETTINGS) or {}
    alert_hours = lib_settings.get("checkout_alert_hours", 3)
    try:
        active = client.get_library_checkouts(library_id, checked_in=False)
    except TTEAPIError:
        active = []

    premium_ids = set(session.get(SK.PREMIUM_GAMES, []))
    suspicious = check_long_checkouts(
        games,
        active,
        premium_ids=premium_ids,
        alert_hours=alert_hours,
    )

    play_groups = session.get(SK.PLAY_GROUPS, {})
    try:
        history = client.get_library_checkouts(library_id, checked_in=True)
    except TTEAPIError:
        history = []

    patterns = check_partner_patterns(
        active + history,
        play_groups,
        games,
        alert_hours=alert_hours,
    )
    flag_suspicious_games(games, suspicious, patterns)
    session[SK.CACHED_GAMES] = games

    if suspicious:
        names = [f"{s['game_name']} ({s['renter_name']}, {s['elapsed_hours']}h)"
                 for s in suspicious]
        count = len(suspicious)
        word = "game" if count == 1 else "games"
        _add_notification("warning",
                          f"{count} {word} checked out beyond threshold.",
                          details=names)

    if patterns:
        descs = [f"{p['person_a']} → {p['person_b']} on game {p['game_id'][:8]}…"
                 for p in patterns]
        count = len(patterns)
        word = "pattern" if count == 1 else "patterns"
        _add_notification("alert",
                          f"{count} suspicious partner {word} detected.",
                          details=descs)


def _parse_component_checks(raw_checks):
    """Normalize component-check state from session."""
    if not isinstance(raw_checks, dict):
        return {}
    parsed = {}
    for game_id, record in raw_checks.items():
        if not isinstance(record, dict):
            continue
        parsed[game_id] = {
            "checked": bool(record.get("checked")),
            "volunteer": (record.get("volunteer") or "").strip(),
            "timestamp": (record.get("timestamp") or "").strip(),
        }
    return parsed


def _format_component_timestamp(raw_timestamp):
    """Render ISO timestamps into a compact local-friendly display string."""
    if not raw_timestamp:
        return ""
    try:
        dt = datetime.fromisoformat(str(raw_timestamp).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return ""
    return dt.strftime("%Y-%m-%d %H:%M")


def _is_component_game_checked_out(game, checkout_map):
    """Determine checked-out state using either local cache or shared checkout map."""
    game_id = game.get("id", "")
    checkout_info = checkout_map.get(game_id)
    return bool(game.get("is_checked_out") or checkout_info is not None), checkout_info


# ── Mode switching ────────────────────────────────────────────────────

@main_bp.route("/games/mode", methods=["POST"])
@login_required(api=True)
def switch_mode():
    """AJAX: switch app mode (management/players/prep/drawing)."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid request"}), 400
    mode = data.get("mode", "management")
    if mode not in ("management", "players", "prep", "drawing"):
        mode = "management"
    session[SK.APP_MODE] = mode
    logger.info("Mode switched to: %s", mode)

    redirect_url = None
    if mode == "players":
        redirect_url = url_for("main.players")
    elif mode == "prep":
        redirect_url = url_for("main.drawing_prep")
    elif mode == "drawing":
        redirect_url = url_for("main.drawing_results")

    return jsonify({"ok": True, "mode": mode, "redirect": redirect_url})


@main_bp.route("/games")
@login_required
def games():
    """Load games and entries, process, and display."""
    library_id = session.get(SK.LIBRARY_ID)
    convention_id = session.get(SK.CONVENTION_ID)
    if not library_id:
        flash("Please select a convention first.", "error")
        return redirect(url_for("main.convention_select"))

    # Sync shared state from other devices
    _load_shared_state()

    refresh = request.args.get("refresh") == "1"
    all_games = session.get(SK.CACHED_GAMES)
    entries = session.get(SK.CACHED_ENTRIES)

    if refresh or all_games is None or entries is None:
        client = _get_client()

        try:
            all_games = client.get_library_games(library_id)
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

        # Enrich with renter info for checked-out games
        try:
            active = client.get_library_checkouts(library_id, checked_in=False)
            checkout_map = {}
            shared_co_map = {}
            for co in active:
                gid = co.get("librarygame_id")
                if gid:
                    checkout_map[gid] = {
                        "_renter_name": co.get("renter_name", "Unknown"),
                        "_checkout_id": co.get("id", ""),
                    }
                    shared_co_map[gid] = {
                        "renter": co.get("renter_name", "Unknown"),
                        "checkout_id": co.get("id", ""),
                    }
            for g in all_games:
                info = checkout_map.get(g.get("id"), {})
                g["_renter_name"] = info.get("_renter_name", g.get("_renter_name", ""))
                g["_checkout_id"] = info.get("_checkout_id", g.get("_checkout_id", ""))
            # Seed shared checkout map so other devices see current state
            _save_shared(SK.CHECKOUT_MAP, shared_co_map)
        except TTEAPIError:
            logger.warning("Could not fetch active checkouts for renter enrichment")

        # Cache games and entries in session for reuse
        session[SK.CACHED_GAMES] = all_games
        session[SK.CACHED_ENTRIES] = entries
        session[SK.TTE_REFRESHED] = True
        logger.info("Loaded %d games and %d entries for library %s",
                    len(all_games), len(entries), library_id)

        # Run suspicious checkout detection on refresh
        _run_suspicious_check(client, library_id)

        # Check for non-P2W games
        _detect_non_p2w_games()

        # If caller asked to return to a different page after refresh, redirect
        ret = request.args.get("ret")
        if ret == "prep":
            return redirect(url_for("main.drawing_prep"))

    # Default mode to management
    app_mode = session.get(SK.APP_MODE, "management")
    if app_mode not in ("management", "drawing", "redraw"):
        app_mode = "management"

    ejected_entries = session.get(SK.EJECTED_ENTRIES, [])
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

    premium_games = session.get(SK.PREMIUM_GAMES, [])

    data_loaded_at = datetime.now().strftime("%-I:%M %p")

    unique_participants = len({e["badge_id"] for e in filtered})

    # Notification count for bell badge
    notifications = session.get(SK.NOTIFICATIONS, [])
    unread_count = sum(1 for n in notifications if not n.get("dismissed"))

    # Checkout alert threshold
    lib_settings = session.get(SK.LIBRARY_SETTINGS) or {}
    alert_hours = lib_settings.get("checkout_alert_hours", 3)

    return render_template(
        "games.html",
        game_data=game_data,
        total_games=len(all_games),
        total_entries=len(filtered),
        unique_participants=unique_participants,
        convention_name=session.get(SK.CONVENTION_NAME) or session.get(SK.LIBRARY_NAME, ""),
        library_name=session.get(SK.LIBRARY_NAME, ""),
        premium_games=premium_games,
        ejected_entries=ejected_entries,
        ejected_badges=ejected_badges,
        ejected_per_game=ejected_per_game,
        data_loaded_at=data_loaded_at,
        app_mode=app_mode,
        notification_count=unread_count,
        alert_hours=alert_hours,
    )


@main_bp.route("/games/players")
@login_required
def players():
    """Player management page — lists all players with game counts and removal controls."""
    library_id = session.get(SK.LIBRARY_ID)
    if not library_id:
        flash("Please select a convention first.", "error")
        return redirect(url_for("main.convention_select"))

    # Sync shared state from other devices
    _load_shared_state()

    # Use cached data from the games page to avoid redundant API calls
    all_games = session.get(SK.CACHED_GAMES)
    entries = session.get(SK.CACHED_ENTRIES)

    if all_games is None or entries is None:
        flash("Please load the games page first.", "info")
        return redirect(url_for("main.games"))

    manual_entry_ids = set(session.get(SK.MANUAL_ENTRY_IDS, []))

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
            "entry_id": entry.get("id"),
            "is_manual": entry.get("id") in manual_entry_ids,
        })

    player_list = sorted(players_map.values(), key=lambda p: p["name"].lower())

    # Build removed set from session
    ejected_entries = session.get(SK.EJECTED_ENTRIES, [])
    removed_all = set()
    removed_per_game = {}
    for badge_id, game_id in ejected_entries:
        if game_id == "*":
            removed_all.add(badge_id)
        else:
            removed_per_game.setdefault(badge_id, set()).add(game_id)

    p2w_games = [
        {"id": g.get("id"), "name": g.get("name", "Unknown")}
        for g in all_games
        if g.get("is_play_to_win")
    ]
    p2w_games.sort(key=lambda g: g["name"].lower())

    return render_template(
        "players.html",
        player_list=player_list,
        total_players=len(player_list),
        total_entries=len(entries),
        total_games=len(all_games),
        convention_name=session.get(SK.CONVENTION_NAME) or session.get(SK.LIBRARY_NAME, ""),
        removed_all=removed_all,
        removed_per_game=removed_per_game,
        p2w_games=p2w_games,
    )


@main_bp.route("/games/manual-entry", methods=["POST"])
@login_required(api=True)
def add_manual_entry():
    """AJAX: add a manual Play-to-Win entry for a specific game."""
    data = request.get_json(silent=True) or {}

    game_id = (data.get("game_id") or "").strip()
    badge_number = (data.get("badge_number") or "").strip()
    name = (data.get("name") or "").strip()

    if not game_id or not is_valid_tte_id(game_id):
        return jsonify({"error": "Invalid game ID"}), 400
    if not badge_number:
        return jsonify({"error": "Badge ID is required"}), 400
    if not name:
        return jsonify({"error": "Name is required"}), 400

    library_id = session.get(SK.LIBRARY_ID)
    if not library_id:
        return jsonify({"error": "No library selected"}), 400

    cache = session.get(SK.PERSON_CACHE, {})
    person = cache.get(str(badge_number))
    if not person or not person.get("badge_id"):
        return jsonify({"error": "Badge not found. Please verify badge ID first."}), 400

    badge_id = person.get("badge_id")
    cached_entries = session.get(SK.CACHED_ENTRIES, []) or []
    existing = [
        e for e in cached_entries
        if e.get("librarygame_id") == game_id and e.get("badge_id") == badge_id
    ]
    if existing:
        return jsonify({"error": "This player is already entered for that game."}), 409

    convention_id = session.get(SK.CONVENTION_ID)
    client = _get_client()
    try:
        created = client.create_playtowin_entry(
            library_id,
            game_id,
            name,
            convention_id=convention_id,
            badge_id=badge_id,
        )
    except TTEAPIError as exc:
        return _handle_api_json_error(exc, "add manual Play-to-Win entry")

    entry_id = created.get("id")
    new_entry = {
        "id": entry_id,
        "librarygame_id": game_id,
        "badge_id": badge_id,
        "name": name,
    }
    session[SK.CACHED_ENTRIES] = cached_entries + [new_entry]

    manual_ids = list(session.get(SK.MANUAL_ENTRY_IDS, []))
    if entry_id and entry_id not in manual_ids:
        manual_ids.append(entry_id)
    _save_shared(SK.MANUAL_ENTRY_IDS, manual_ids)

    logger.info("Manual P2W entry added: game=%s badge=%s entry=%s", game_id, badge_id, entry_id)
    return jsonify({"ok": True, "entry_id": entry_id})


@main_bp.route("/games/manual-entry/<entry_id>", methods=["DELETE"])
@login_required(api=True)
def remove_manual_entry(entry_id):
    """AJAX: remove a manual Play-to-Win entry by ID."""
    if not entry_id or not is_valid_tte_id(entry_id):
        return jsonify({"error": "Invalid entry ID"}), 400

    manual_ids = set(session.get(SK.MANUAL_ENTRY_IDS, []))
    if entry_id not in manual_ids:
        return jsonify({"error": "Entry is not tracked as manual"}), 404

    client = _get_client()
    try:
        client.delete_playtowin(entry_id)
    except TTEAPIError as exc:
        return _handle_api_json_error(exc, "remove manual Play-to-Win entry")

    cached_entries = session.get(SK.CACHED_ENTRIES, []) or []
    session[SK.CACHED_ENTRIES] = [e for e in cached_entries if e.get("id") != entry_id]

    updated_manual_ids = [mid for mid in manual_ids if mid != entry_id]
    _save_shared(SK.MANUAL_ENTRY_IDS, updated_manual_ids)

    logger.info("Manual P2W entry removed: %s", entry_id)
    return jsonify({"ok": True})


@main_bp.route("/games/prep")
@login_required
def drawing_prep():
    """Drawing Prep page — pre-drawing checklist with component check and suspicious activity."""
    library_id = session.get(SK.LIBRARY_ID)
    if not library_id:
        flash("Please select a convention first.", "error")
        return redirect(url_for("main.convention_select"))

    # Sync shared state from other devices
    _load_shared_state()

    all_games = session.get(SK.CACHED_GAMES)
    entries = session.get(SK.CACHED_ENTRIES)
    has_data = all_games is not None and entries is not None

    # Component check: inspection checklist separate from checkout status.
    component_items = []
    inspected_count = 0
    checked_out_count = 0
    if all_games:
        checkout_map = session.get(SK.CHECKOUT_MAP, {})
        component_checks = _parse_component_checks(session.get(SK.COMPONENT_CHECKS, {}))
        for g in all_games:
            if not g.get("is_play_to_win"):
                continue
            gid = g.get("id", "")
            is_out, co_info = _is_component_game_checked_out(g, checkout_map)
            if is_out:
                checked_out_count += 1
            check_record = component_checks.get(gid, {})
            checked = bool(check_record.get("checked"))
            if checked:
                inspected_count += 1
            renter = (co_info or {}).get("renter") or g.get("_renter_name", "Unknown")
            checkout_id = (co_info or {}).get("checkout_id") or g.get("_checkout_id", "")
            component_items.append({
                "id": gid,
                "name": g.get("name", "Unknown"),
                "is_checked_out": is_out,
                "renter": renter if is_out else "",
                "checkout_id": checkout_id,
                "checked": checked,
                "volunteer": check_record.get("volunteer", ""),
                "timestamp": check_record.get("timestamp", ""),
                "timestamp_display": _format_component_timestamp(check_record.get("timestamp", "")),
            })

    component_items.sort(key=lambda item: item["name"].lower())
    total_component_games = len(component_items)
    remaining_component_checks = max(total_component_games - inspected_count, 0)

    # Suspicious activity: gather notifications
    notifications = session.get(SK.NOTIFICATIONS, [])
    suspicious_alerts = [n for n in notifications if n.get("type") in ("warning", "alert") and not n.get("dismissed")]

    # Ejection summary
    ejected_entries = session.get(SK.EJECTED_ENTRIES, [])
    ejected_all_count = sum(1 for _, gid in ejected_entries if gid == "*")
    ejected_game_count = sum(1 for _, gid in ejected_entries if gid != "*")

    # Stats
    total_games = len(all_games) if all_games else 0
    total_entries = len(entries) if entries else 0
    unique_participants = len({e["badge_id"] for e in entries}) if entries else 0
    zero_entry_games = 0
    if all_games and entries:
        game_ids_with_entries = {e.get("librarygame_id") for e in entries}
        zero_entry_games = sum(
            1 for g in all_games
            if g.get("is_play_to_win") and g.get("id") not in game_ids_with_entries
        )

    # Mark prep as completed
    session[SK.PREP_COMPLETED] = True

    convention_name = session.get(SK.CONVENTION_NAME) or session.get(SK.LIBRARY_NAME, "")

    return render_template(
        "drawing_prep.html",
        convention_name=convention_name,
        has_data=has_data,
        component_items=component_items,
        total_component_games=total_component_games,
        inspected_count=inspected_count,
        remaining_component_checks=remaining_component_checks,
        checked_out_count=checked_out_count,
        suspicious_alerts=suspicious_alerts,
        ejected_all_count=ejected_all_count,
        ejected_game_count=ejected_game_count,
        total_games=total_games,
        total_entries=total_entries,
        unique_participants=unique_participants,
        zero_entry_games=zero_entry_games,
    )


@main_bp.route("/games/component-check", methods=["POST"])
@login_required(api=True)
def mark_component_check():
    """AJAX: mark a game's physical component inspection as complete."""
    data = request.get_json(silent=True) or {}
    game_id = (data.get("game_id") or "").strip()
    volunteer = (data.get("volunteer") or "").strip()

    if not game_id or not is_valid_tte_id(game_id):
        return jsonify({"error": "Invalid game ID"}), 400
    if not volunteer:
        return jsonify({"error": "Volunteer name is required"}), 400

    cached_games = session.get(SK.CACHED_GAMES, [])
    game = next((g for g in cached_games if g.get("id") == game_id and g.get("is_play_to_win")), None)
    if not game:
        return jsonify({"error": "Game not found"}), 404

    checkout_map = session.get(SK.CHECKOUT_MAP, {})
    is_out, _ = _is_component_game_checked_out(game, checkout_map)
    if is_out:
        return jsonify({"error": "Game must be checked in before inspection"}), 409

    checks = _parse_component_checks(session.get(SK.COMPONENT_CHECKS, {}))
    timestamp = datetime.now(timezone.utc).isoformat()
    checks[game_id] = {
        "checked": True,
        "volunteer": volunteer,
        "timestamp": timestamp,
    }
    session[SK.COMPONENT_CHECKS] = checks
    return jsonify({
        "ok": True,
        "game_id": game_id,
        "volunteer": volunteer,
        "timestamp": timestamp,
        "timestamp_display": _format_component_timestamp(timestamp),
    })


@main_bp.route("/games/component-uncheck", methods=["POST"])
@login_required(api=True)
def unmark_component_check():
    """AJAX: clear a game's physical component inspection marker."""
    data = request.get_json(silent=True) or {}
    game_id = (data.get("game_id") or "").strip()

    if not game_id or not is_valid_tte_id(game_id):
        return jsonify({"error": "Invalid game ID"}), 400

    checks = _parse_component_checks(session.get(SK.COMPONENT_CHECKS, {}))
    if game_id not in checks:
        return jsonify({"error": "Inspection record not found"}), 404

    checks.pop(game_id, None)
    session[SK.COMPONENT_CHECKS] = checks
    return jsonify({"ok": True, "game_id": game_id})


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
    if any(not is_valid_tte_id(gid) for gid in game_ids):
        return jsonify({"error": "Invalid game ID format"}), 400

    session[SK.PREMIUM_GAMES] = game_ids
    return jsonify({"ok": True, "count": len(game_ids)})


@main_bp.route("/games/eject", methods=["POST"])
@login_required
def eject_player():
    """AJAX endpoint: eject a player from the drawing."""
    result = _parse_eject_payload()
    if isinstance(result[1], int):
        return result
    badge_id, game_id = result

    ejected = session.get(SK.EJECTED_ENTRIES, [])

    # Check for duplicates
    for b, g in ejected:
        if b == badge_id and g == game_id:
            return jsonify({"error": "Already ejected"}), 409

    # If ejecting from all games, remove any per-game ejections for this badge
    if game_id == "*":
        ejected = [[b, g] for b, g in ejected if b != badge_id]

    ejected.append([badge_id, game_id])
    _save_shared(SK.EJECTED_ENTRIES, ejected)
    logger.info("Player %s ejected from %s", badge_id, game_id if game_id != "*" else "all games")
    return jsonify({"ok": True, "count": len(ejected)})


@main_bp.route("/games/uneject", methods=["POST"])
@login_required
def uneject_player():
    """AJAX endpoint: undo an ejection."""
    result = _parse_eject_payload()
    if isinstance(result[1], int):
        return result
    badge_id, game_id = result

    ejected = session.get(SK.EJECTED_ENTRIES, [])
    updated = [[b, g] for b, g in ejected if not (b == badge_id and g == game_id)]

    if len(updated) == len(ejected):
        return jsonify({"error": "Ejection not found"}), 404

    _save_shared(SK.EJECTED_ENTRIES, updated)
    return jsonify({"ok": True, "count": len(updated)})


@main_bp.route("/games/entrants/<game_id>")
@login_required(api=True)
def get_entrants(game_id):
    """AJAX endpoint: return entrants for a specific game."""
    if not is_valid_tte_id(game_id):
        return jsonify({"error": "Invalid game ID format"}), 400
    library_id = session.get(SK.LIBRARY_ID)
    if not library_id:
        return jsonify({"error": "No library selected"}), 400

    client = _get_client()
    try:
        raw_entries = client.get_library_game_playtowins(game_id)
    except TTEAPIError as exc:
        return _handle_api_json_error(exc, "load entrants")

    entries = process_entries(raw_entries)
    ejected_entries = session.get(SK.EJECTED_ENTRIES, [])

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


# ── Badge lookup ──────────────────────────────────────────────────────

@main_bp.route("/games/badge-lookup")
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


# ── Active checkout lookup ────────────────────────────────────────────

@main_bp.route("/games/active-checkout")
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


# ── Checkout / Checkin ────────────────────────────────────────────────

@main_bp.route("/games/checkout", methods=["POST"])
@login_required(api=True)
def create_checkout():
    """AJAX: create a game checkout."""
    denied = check_checkout_privilege()
    if denied:
        return denied

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

    # Verify game is available before checkout
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
    _update_game_cache(game_id, is_checked_out=1,
                       _renter_name=renter_name,
                       _checkout_id=result.get("id", ""))

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


@main_bp.route("/games/checkin", methods=["POST"])
@login_required(api=True)
def checkin():
    """AJAX: check in a game (return to library)."""
    denied = check_checkout_privilege()
    if denied:
        return denied

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
        _update_game_cache(game_id, is_checked_out=0,
                           _renter_name="", _checkout_id="")

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


@main_bp.route("/games/checkout-status")
@login_required(api=True)
def checkout_status():
    """AJAX: poll for checkout changes from other devices.

    Reads the shared checkout map (written by _update_game_cache on
    every checkout/checkin) and diffs against the local session cache.
    Returns only changed game IDs so the JS can update rows in place.
    No TTE API calls — purely local file reads.
    """
    library_id = session.get(SK.LIBRARY_ID)
    if not library_id:
        return jsonify({"error": "No library selected"}), 400

    # Load latest shared state (including checkout_map from other devices)
    state = shared_state.load(library_id)
    shared_map = state.get(SK.CHECKOUT_MAP, {})

    # Compare against local game cache
    games = session.get(SK.CACHED_GAMES, [])
    changes = {}
    for game in games:
        gid = game.get("id")
        if not gid or gid not in shared_map:
            continue

        info = shared_map[gid]
        was_out = bool(game.get("is_checked_out"))

        if info is None:
            # Shared state says available
            if was_out:
                changes[gid] = {
                    "checked_out": False,
                    "renter": "",
                    "checkout_id": "",
                }
                game["is_checked_out"] = 0
                game["_renter_name"] = ""
                game["_checkout_id"] = ""
        else:
            # Shared state says checked out
            if not was_out or game.get("_renter_name", "") != info.get("renter", ""):
                changes[gid] = {
                    "checked_out": True,
                    "renter": info.get("renter", "Unknown"),
                    "checkout_id": info.get("checkout_id", ""),
                }
                game["is_checked_out"] = 1
                game["_renter_name"] = info.get("renter", "Unknown")
                game["_checkout_id"] = info.get("checkout_id", "")

    if changes:
        session[SK.CACHED_GAMES] = games

    return jsonify({"changes": changes})


# ── P2W entries ───────────────────────────────────────────────────────

@main_bp.route("/games/p2w-entry", methods=["POST"])
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

    # Check for existing P2W entries to prevent duplicates
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


@main_bp.route("/games/p2w-suggestions")
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


@main_bp.route("/games/reset-checkout-time", methods=["POST"])
@login_required(api=True)
def reset_checkout_time():
    """AJAX: reset a checkout's timestamp."""
    denied = check_checkout_privilege()
    if denied:
        return denied

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


# ── Notifications ─────────────────────────────────────────────────────

@main_bp.route("/games/notifications")
@login_required(api=True)
def get_notifications():
    """AJAX: return notifications list."""
    _load_shared_state()
    notifications = session.get(SK.NOTIFICATIONS, [])
    active = [n for n in notifications if not n.get("dismissed")]
    return jsonify({"notifications": active})


@main_bp.route("/games/notifications/dismiss", methods=["POST"])
@login_required(api=True)
def dismiss_notification():
    """AJAX: dismiss a notification by ID."""
    data = request.get_json(silent=True)
    if not data or "id" not in data:
        return jsonify({"error": "Notification ID required"}), 400

    notif_id = data["id"]
    notifications = session.get(SK.NOTIFICATIONS, [])
    for n in notifications:
        if n.get("id") == notif_id:
            n["dismissed"] = True
            break
    _save_shared(SK.NOTIFICATIONS, notifications)
    remaining = sum(1 for n in notifications if not n.get("dismissed"))
    return jsonify({"success": True, "remaining": remaining})


# ── Settings ──────────────────────────────────────────────────────────

@main_bp.route("/games/settings", methods=["POST"])
@login_required(api=True)
def update_settings():
    """AJAX: update checkout alert threshold and other settings."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid request"}), 400

    settings = session.get(SK.LIBRARY_SETTINGS) or {}

    if "checkout_alert_hours" in data:
        try:
            hours = int(data["checkout_alert_hours"])
            if hours < 1:
                hours = 1
            if hours > 24:
                hours = 24
            settings["checkout_alert_hours"] = hours
        except (ValueError, TypeError):
            return jsonify({"error": "Invalid hours value"}), 400

    _save_shared(SK.LIBRARY_SETTINGS, settings)
    return jsonify({"success": True})


@main_bp.route("/games/mark-all-p2w", methods=["POST"])
@login_required(api=True)
def mark_all_p2w():
    """AJAX: mark all in-circulation games as Play-to-Win (FR-CAT-08)."""
    library_id = session.get(SK.LIBRARY_ID)
    if not library_id:
        return jsonify({"error": "No library selected"}), 400

    games = session.get(SK.CACHED_GAMES, [])
    to_update = [
        g for g in games
        if not g.get("is_play_to_win") and g.get("is_in_circulation")
    ]

    if not to_update:
        return jsonify({"success": True, "updated": 0,
                        "message": "All in-circulation games are already Play-to-Win."})

    client = _get_client()
    updated = 0
    for game in to_update:
        try:
            client.update_library_game(game["id"], {"is_play_to_win": 1})
            game["is_play_to_win"] = 1
            updated += 1
        except TTEAPIError as exc:
            logger.warning("Failed to mark game %s as P2W: %s",
                           game.get("name"), exc)

    session[SK.CACHED_GAMES] = games
    logger.info("Marked %d/%d games as P2W", updated, len(to_update))
    return jsonify({"success": True, "updated": updated,
                    "message": f"Marked {updated} games as Play-to-Win."})


# ── Volunteer login ───────────────────────────────────────────────────

@main_bp.route("/volunteer-login", methods=["GET", "POST"])
def volunteer_login():
    """Volunteer login page — authenticates with volunteer's own TTE credentials."""
    library_id = session.get(SK.LIBRARY_ID)
    library_name = session.get(SK.LIBRARY_NAME)

    if not library_id:
        flash("A library must be selected before volunteers can log in.", "error")
        return redirect(url_for("main.login"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        api_key = request.form.get("api_key", "").strip()

        if not username or not password or not api_key:
            flash("Username, password, and API key are required.", "error")
            return render_template("volunteer_login.html",
                                   library_name=library_name), 400

        from tte_client import TTEClient
        client = TTEClient(api_key_id=api_key)
        try:
            client.login(username, password)
        except TTEAPIError as exc:
            logger.warning("Volunteer login failed for '%s': %s", username, exc)
            flash(f"Login failed: {exc}", "error")
            return render_template("volunteer_login.html",
                                   library_name=library_name), 401

        # Verify checkout privilege on this library
        has_checkout = False
        try:
            privileges = client.get_library_privileges(library_id)
            for priv in privileges:
                if priv.get("user_id") == client.user_id:
                    has_checkout = bool(priv.get("checkouts"))
                    break
        except TTEAPIError as exc:
            logger.warning("Could not verify privileges for volunteer '%s': %s",
                           username, exc)
            flash("Could not verify your library privileges. "
                  "Please ask the library owner to grant you access.", "error")
            try:
                client.logout()
            except TTEAPIError:
                pass
            return render_template("volunteer_login.html",
                                   library_name=library_name), 403

        if not has_checkout:
            logger.warning("Volunteer '%s' lacks checkout privilege on library %s",
                           username, library_id)
            flash("Your account does not have checkout privileges on this library. "
                  "Please ask the library owner to grant you access.", "error")
            try:
                client.logout()
            except TTEAPIError:
                pass
            return render_template("volunteer_login.html",
                                   library_name=library_name), 403

        # Store volunteer session
        session[SK.TTE_SESSION_ID] = client.session_id
        session[SK.TTE_USERNAME] = username
        session[SK.TTE_USER_ID] = client.user_id
        session[SK.TTE_API_KEY] = api_key
        session[SK.AUTH_MODE] = "volunteer"
        session[SK.VOLUNTEER_NAME] = username
        session[SK.HAS_CHECKOUT_PRIVILEGE] = has_checkout
        session[SK.APP_MODE] = "management"

        logger.info("Volunteer '%s' logged in for library '%s'",
                     username, library_name)
        flash(f"Welcome, {username}! You are logged in as a volunteer.", "success")
        return redirect(url_for("main.games"))

    return render_template("volunteer_login.html",
                           library_name=library_name)


@main_bp.route("/volunteer-logout", methods=["POST"])
@login_required
def volunteer_logout():
    """Log out a volunteer — preserves library context for next volunteer."""
    username = session.get(SK.TTE_USERNAME, "unknown")
    tte_session_id = session.get(SK.TTE_SESSION_ID)
    tte_api_key = session.get(SK.TTE_API_KEY)

    if tte_session_id:
        from tte_client import TTEClient
        client = TTEClient(api_key_id=tte_api_key)
        client.session_id = tte_session_id
        try:
            client.logout()
        except TTEAPIError:
            pass

    # Preserve library context so next volunteer can log in
    library_id = session.get(SK.LIBRARY_ID)
    library_name = session.get(SK.LIBRARY_NAME)
    convention_id = session.get(SK.CONVENTION_ID)
    convention_name = session.get(SK.CONVENTION_NAME)
    cached_games = session.get(SK.CACHED_GAMES)

    session.clear()

    if library_id:
        session[SK.LIBRARY_ID] = library_id
    if library_name:
        session[SK.LIBRARY_NAME] = library_name
    if convention_id:
        session[SK.CONVENTION_ID] = convention_id
    if convention_name:
        session[SK.CONVENTION_NAME] = convention_name
    if cached_games is not None:
        session[SK.CACHED_GAMES] = cached_games

    logger.info("Volunteer '%s' logged out", username)
    flash("You have been logged out.", "info")
    return redirect(url_for("main.volunteer_login"))
