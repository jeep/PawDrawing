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


def advance_winner(drawing_state, game_id):
    """Advance to the next person in the shuffled list for a game.

    Returns True if a new winner was found, False if the list is exhausted.
    """
    for item in drawing_state:
        if item["game"]["id"] == game_id:
            item["winner_index"] += 1
            return item["winner_index"] < len(item["shuffled"])
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

    auto_resolved = []
    max_iterations = 100  # Safety bound

    for _ in range(max_iterations):
        conflicts = detect_conflicts(drawing_state)
        if not conflicts:
            break

        resolved, remaining = resolve_premium_auto(conflicts, premium_set)

        if resolved:
            for badge_id, kept_game_id in resolved.items():
                their_games = conflicts[badge_id]
                relinquished = [gid for gid in their_games if gid != kept_game_id]
                auto_resolved.append({
                    "badge_id": badge_id,
                    "kept_game_id": kept_game_id,
                    "relinquished": relinquished,
                })
            apply_resolution(drawing_state, resolved, premium_set)
            # Continue loop to check for new conflicts from cascading
            continue

        if remaining:
            # Build conflict info for admin input
            game_name_map = {
                item["game"]["id"]: item["game"].get("name", "Unknown")
                for item in drawing_state
            }
            conflicts_needing_input = []
            for badge_id, game_ids in remaining.items():
                premium_wins = [gid for gid in game_ids if gid in premium_set]
                conflicts_needing_input.append({
                    "badge_id": badge_id,
                    "game_ids": game_ids,
                    "game_names": {gid: game_name_map.get(gid, "Unknown") for gid in game_ids},
                    "is_premium_conflict": len(premium_wins) > 1,
                })
            return drawing_state, conflicts_needing_input, auto_resolved

    return drawing_state, [], auto_resolved
