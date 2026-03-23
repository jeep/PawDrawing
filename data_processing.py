"""Data processing for Play-to-Win games and entries.

Handles de-duplication, validation, and grouping of PlayToWin entries.
"""


def process_entries(entries):
    """Process raw PlayToWin entries: filter, normalize identifiers, and de-duplicate.

    Uses badge_id as the primary identifier. Falls back to user_id, then name
    for entries without a badge (common in library-only mode).
    Entries with no usable identifier are excluded.

    De-duplication keeps one entry per (badge_id, librarygame_id) pair.
    When duplicates exist, the first occurrence is kept.

    Returns a list of unique, valid entries.
    """
    seen = set()
    result = []

    for entry in entries:
        badge_id = entry.get("badge_id") or entry.get("user_id") or entry.get("name")
        if not badge_id:
            continue

        # Normalize: ensure badge_id is set for downstream use
        entry["badge_id"] = badge_id

        game_id = entry.get("librarygame_id")
        key = (badge_id, game_id)
        if key in seen:
            continue

        seen.add(key)
        result.append(entry)

    return result


def group_entries_by_game(entries, games):
    """Group processed entries by librarygame_id and attach game metadata.

    Returns a list of dicts, one per game:
        {
            "game": { ... game data ... },
            "entries": [ ... entries for this game ... ],
            "entrant_count": int,
        }

    Games with zero entries are included with an empty entries list.
    """
    # Index entries by game id
    entries_by_game = {}
    for entry in entries:
        game_id = entry.get("librarygame_id")
        entries_by_game.setdefault(game_id, []).append(entry)

    result = []
    for game in games:
        game_id = game.get("id")
        game_entries = entries_by_game.get(game_id, [])
        result.append({
            "game": game,
            "entries": game_entries,
            "entrant_count": len(game_entries),
        })

    return result
