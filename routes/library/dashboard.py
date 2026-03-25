"""Library Management dashboard and mode-switching routes."""

import logging
import uuid
from collections import Counter
from datetime import datetime, timezone

from flask import flash, jsonify, redirect, render_template, request, session, url_for

from session_keys import SK
from tte_client import TTEAPIError

from . import library_bp
from routes.helpers import _get_client, login_required

logger = logging.getLogger(__name__)


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
    session[SK.NOTIFICATIONS] = notifications


def _detect_non_p2w_games():
    """Check for non-P2W games in the catalog and create notification (FR-CAT-07)."""
    games = session.get(SK.CACHED_GAMES, [])
    non_p2w = [
        g for g in games
        if not g.get("is_play_to_win") and g.get("is_in_circulation")
    ]
    if not non_p2w:
        return

    names = [g.get("name", "Unknown") for g in non_p2w]
    message = f"{len(non_p2w)} game{'s' if len(non_p2w) != 1 else ''} in this library {'are' if len(non_p2w) != 1 else 'is'} not marked Play-to-Win."
    _add_notification("non_p2w", message, details=names)


@library_bp.route("/")
@login_required
def dashboard():
    """Library Management dashboard — main landing page for checkout operations."""
    library_name = session.get(SK.LIBRARY_NAME)
    if not library_name:
        flash("Please select a library first.", "error")
        return redirect(url_for("main.convention_select"))

    games = session.get(SK.CACHED_GAMES, [])
    convention_name = session.get(SK.CONVENTION_NAME)
    notifications = session.get(SK.NOTIFICATIONS, [])
    unread_count = sum(1 for n in notifications if not n.get("dismissed"))

    # Quick stats from cached data
    total_games = len(games)
    checked_out = sum(1 for g in games if g.get("is_checked_out"))
    p2w_games = sum(1 for g in games if g.get("is_play_to_win"))

    return render_template(
        "library/dashboard.html",
        library_name=library_name,
        convention_name=convention_name,
        total_games=total_games,
        checked_out=checked_out,
        p2w_games=p2w_games,
        unread_count=unread_count,
    )


@library_bp.route("/switch-mode", methods=["POST"])
@login_required
def switch_mode():
    """Switch between Drawing and Library Management modes."""
    target = request.form.get("mode", "drawing")
    if target not in ("drawing", "library"):
        target = "drawing"
    session[SK.APP_MODE] = target
    logger.info("Mode switched to: %s", target)
    if target == "library":
        return redirect(url_for("library.dashboard"))
    return redirect(url_for("main.convention_select"))


@library_bp.route("/update-settings", methods=["POST"])
@login_required
def update_settings():
    """Update library settings (non-P2W toggle, etc.)."""
    data = request.get_json(silent=True) or {}
    settings = session.get(SK.LIBRARY_SETTINGS) or {}
    if "include_non_p2w" in data:
        settings["include_non_p2w"] = bool(data["include_non_p2w"])
    session[SK.LIBRARY_SETTINGS] = settings
    return jsonify({"success": True})


@library_bp.route("/refresh-catalog", methods=["POST"])
@login_required
def refresh_catalog():
    """Re-fetch the full game catalog from TTE (FR-CAT-05)."""
    library_id = session.get(SK.LIBRARY_ID)
    if not library_id:
        flash("No library selected.", "error")
        return redirect(url_for("library.dashboard"))

    settings = session.get(SK.LIBRARY_SETTINGS) or {}
    p2w_only = not settings.get("include_non_p2w", False)

    client = _get_client()
    try:
        games = client.get_library_games(library_id, play_to_win_only=p2w_only)
    except TTEAPIError as exc:
        logger.error("Catalog refresh failed: %s", exc)
        flash(f"Catalog refresh failed: {exc}", "error")
        return redirect(url_for("library.dashboard"))

    # Enrich with P2W entry counts (FR-LOWPLAY-01)
    try:
        all_p2w = client.get_library_playtowins(library_id)
        p2w_counts = Counter(e.get("librarygame_id") for e in all_p2w)
        for g in games:
            g["_p2w_count"] = p2w_counts.get(g.get("id"), 0)
    except TTEAPIError:
        logger.warning("Could not fetch P2W entries for count enrichment")

    session[SK.CACHED_GAMES] = games
    logger.info("Catalog refreshed: %d games loaded", len(games))

    # Check for non-P2W games if we loaded all games
    if not p2w_only:
        _detect_non_p2w_games()

    flash(f"Catalog refreshed — {len(games)} games loaded.", "success")
    return redirect(url_for("library.dashboard"))


@library_bp.route("/mark-all-p2w", methods=["POST"])
@login_required
def mark_all_p2w():
    """Mark all in-circulation games as Play-to-Win (FR-CAT-08)."""
    library_id = session.get(SK.LIBRARY_ID)
    if not library_id:
        flash("No library selected.", "error")
        return redirect(url_for("library.dashboard"))

    games = session.get(SK.CACHED_GAMES, [])
    to_update = [
        g for g in games
        if not g.get("is_play_to_win") and g.get("is_in_circulation")
    ]

    if not to_update:
        flash("All in-circulation games are already marked Play-to-Win.", "info")
        return redirect(url_for("library.dashboard"))

    client = _get_client()
    updated = 0
    for game in to_update:
        try:
            client.update_library_game(game["id"], {"is_play_to_win": 1})
            game["is_play_to_win"] = 1
            updated += 1
        except TTEAPIError as exc:
            logger.warning("Failed to mark game %s as P2W: %s", game.get("name"), exc)

    session[SK.CACHED_GAMES] = games
    logger.info("Marked %d/%d games as P2W", updated, len(to_update))
    flash(f"Marked {updated} games as Play-to-Win.", "success")
    return redirect(url_for("library.dashboard"))


@library_bp.route("/check-suspicious", methods=["POST"])
@login_required
def check_suspicious():
    """Run suspicious checkout detection and generate notifications (FR-SUSPCHK)."""
    library_id = session.get(SK.LIBRARY_ID)
    if not library_id:
        flash("No library selected.", "error")
        return redirect(url_for("library.dashboard"))

    from .suspicious import (
        check_long_checkouts,
        check_partner_patterns,
        flag_suspicious_games,
    )

    games = session.get(SK.CACHED_GAMES, [])

    client = _get_client()
    try:
        active = client.get_library_checkouts(library_id, checked_in=False)
    except TTEAPIError:
        active = []

    suspicious = check_long_checkouts(games, active, premium_ids=set(session.get(SK.PREMIUM_GAMES, [])))
    play_groups = session.get(SK.PLAY_GROUPS, {})

    # Also check history for partner patterns
    try:
        history = client.get_library_checkouts(library_id, checked_in=True)
    except TTEAPIError:
        history = []

    patterns = check_partner_patterns(active + history, play_groups, games)
    flagged = flag_suspicious_games(games, suspicious, patterns)
    session[SK.CACHED_GAMES] = games

    if suspicious:
        names = [f"{s['game_name']} ({s['renter_name']}, {s['elapsed_hours']}h)"
                 for s in suspicious]
        msg = f"{len(suspicious)} game{'s' if len(suspicious) != 1 else ''} checked out beyond threshold."
        _add_notification("warning", msg, details=names)

    if patterns:
        descs = [f"{p['person_a']} → {p['person_b']} on game {p['game_id'][:8]}…"
                 for p in patterns]
        _add_notification(
            "alert",
            f"{len(patterns)} suspicious partner pattern{'s' if len(patterns) != 1 else ''} detected.",
            details=descs,
        )

    if not suspicious and not patterns:
        flash("No suspicious checkouts detected.", "info")
    else:
        flash(f"Found {len(flagged)} flagged game(s). Check notifications for details.", "warning")

    return redirect(url_for("library.dashboard"))


@library_bp.route("/notifications")
@login_required
def notifications():
    """Notifications page — view and dismiss alerts."""
    all_notifications = session.get(SK.NOTIFICATIONS, [])
    return render_template(
        "library/notifications.html",
        notifications=all_notifications,
    )


@library_bp.route("/notifications/dismiss", methods=["POST"])
@login_required(api=True)
def dismiss_notification():
    """AJAX: dismiss a notification by ID."""
    from flask import jsonify, request
    data = request.get_json(silent=True)
    if not data or "id" not in data:
        return jsonify({"error": "Notification ID required"}), 400

    notif_id = data["id"]
    notifications = session.get(SK.NOTIFICATIONS, [])
    for n in notifications:
        if n.get("id") == notif_id:
            n["dismissed"] = True
            break
    session[SK.NOTIFICATIONS] = notifications
    return jsonify({"success": True})
