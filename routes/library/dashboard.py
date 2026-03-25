"""Library Management dashboard and mode-switching routes."""

import logging

from flask import flash, redirect, render_template, request, session, url_for

from session_keys import SK

from . import library_bp
from routes.helpers import login_required

logger = logging.getLogger(__name__)


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
