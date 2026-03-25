"""Library Management component check tracking routes (FR-COMP-01–05)."""

import json
import logging
import os
from datetime import datetime, timezone

from flask import flash, jsonify, redirect, render_template, request, session, url_for

from session_keys import SK

from . import library_bp
from routes.helpers import is_valid_tte_id, login_required

logger = logging.getLogger(__name__)

_CHECKS_DIR = "component_checks"


def _checks_filepath(library_id):
    """Return the JSON file path for a library's component checks."""
    # Sanitise library_id to prevent path traversal
    safe_id = "".join(c for c in library_id if c.isalnum() or c in "-_")
    return os.path.join(_CHECKS_DIR, f"{safe_id}.json")


def _load_checks(library_id):
    """Load component checks from JSON file, falling back to session."""
    filepath = _checks_filepath(library_id)
    if os.path.isfile(filepath):
        try:
            with open(filepath, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            logger.warning("Failed to read component checks from %s", filepath)
    return session.get(SK.COMPONENT_CHECKS) or {}


def _save_checks(library_id, checks):
    """Persist component checks to both session and JSON file."""
    session[SK.COMPONENT_CHECKS] = checks
    os.makedirs(_CHECKS_DIR, exist_ok=True)
    filepath = _checks_filepath(library_id)
    try:
        with open(filepath, "w") as f:
            json.dump(checks, f, indent=2)
    except OSError:
        logger.warning("Failed to write component checks to %s", filepath)


@library_bp.route("/component-checks")
@login_required
def component_checks():
    """Component check tracking page (FR-COMP-04)."""
    library_id = session.get(SK.LIBRARY_ID)
    if not library_id:
        flash("No library selected.", "error")
        return redirect(url_for("library.dashboard"))

    games = session.get(SK.CACHED_GAMES, [])
    checks = _load_checks(library_id)

    show_unchecked = request.args.get("unchecked") == "1"

    items = []
    for game in games:
        gid = game.get("id")
        check_info = checks.get(gid)
        if show_unchecked and check_info:
            continue
        items.append({
            "id": gid,
            "name": game.get("name", "Unknown"),
            "catalog_number": game.get("catalog_number", ""),
            "checked": bool(check_info),
            "volunteer": check_info.get("volunteer") if check_info else None,
            "timestamp": check_info.get("timestamp") if check_info else None,
        })

    items.sort(key=lambda x: x["name"].lower())

    total = len(games)
    checked_count = sum(1 for g in games if checks.get(g.get("id")))

    return render_template(
        "library/component_checks.html",
        items=items,
        total=total,
        checked_count=checked_count,
        remaining=total - checked_count,
        show_unchecked=show_unchecked,
    )


@library_bp.route("/component-check", methods=["POST"])
@login_required(api=True)
def mark_component_check():
    """AJAX: mark a game as component-checked (FR-COMP-02)."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid request"}), 400

    game_id = data.get("game_id", "").strip()
    volunteer = data.get("volunteer", "").strip()

    if not game_id or not is_valid_tte_id(game_id):
        return jsonify({"error": "Invalid game ID"}), 400
    if not volunteer:
        return jsonify({"error": "Volunteer name is required"}), 400

    library_id = session.get(SK.LIBRARY_ID)
    if not library_id:
        return jsonify({"error": "No library selected"}), 400

    checks = _load_checks(library_id)
    checks[game_id] = {
        "checked": True,
        "volunteer": volunteer,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    _save_checks(library_id, checks)

    return jsonify({"success": True})


@library_bp.route("/component-uncheck", methods=["POST"])
@login_required(api=True)
def unmark_component_check():
    """AJAX: unmark a game's component check."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid request"}), 400

    game_id = data.get("game_id", "").strip()
    if not game_id or not is_valid_tte_id(game_id):
        return jsonify({"error": "Invalid game ID"}), 400

    library_id = session.get(SK.LIBRARY_ID)
    if not library_id:
        return jsonify({"error": "No library selected"}), 400

    checks = _load_checks(library_id)
    checks.pop(game_id, None)
    _save_checks(library_id, checks)

    return jsonify({"success": True})
