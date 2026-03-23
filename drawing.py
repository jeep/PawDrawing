"""Drawing algorithm for Play-to-Win winner selection.

Handles shuffle, initial winner selection, multi-winner conflict detection,
premium auto-assignment, and iterative conflict resolution.
"""

import random
from collections import defaultdict


def shuffle_entries(game_data, rng=None):
    """Shuffle entries for each game. Returns a new list with shuffled entry copies.

    Each item in the result has:
        - "game": game metadata dict
        - "shuffled": full shuffled list of entries (preserved for redistribution)
        - "winner_index": 0 (initial winner is first in shuffled list)

    Games with zero entries are included with an empty shuffled list
    and winner_index of -1.
    """
    if rng is None:
        rng = random.Random()

    result = []
    for item in game_data:
        entries = list(item["entries"])
        rng.shuffle(entries)
        result.append({
            "game": item["game"],
            "shuffled": entries,
            "winner_index": 0 if entries else -1,
        })
    return result


def get_current_winners(drawing_state):
    """Extract current winners from drawing state.

    Returns a dict mapping game_id -> winner entry (or None if exhausted).
    """
    winners = {}
    for item in drawing_state:
        game_id = item["game"]["id"]
        idx = item["winner_index"]
        if 0 <= idx < len(item["shuffled"]):
            winners[game_id] = item["shuffled"][idx]
        else:
            winners[game_id] = None
    return winners


def detect_conflicts(drawing_state):
    """Find badge_ids that won more than one game.

    Returns a dict: badge_id -> list of game_ids they won.
    Only includes badge_ids with 2+ wins.
    """
    winners = get_current_winners(drawing_state)
    badge_games = defaultdict(list)

    for game_id, entry in winners.items():
        if entry is not None:
            badge_id = entry.get("badge_id")
            if badge_id:
                badge_games[badge_id].append(game_id)

    return {bid: gids for bid, gids in badge_games.items() if len(gids) > 1}


def resolve_premium_auto(conflicts, premium_game_ids):
    """Auto-resolve conflicts where a person won exactly one premium game.

    Returns:
        resolved: dict mapping badge_id -> game_id they keep
        remaining: dict of still-unresolved conflicts (badge_id -> [game_ids])
    """
    resolved = {}
    remaining = {}

    for badge_id, game_ids in conflicts.items():
        premium_wins = [gid for gid in game_ids if gid in premium_game_ids]

        if len(premium_wins) == 1:
            # Auto-assign the single premium game
            resolved[badge_id] = premium_wins[0]
        else:
            # Needs manual resolution (0 or 2+ premium wins)
            remaining[badge_id] = game_ids

    return resolved, remaining


def advance_winner(drawing_state, game_id, not_here=None):
    """Advance to the next person in the shuffled list for a game.

    Skips anyone in the not_here set (badge_ids of absent people).
    Returns True if a new winner was found, False if the list is exhausted.
    """
    if not_here is None:
        not_here = set()
    for item in drawing_state:
        if item["game"]["id"] == game_id:
            while True:
                item["winner_index"] += 1
                if item["winner_index"] >= len(item["shuffled"]):
                    return False
                candidate = item["shuffled"][item["winner_index"]]
                if candidate.get("badge_id") not in not_here:
                    return True
    return False


def apply_resolution(drawing_state, keep_map, premium_game_ids):
    """Apply conflict resolutions: for each resolved badge_id, advance winners
    on all their games except the one they keep.

    keep_map: dict mapping badge_id -> game_id to keep

    Returns list of game_ids that were advanced (relinquished games).
    """
    winners = get_current_winners(drawing_state)
    advanced = []

    for badge_id, keep_game_id in keep_map.items():
        # Find all games this badge_id currently wins
        their_games = [
            gid for gid, entry in winners.items()
            if entry and entry.get("badge_id") == badge_id
        ]
        for game_id in their_games:
            if game_id != keep_game_id:
                advance_winner(drawing_state, game_id)
                advanced.append(game_id)

    return advanced


def _resolve_conflicts_loop(state, premium_set):
    """Run the conflict detection/auto-resolution loop on a drawing state.

    Returns:
        conflicts_out: list of unresolved conflict dicts (empty if all resolved)
        auto_resolved: list of auto-resolved premium assignment dicts
    """
    auto_resolved = []
    max_iterations = 100  # Safety bound

    for _ in range(max_iterations):
        conflicts = detect_conflicts(state)
        if not conflicts:
            break

        resolved, remaining = resolve_premium_auto(conflicts, premium_set)

        if resolved:
            winners = get_current_winners(state)
            game_name_map = {
                item["game"]["id"]: item["game"].get("name", "Unknown")
                for item in state
            }
            for badge_id, kept_game_id in resolved.items():
                their_games = conflicts[badge_id]
                relinquished = [gid for gid in their_games if gid != kept_game_id]
                winner_name = "Unknown"
                w = winners.get(kept_game_id)
                if w and w.get("name"):
                    winner_name = w["name"]
                auto_resolved.append({
                    "badge_id": badge_id,
                    "winner_name": winner_name,
                    "kept_game_id": kept_game_id,
                    "kept_game_name": game_name_map.get(kept_game_id, "Unknown"),
                    "relinquished": relinquished,
                    "relinquished_names": [game_name_map.get(gid, "Unknown") for gid in relinquished],
                })
            apply_resolution(state, resolved, premium_set)
            continue

        if remaining:
            winners = get_current_winners(state)
            game_name_map = {
                item["game"]["id"]: item["game"].get("name", "Unknown")
                for item in state
            }
            conflicts_out = []
            for badge_id, game_ids in remaining.items():
                premium_wins = [gid for gid in game_ids if gid in premium_set]
                winner_name = "Unknown"
                for gid in game_ids:
                    w = winners.get(gid)
                    if w and w.get("name"):
                        winner_name = w["name"]
                        break
                conflicts_out.append({
                    "badge_id": badge_id,
                    "winner_name": winner_name,
                    "game_ids": game_ids,
                    "game_names": {gid: game_name_map.get(gid, "Unknown") for gid in game_ids},
                    "is_premium_conflict": len(premium_wins) > 1,
                })
            return conflicts_out, auto_resolved

    return [], auto_resolved


def run_drawing(game_data, premium_game_ids, rng=None):
    """Execute the full drawing algorithm.

    Returns:
        drawing_state: the shuffled state with final winner indices
        conflicts_needing_input: list of unresolved conflicts requiring admin input
            Each is: {"badge_id": str, "game_ids": [str], "game_names": {id: name},
                       "is_premium_conflict": bool}
        auto_resolved: list of auto-resolved premium assignments
            Each is: {"badge_id": str, "kept_game_id": str, "relinquished": [str]}

    If conflicts_needing_input is non-empty, the caller must get admin input
    and call apply_resolution + re-run conflict detection.
    """
    premium_set = set(premium_game_ids) if premium_game_ids else set()
    drawing_state = shuffle_entries(game_data, rng=rng)

    conflicts, auto_resolved = _resolve_conflicts_loop(drawing_state, premium_set)
    return drawing_state, conflicts, auto_resolved


def redraw_unclaimed(drawing_state, unclaimed_game_ids, not_here, original_winners,
                     same_rules=False, premium_game_ids=None, rng=None):
    """Redraw only the unclaimed games with a fresh shuffle.

    Args:
        drawing_state: the full drawing state list
        unclaimed_game_ids: set of game_ids to redraw
        not_here: set of badge_ids marked absent
        original_winners: set of badge_ids who won in the first drawing
        same_rules: if True, apply one-win conflict resolution among redraw winners
        premium_game_ids: list of premium game IDs (used only with same_rules)
        rng: optional random.Random instance for reproducibility

    Returns:
        conflicts: list of conflict dicts if same_rules produced unresolved conflicts
        auto_resolved: list of auto-resolved premium assignments (same_rules only)
    """
    if rng is None:
        rng = random.Random()

    exclude = not_here | original_winners

    for item in drawing_state:
        game_id = item["game"]["id"]
        if game_id not in unclaimed_game_ids:
            continue

        # Filter to eligible entrants and re-shuffle
        eligible = [e for e in item["shuffled"] if e.get("badge_id") not in exclude]
        rng.shuffle(eligible)
        item["shuffled"] = eligible
        item["winner_index"] = 0 if eligible else -1

    if not same_rules:
        return [], []

    # Apply one-win conflict resolution among redraw winners
    premium_set = set(premium_game_ids) if premium_game_ids else set()
    redraw_state = [item for item in drawing_state if item["game"]["id"] in unclaimed_game_ids]

    return _resolve_conflicts_loop(redraw_state, premium_set)
