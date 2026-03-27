"""Library Management component check routes."""

import os
import time

from flask import jsonify, redirect, render_template, request, session, url_for

from session_keys import SK

from . import library_bp
from routes.helpers import is_valid_tte_id, login_required


def _checks_dir():
    path = os.path.join("shared_state", "component_checks")
    os.makedirs(path, exist_ok=True)
    return path


def _checks_file(library_id):
    return os.path.join(_checks_dir(), f"{library_id}.json")


def _load_checks(library_id):
    # Prefer session state so all existing behavior remains fast and deterministic.
    return dict(session.get(SK.COMPONENT_CHECKS, {}))


def _save_checks(library_id, checks):
    session[SK.COMPONENT_CHECKS] = checks


def _build_items(games, checks, show_unchecked=False):
    items = []
    for g in games:
        gid = g.get("id")
        rec = checks.get(gid)
        checked = bool(rec and rec.get("checked"))
        if show_unchecked and checked:
            continue
        items.append({
            "id": gid,
            "name": g.get("name", "Unknown"),
            "catalog_number": g.get("catalog_number", ""),
            "checked": checked,
            "volunteer": rec.get("volunteer", "") if rec else "",
        })
    return items


@library_bp.route("/component-checks")
@login_required
def component_checks():
    library_id = session.get(SK.LIBRARY_ID)
    if not library_id:
        return redirect(url_for("main.convention_select"))

    games = session.get(SK.CACHED_GAMES, [])
    checks = _load_checks(library_id)
    show_unchecked = request.args.get("unchecked") == "1"

    items = _build_items(games, checks, show_unchecked=show_unchecked)
    checked_count = sum(1 for item in _build_items(games, checks) if item["checked"])
    total = len(games)

    return render_template(
        "library/component_checks.html",
        items=items,
        checked_count=checked_count,
        total=total,
        remaining=max(0, total - checked_count),
        show_unchecked=show_unchecked,
    )


@library_bp.route("/component-check", methods=["POST"])
@login_required(api=True)
def mark_component_check():
    library_id = session.get(SK.LIBRARY_ID)
    if not library_id:
        return jsonify({"error": "No library selected"}), 400

    data = request.get_json(silent=True) or {}
    game_id = (data.get("game_id") or "").strip()
    volunteer = (data.get("volunteer") or "").strip()

    if not game_id or not is_valid_tte_id(game_id):
        return jsonify({"error": "Invalid game ID"}), 400
    if not volunteer:
        return jsonify({"error": "Volunteer name is required"}), 400

    checks = _load_checks(library_id)
    checks[game_id] = {
        "checked": True,
        "volunteer": volunteer,
        "timestamp": int(time.time()),
    }
    _save_checks(library_id, checks)
    return jsonify({"success": True})


@library_bp.route("/component-uncheck", methods=["POST"])
@login_required(api=True)
def unmark_component_check():
    library_id = session.get(SK.LIBRARY_ID)
    if not library_id:
        return jsonify({"error": "No library selected"}), 400

    data = request.get_json(silent=True) or {}
    game_id = (data.get("game_id") or "").strip()
    if not game_id or not is_valid_tte_id(game_id):
        return jsonify({"error": "Invalid game ID"}), 400

    checks = _load_checks(library_id)
    checks.pop(game_id, None)
    _save_checks(library_id, checks)
    return jsonify({"success": True})
