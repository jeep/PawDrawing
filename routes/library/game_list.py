"""Library Management game list with low-play/checkout filters (FR-LOWPLAY-01–04)."""

import logging

from flask import flash, redirect, render_template, request, session, url_for

from session_keys import SK

from . import library_bp
from routes.helpers import login_required

logger = logging.getLogger(__name__)


@library_bp.route("/games")
@login_required
def game_list():
    """Full game list with sortable columns and threshold filters (FR-LOWPLAY)."""
    library_id = session.get(SK.LIBRARY_ID)
    if not library_id:
        flash("No library selected.", "error")
        return redirect(url_for("library.dashboard"))

    games = session.get(SK.CACHED_GAMES, [])
    premium_ids = set(session.get(SK.PREMIUM_GAMES, []))

    # Read filter params
    max_p2w = request.args.get("max_p2w", type=int)
    max_checkouts = request.args.get("max_checkouts", type=int)
    sort_by = request.args.get("sort", "name")
    sort_dir = request.args.get("dir", "asc")
    status_filter = request.args.get("status", "")

    items = []
    for g in games:
        p2w_count = g.get("_p2w_count", 0)
        checkout_count = g.get("checkout_count", 0) or 0

        # Apply threshold filters (FR-LOWPLAY-02)
        if max_p2w is not None and p2w_count >= max_p2w:
            continue
        if max_checkouts is not None and checkout_count >= max_checkouts:
            continue

        # Apply status filter
        if status_filter == "available" and g.get("is_checked_out"):
            continue
        if status_filter == "out" and not g.get("is_checked_out"):
            continue

        items.append({
            "id": g.get("id"),
            "name": g.get("name", "Unknown"),
            "catalog_number": g.get("catalog_number", ""),
            "is_checked_out": g.get("is_checked_out"),
            "is_play_to_win": g.get("is_play_to_win"),
            "is_in_circulation": g.get("is_in_circulation"),
            "is_premium": g.get("id") in premium_ids,
            "checkout_count": checkout_count,
            "p2w_count": p2w_count,
            "suspicious": g.get("_suspicious", False),
            "renter_name": g.get("_renter_name", ""),
            "checkout_id": g.get("_checkout_id", ""),
        })

    # Sort
    reverse = sort_dir == "desc"
    if sort_by == "checkouts":
        items.sort(key=lambda x: x["checkout_count"], reverse=reverse)
    elif sort_by == "p2w":
        items.sort(key=lambda x: x["p2w_count"], reverse=reverse)
    elif sort_by == "catalog":
        items.sort(key=lambda x: x["catalog_number"].lower(), reverse=reverse)
    else:
        items.sort(key=lambda x: x["name"].lower(), reverse=reverse)

    return render_template(
        "library/game_list.html",
        items=items,
        total=len(games),
        showing=len(items),
        max_p2w=max_p2w,
        max_checkouts=max_checkouts,
        sort_by=sort_by,
        sort_dir=sort_dir,
        status_filter=status_filter,
    )
