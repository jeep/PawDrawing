#!/usr/bin/env python3
"""Populate a TTE library with test games and Play-to-Win entries.

Creates 100 games and 300 participants with randomized entry distributions:
  - 2 games with 0 entries
  - 10 games with 2-5 entries
  - 10 games with 50+ entries
  - 78 games with 5-50 entries

Participant play counts:
  - 20 participants play 20+ games
  - 20 participants play 1-3 games
  - 260 participants play 4-19 games (weighted toward 5-10)

Usage:
    python populate_library.py               # Full run: create games + entries
    python populate_library.py --entries-only  # Skip game creation, use existing games
"""

import argparse
import getpass
import random
import sys
import time

import requests

BASE_URL = "https://tabletop.events/api"
API_KEY = "83B7B502-252C-11F1-82CC-5911EC97371B"
USERNAME = "jeepeterson"
LIBRARY_NAME = "PAW Test"

NUM_GAMES = 100
NUM_PARTICIPANTS = 300

# Rate limiting
MIN_REQUEST_INTERVAL = 1.0
_last_request_time = 0.0


def _throttle():
    global _last_request_time
    elapsed = time.monotonic() - _last_request_time
    if elapsed < MIN_REQUEST_INTERVAL:
        time.sleep(MIN_REQUEST_INTERVAL - elapsed)
    _last_request_time = time.monotonic()


def api_request(method, path, session_id=None, params=None, json_body=None):
    _throttle()
    url = f"{BASE_URL}/{path.lstrip('/')}"
    if params is None:
        params = {}
    if session_id:
        params["session_id"] = session_id

    resp = requests.request(method, url, params=params, json=json_body, timeout=30)
    if not resp.ok:
        print(f"  API error {resp.status_code}: {resp.text[:300]}")
        sys.exit(1)
    data = resp.json()
    return data.get("result", data)


def get_all_pages(path, session_id, params=None):
    if params is None:
        params = {}
    params["_items_per_page"] = 100
    params["_page_number"] = 1
    all_items = []
    while True:
        result = api_request("GET", path, session_id, params=dict(params))
        all_items.extend(result.get("items", []))
        paging = result.get("paging", {})
        total_pages = int(paging.get("total_pages", 1))
        if params["_page_number"] >= total_pages:
            break
        params["_page_number"] += 1
    return all_items


# ── Game name generation ───────────────────────────────────────────────

BOARD_GAME_NAMES = [
    "Catan", "Ticket to Ride", "Pandemic", "Carcassonne", "Azul",
    "Wingspan", "Splendor", "7 Wonders", "Codenames", "Dominion",
    "Terraforming Mars", "Scythe", "Spirit Island", "Gloomhaven",
    "Root", "Everdell", "Brass: Birmingham", "Viticulture",
    "Concordia", "Great Western Trail", "Agricola", "Puerto Rico",
    "Power Grid", "Castles of Burgundy", "Clank!", "Ark Nova",
    "Cascadia", "Patchwork", "Jaipur", "Lost Ruins of Arnak",
    "Dune: Imperium", "Quacks of Quedlinburg", "Mysterium",
    "Champions of Midgard", "Dead of Winter", "Blood Rage",
    "Rising Sun", "Inis", "Kemet", "Cyclades",
    "Twilight Imperium", "Eclipse", "Through the Ages",
    "Terra Mystica", "Gaia Project", "Feast for Odin",
    "Le Havre", "Caverna", "Ora et Labora", "Hallertau",
    "Paladins of the West Kingdom", "Architects of the West Kingdom",
    "Viscounts of the West Kingdom", "Raiders of the North Sea",
    "Nemesis", "Mansions of Madness", "Betrayal at House on the Hill",
    "Villainous", "Photosynthesis", "Sagrada",
    "Calico", "Barenpark", "Kingdomino", "Sushi Go Party!",
    "Century: Spice Road", "Star Realms", "Hero Realms",
    "Marvel Champions", "Arkham Horror: The Card Game",
    "Eldritch Horror", "Robinson Crusoe", "Mage Knight",
    "War of the Ring", "Star Wars: Rebellion", "Twilight Struggle",
    "Undaunted: Normandy", "Unmatched", "Santorini",
    "Hive", "Onitama", "Blokus", "Dixit", "Wavelength",
    "Decrypto", "Just One", "Skull", "The Crew",
    "Hanabi", "The Mind", "Love Letter", "Coup",
    "Citadels", "Sheriff of Nottingham", "Cosmic Encounter",
    "Small World", "Ethnos", "Alhambra", "Istanbul",
    "Five Tribes", "Lords of Waterdeep", "Stone Age",
    "Marco Polo", "Troyes",
]

FIRST_NAMES = [
    "James", "Mary", "Robert", "Patricia", "John", "Jennifer", "Michael",
    "Linda", "David", "Elizabeth", "William", "Barbara", "Richard", "Susan",
    "Joseph", "Jessica", "Thomas", "Sarah", "Christopher", "Karen",
    "Charles", "Lisa", "Daniel", "Nancy", "Matthew", "Betty", "Anthony",
    "Margaret", "Mark", "Sandra", "Donald", "Ashley", "Steven", "Kimberly",
    "Paul", "Emily", "Andrew", "Donna", "Joshua", "Michelle", "Kenneth",
    "Carol", "Kevin", "Amanda", "Brian", "Dorothy", "George", "Melissa",
    "Timothy", "Deborah", "Ronald", "Stephanie", "Edward", "Rebecca",
    "Jason", "Sharon", "Jeffrey", "Laura", "Ryan", "Cynthia",
    "Jacob", "Kathleen", "Gary", "Amy", "Nicholas", "Angela", "Eric",
    "Shirley", "Jonathan", "Anna", "Stephen", "Brenda", "Larry", "Pamela",
    "Justin", "Emma", "Scott", "Nicole", "Brandon", "Helen", "Benjamin",
    "Samantha", "Samuel", "Katherine", "Raymond", "Christine", "Gregory",
    "Debra", "Frank", "Rachel", "Alexander", "Carolyn", "Patrick", "Janet",
    "Jack", "Catherine", "Dennis", "Maria", "Jerry", "Heather",
]

LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
    "Davis", "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez",
    "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin",
    "Lee", "Perez", "Thompson", "White", "Harris", "Sanchez", "Clark",
    "Ramirez", "Lewis", "Robinson", "Walker", "Young", "Allen", "King",
    "Wright", "Scott", "Torres", "Nguyen", "Hill", "Flores", "Green",
    "Adams", "Nelson", "Baker", "Hall", "Rivera", "Campbell", "Mitchell",
    "Carter", "Roberts", "Gomez", "Phillips", "Evans", "Turner", "Diaz",
    "Parker", "Cruz", "Edwards", "Collins", "Reyes", "Stewart", "Morris",
    "Morales", "Murphy", "Cook", "Rogers", "Gutierrez", "Ortiz", "Morgan",
    "Cooper", "Peterson", "Bailey", "Reed", "Kelly", "Howard", "Ramos",
    "Kim", "Cox", "Ward", "Richardson", "Watson", "Brooks", "Chavez",
    "Wood", "James", "Bennett", "Gray", "Mendoza", "Ruiz", "Hughes",
    "Price", "Alvarez", "Castillo", "Sanders", "Patel", "Myers", "Long",
    "Ross", "Foster", "Jimenez",
]


def generate_participant_names(n, rng):
    """Generate n unique participant names."""
    names = set()
    while len(names) < n:
        first = rng.choice(FIRST_NAMES)
        last = rng.choice(LAST_NAMES)
        name = f"{first} {last}"
        names.add(name)
    return sorted(names)


# ── Distribution logic ─────────────────────────────────────────────────

def assign_entry_counts_to_games(rng):
    """Return a list of 100 target entry counts per game.

    - 2 games: 0 entries
    - 10 games: 2-5 entries
    - 10 games: 50-70 entries
    - 78 games: 5-50 entries
    """
    counts = []
    counts.extend([0] * 2)
    counts.extend([rng.randint(2, 5) for _ in range(10)])
    counts.extend([rng.randint(50, 70) for _ in range(10)])
    counts.extend([rng.randint(5, 50) for _ in range(78)])
    rng.shuffle(counts)
    return counts


def assign_play_counts_to_participants(rng):
    """Return a list of 300 target play counts per participant.

    - 20 participants: 20-35 games
    - 20 participants: 1-3 games
    - 260 participants: 4-19 games (weighted toward 5-10)
    """
    counts = []
    counts.extend([rng.randint(20, 35) for _ in range(20)])
    counts.extend([rng.randint(1, 3) for _ in range(20)])
    # Weighted distribution favoring 5-10
    for _ in range(260):
        # 60% chance of 5-10, 40% chance of 4-19
        if rng.random() < 0.6:
            counts.append(rng.randint(5, 10))
        else:
            counts.append(rng.randint(4, 19))
    rng.shuffle(counts)
    return counts


def build_entry_assignments(game_entry_counts, participant_play_counts, rng):
    """Build a set of (participant_index, game_index) pairs.

    Tries to satisfy both per-game entry counts and per-participant play counts
    using a probabilistic approach.
    """
    num_games = len(game_entry_counts)
    num_participants = len(participant_play_counts)

    # Track remaining capacity
    game_remaining = list(game_entry_counts)
    participant_remaining = list(participant_play_counts)
    assignments = set()

    # Games with 0 entries stay empty
    eligible_games = [i for i in range(num_games) if game_entry_counts[i] > 0]

    # Sort participants by play count descending (assign heavy players first)
    participant_order = sorted(
        range(num_participants),
        key=lambda i: participant_play_counts[i],
        reverse=True,
    )

    for p_idx in participant_order:
        target = participant_remaining[p_idx]
        if target <= 0:
            continue

        # Pick games weighted by remaining capacity
        available = [g for g in eligible_games if game_remaining[g] > 0 and (p_idx, g) not in assignments]
        if not available:
            available = [g for g in eligible_games if (p_idx, g) not in assignments]

        num_to_assign = min(target, len(available))
        if num_to_assign <= 0:
            continue

        # Weight by remaining capacity (higher remaining = more likely to be picked)
        weights = [max(game_remaining[g], 1) for g in available]
        chosen = []
        for _ in range(num_to_assign):
            if not available:
                break
            selected = rng.choices(available, weights=weights, k=1)[0]
            chosen.append(selected)
            idx = available.index(selected)
            available.pop(idx)
            weights.pop(idx)

        for g_idx in chosen:
            assignments.add((p_idx, g_idx))
            game_remaining[g_idx] -= 1
            participant_remaining[p_idx] -= 1

    return assignments


# ── Main ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Populate a TTE library with test data.")
    parser.add_argument("--entries-only", action="store_true",
                        help="Skip game creation, create entries for existing games")
    args = parser.parse_args()

    rng = random.Random(42)

    password = getpass.getpass(f"TTE password for {USERNAME}: ")

    # Login
    print("Logging in...")
    result = api_request("POST", "/session", json_body={
        "username": USERNAME,
        "password": password,
        "api_key_id": API_KEY,
    })
    session_id = result["id"]
    user_id = result.get("user_id")
    print(f"  Logged in (user_id: {user_id})")

    # Find library
    print(f"Finding library '{LIBRARY_NAME}'...")
    libraries = get_all_pages(f"/user/{user_id}/libraries", session_id)
    library = next((lib for lib in libraries if lib["name"] == LIBRARY_NAME), None)
    if not library:
        print(f"  Library '{LIBRARY_NAME}' not found. Available:")
        for lib in libraries:
            print(f"    - {lib['name']} ({lib['id']})")
        sys.exit(1)
    library_id = library["id"]
    print(f"  Found: {library_id}")

    # Check existing games
    print("Checking existing games...")
    existing_games = get_all_pages(f"/library/{library_id}/games", session_id)
    if args.entries_only:
        if not existing_games:
            print("  No existing games found. Run without --entries-only first.")
            sys.exit(1)
        print(f"  Using {len(existing_games)} existing games (--entries-only mode).")
    elif existing_games:
        print(f"  Library already has {len(existing_games)} games.")
        answer = input("  Delete existing games first? (y/N): ").strip().lower()
        if answer == "y":
            print(f"  Deleting {len(existing_games)} existing games...")
            for i, game in enumerate(existing_games, 1):
                api_request("DELETE", f"/librarygame/{game['id']}", session_id)
                print(f"    Deleted {i}/{len(existing_games)}: {game['name']}")
        else:
            print("  Keeping existing games. Aborting to avoid confusion.")
            sys.exit(0)

    # Generate distributions
    print("\nGenerating distributions...")
    game_entry_counts = assign_entry_counts_to_games(rng)
    participant_play_counts = assign_play_counts_to_participants(rng)
    participant_names = generate_participant_names(NUM_PARTICIPANTS, rng)

    total_entries = sum(game_entry_counts)
    total_plays = sum(participant_play_counts)
    print(f"  Target entries by games: {total_entries}")
    print(f"  Target plays by participants: {total_plays}")
    print(f"  Games with 0 entries: {sum(1 for c in game_entry_counts if c == 0)}")
    print(f"  Games with 2-5 entries: {sum(1 for c in game_entry_counts if 2 <= c <= 5)}")
    print(f"  Games with 50+ entries: {sum(1 for c in game_entry_counts if c >= 50)}")
    print(f"  Participants with 20+ plays: {sum(1 for c in participant_play_counts if c >= 20)}")
    print(f"  Participants with 1-3 plays: {sum(1 for c in participant_play_counts if 1 <= c <= 3)}")

    # Build assignments
    assignments = build_entry_assignments(game_entry_counts, participant_play_counts, rng)
    print(f"  Total entries to create: {len(assignments)}")

    # Verify constraints
    from collections import Counter
    games_per_participant = Counter(p for p, g in assignments)
    entries_per_game = Counter(g for p, g in assignments)
    zero_entry_games = sum(1 for i in range(NUM_GAMES) if entries_per_game.get(i, 0) == 0)
    print(f"\n  Actual distribution:")
    print(f"    Games with 0 entries: {zero_entry_games}")
    print(f"    Games with 2-5 entries: {sum(1 for g, c in entries_per_game.items() if 2 <= c <= 5)}")
    print(f"    Games with 50+ entries: {sum(1 for g, c in entries_per_game.items() if c >= 50)}")
    participants_20plus = sum(1 for p, c in games_per_participant.items() if c >= 20)
    participants_1to3 = sum(1 for p, c in games_per_participant.items() if 1 <= c <= 3)
    print(f"    Participants with 20+ plays: {participants_20plus}")
    print(f"    Participants with 1-3 plays: {participants_1to3}")

    input("\nPress Enter to start creating data on TTE (Ctrl+C to cancel)...")

    # Create or reuse games
    if args.entries_only:
        # Sort existing games by name to get consistent ordering
        existing_games.sort(key=lambda g: g["name"])
        game_ids = [g["id"] for g in existing_games]
        print(f"\nUsing {len(game_ids)} existing games.")
    else:
        print(f"\nCreating {NUM_GAMES} games...")
        game_names = BOARD_GAME_NAMES[:NUM_GAMES]
        game_ids = []
        for i, name in enumerate(game_names, 1):
            result = api_request("POST", "/librarygame", session_id, json_body={
                "library_id": library_id,
                "name": name,
                "catalog_number": f"PTW-{i:03d}",
                "is_play_to_win": 1,
            })
            game_id = result["id"]
            game_ids.append(game_id)
            print(f"  [{i}/{NUM_GAMES}] Created: {name} ({game_id})")

    # Create entries
    # Sort assignments by game for clearer progress display
    sorted_assignments = sorted(assignments, key=lambda x: (x[1], x[0]))
    total = len(sorted_assignments)
    print(f"\nCreating {total} Play-to-Win entries...")

    for i, (p_idx, g_idx) in enumerate(sorted_assignments, 1):
        participant_name = participant_names[p_idx]
        game_id = game_ids[g_idx]
        api_request("POST", "/playtowin", session_id, json_body={
            "library_id": library_id,
            "librarygame_id": game_id,
            "name": participant_name,
        })
        if i % 25 == 0 or i == total:
            print(f"  [{i}/{total}] entries created...")

    # Summary
    print(f"\n{'='*60}")
    if args.entries_only:
        print(f"Done! Created {total} entries for {len(game_ids)} existing games.")
    else:
        print(f"Done! Created {NUM_GAMES} games and {total} entries.")
    print(f"Library: {LIBRARY_NAME} ({library_id})")
    print(f"{'='*60}")

    # Logout
    api_request("DELETE", f"/session/{session_id}", session_id)
    print("Logged out.")


if __name__ == "__main__":
    main()
