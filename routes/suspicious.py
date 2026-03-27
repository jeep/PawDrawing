"""Suspicious checkout detection logic (FR-SUSPCHK-01–05)."""

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def _parse_datetime(dt_str):
    """Parse a TTE datetime string, returning None on failure."""
    if not dt_str:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(dt_str, fmt).replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue
    return None


def compute_threshold_seconds(game):
    """Compute the suspicious-checkout threshold for a game.

    Rules (FR-SUSPCHK-01):
    - 2× max_play_time (in minutes → seconds), minimum 1 hour.
    - Falls back to 4 hours if play time data is unavailable.
    """
    max_play = game.get("max_play_time")
    if max_play and int(max_play) > 0:
        threshold = int(max_play) * 2 * 60  # minutes → seconds, × 2
        return max(threshold, 3600)  # minimum 1 hour
    return 4 * 3600  # 4-hour fallback


def _resolve_threshold_seconds(game, alert_hours=None):
    """Combine per-game threshold with optional operator alert-hours floor."""
    threshold = compute_threshold_seconds(game)
    if alert_hours is None:
        return threshold
    try:
        alert_seconds = int(alert_hours) * 3600
    except (TypeError, ValueError):
        return threshold
    if alert_seconds <= 0:
        return threshold
    return max(threshold, alert_seconds)


def check_long_checkouts(games, active_checkouts, premium_ids=None, alert_hours=None):
    """Detect currently-active checkouts that exceed the game's threshold.

    Args:
        games: list of game dicts from session cache.
        active_checkouts: list of checkout dicts (is_checked_in=0).
        premium_ids: optional set of game IDs designated as premium.

    Returns:
        list of dicts with suspicious checkout info.
    """
    game_map = {g.get("id"): g for g in games}
    premium = set(premium_ids or [])
    now = datetime.now(timezone.utc)
    suspicious = []

    for co in active_checkouts:
        game_id = co.get("librarygame_id")
        game = game_map.get(game_id, {})
        threshold = _resolve_threshold_seconds(game, alert_hours=alert_hours)

        started = _parse_datetime(co.get("date_created"))
        if not started:
            continue

        elapsed = (now - started).total_seconds()
        if elapsed > threshold:
            suspicious.append({
                "checkout_id": co.get("id"),
                "game_id": game_id,
                "game_name": game.get("name", "Unknown"),
                "renter_name": co.get("renter_name", "Unknown"),
                "elapsed_hours": round(elapsed / 3600, 1),
                "threshold_hours": round(threshold / 3600, 1),
                "is_premium": game_id in premium,
            })

    return suspicious


def check_partner_patterns(checkouts, play_groups, games=None, alert_hours=None):
    """Detect sequential long checkouts by play partners (FR-SUSPCHK-02).

    If person A had a long checkout for game X, and person B (a frequent
    co-player of A) then checks out game X for a long time, flag it.

    Args:
        checkouts: list of all checkout dicts (both active and history).
        play_groups: dict mapping person name → list of co-entrant names.
        games: optional list of game dicts for per-game threshold lookup.

    Returns:
        list of pattern dicts describing suspicious partner patterns.
    """
    # Build game lookup for per-game thresholds
    game_map = {g.get("id"): g for g in (games or [])}

    # Group checkouts by game, sorted by date
    from collections import defaultdict
    game_checkouts = defaultdict(list)
    for co in checkouts:
        game_checkouts[co.get("librarygame_id")].append(co)

    patterns = []
    for game_id, cos in game_checkouts.items():
        cos.sort(key=lambda c: _parse_datetime(c.get("date_created")) or datetime.min.replace(tzinfo=timezone.utc))
        game = game_map.get(game_id, {})
        threshold = _resolve_threshold_seconds(game, alert_hours=alert_hours)

        long_cos = [
            co for co in cos
            if (co.get("checkedout_seconds", 0) or 0) > threshold
        ]

        for i in range(len(long_cos) - 1):
            a = long_cos[i]
            a_name = a.get("renter_name", "")
            if not a_name:
                continue

            partners_of_a = play_groups.get(a_name, [])
            if not partners_of_a:
                continue

            # Consider any later long checkout by a play partner, not just adjacent rows.
            for j in range(i + 1, len(long_cos)):
                b = long_cos[j]
                b_name = b.get("renter_name", "")
                if b_name not in partners_of_a:
                    continue

                a_secs = a.get("checkedout_seconds", 0) or 0
                b_secs = b.get("checkedout_seconds", 0) or 0
                patterns.append({
                    "game_id": game_id,
                    "person_a": a_name,
                    "person_b": b_name,
                    "a_hours": round(a_secs / 3600, 1),
                    "b_hours": round(b_secs / 3600, 1),
                })
                break

    return patterns


def flag_suspicious_games(games, suspicious_checkouts, partner_patterns):
    """Set a '_suspicious' flag on games with suspicious checkout activity.

    Modifies games in place. Returns list of flagged game IDs.
    """
    flagged_ids = set()
    for s in suspicious_checkouts:
        flagged_ids.add(s["game_id"])
    for p in partner_patterns:
        flagged_ids.add(p["game_id"])

    for game in games:
        game["_suspicious"] = game.get("id") in flagged_ids

    return list(flagged_ids)
