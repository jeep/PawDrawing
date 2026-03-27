"""Run the app in demo mode with mock session data for UX testing.

Usage:
    FLASK_SECRET_KEY=demo python run_demo.py

Opens on http://localhost:5001 with the games page pre-loaded.
No TTE connection needed — all API calls return mock data.
"""

import os
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

os.environ.setdefault("FLASK_SECRET_KEY", "demo-secret-key-for-local-testing")

from app import create_app
from session_keys import SK
from tte_client import TTEClient

app = create_app()

# ── Stable mock UUIDs (must pass is_valid_tte_id validation) ───────────
_NS = uuid.UUID("12345678-1234-1234-1234-123456789abc")
GAME_CATAN = str(uuid.uuid5(_NS, "game-catan"))
GAME_AZUL = str(uuid.uuid5(_NS, "game-azul"))
GAME_WINGSPAN = str(uuid.uuid5(_NS, "game-wingspan"))
GAME_TTR = str(uuid.uuid5(_NS, "game-ttr"))
GAME_PANDEMIC = str(uuid.uuid5(_NS, "game-pandemic"))
GAME_CODENAMES = str(uuid.uuid5(_NS, "game-codenames"))
GAME_SPLENDOR = str(uuid.uuid5(_NS, "game-splendor"))
GAME_7WONDERS = str(uuid.uuid5(_NS, "game-7wonders"))
GAME_MYSTERIUM = str(uuid.uuid5(_NS, "game-mysterium"))
GAME_DIXIT = str(uuid.uuid5(_NS, "game-dixit"))
CO_AZUL = str(uuid.uuid5(_NS, "co-azul"))
CO_AZUL_OLD = str(uuid.uuid5(_NS, "co-azul-old"))
CO_PANDEMIC = str(uuid.uuid5(_NS, "co-pandemic"))
CO_CATAN_OLD1 = str(uuid.uuid5(_NS, "co-catan-old1"))
CO_CATAN_OLD2 = str(uuid.uuid5(_NS, "co-catan-old2"))
P2W_AZUL_1 = str(uuid.uuid5(_NS, "p2w-azul-1"))
P2W_AZUL_2 = str(uuid.uuid5(_NS, "p2w-azul-2"))
P2W_AZUL_3 = str(uuid.uuid5(_NS, "p2w-azul-3"))
P2W_CATAN_1 = str(uuid.uuid5(_NS, "p2w-catan-1"))
P2W_CATAN_2 = str(uuid.uuid5(_NS, "p2w-catan-2"))
P2W_PAND_1 = str(uuid.uuid5(_NS, "p2w-pand-1"))
BADGE_B1 = str(uuid.uuid5(_NS, "badge-b1"))
BADGE_B2 = str(uuid.uuid5(_NS, "badge-b2"))
BADGE_B3 = str(uuid.uuid5(_NS, "badge-b3"))

# ── Mock game catalog ──────────────────────────────────────────────────

MOCK_GAMES = [
    {"id": GAME_CATAN, "name": "Catan", "catalog_number": "PTW-001",
     "is_play_to_win": 1, "is_checked_out": 0, "is_in_circulation": 1,
     "min_play_time": 60, "max_play_time": 90, "min_players": 3, "max_players": 4,
     "checkout_count": 5, "_p2w_count": 12, "publisher_name": "Catan Studio"},
    {"id": GAME_AZUL, "name": "Azul", "catalog_number": "PTW-002",
     "is_play_to_win": 1, "is_checked_out": 1, "is_in_circulation": 1,
     "min_play_time": 30, "max_play_time": 45, "min_players": 2, "max_players": 4,
     "checkout_count": 8, "_p2w_count": 7, "publisher_name": "Plan B Games",
     "_renter_name": "Jamie Rodriguez", "_checkout_id": CO_AZUL},
    {"id": GAME_WINGSPAN, "name": "Wingspan", "catalog_number": "PTW-003",
     "is_play_to_win": 1, "is_checked_out": 0, "is_in_circulation": 1,
     "min_play_time": 40, "max_play_time": 70, "min_players": 1, "max_players": 5,
     "checkout_count": 3, "_p2w_count": 9, "publisher_name": "Stonemaier Games"},
    {"id": GAME_TTR, "name": "Ticket to Ride", "catalog_number": "PTW-004",
     "is_play_to_win": 1, "is_checked_out": 0, "is_in_circulation": 1,
     "min_play_time": 30, "max_play_time": 60, "min_players": 2, "max_players": 5,
     "checkout_count": 12, "_p2w_count": 15, "publisher_name": "Days of Wonder"},
    {"id": GAME_PANDEMIC, "name": "Pandemic", "catalog_number": "PTW-005",
     "is_play_to_win": 1, "is_checked_out": 1, "is_in_circulation": 1,
     "min_play_time": 45, "max_play_time": 60, "min_players": 2, "max_players": 4,
     "checkout_count": 6, "_p2w_count": 4, "publisher_name": "Z-Man Games",
     "_renter_name": "Sam Chen", "_checkout_id": CO_PANDEMIC},
    {"id": GAME_CODENAMES, "name": "Codenames", "catalog_number": "PTW-006",
     "is_play_to_win": 1, "is_checked_out": 0, "is_in_circulation": 1,
     "min_play_time": 15, "max_play_time": 20, "min_players": 4, "max_players": 8,
     "checkout_count": 15, "_p2w_count": 20, "publisher_name": "Czech Games Edition"},
    {"id": GAME_SPLENDOR, "name": "Splendor", "catalog_number": "PTW-007",
     "is_play_to_win": 1, "is_checked_out": 0, "is_in_circulation": 1,
     "min_play_time": 20, "max_play_time": 30, "min_players": 2, "max_players": 4,
     "checkout_count": 4, "_p2w_count": 6, "publisher_name": "Space Cowboys"},
    {"id": GAME_7WONDERS, "name": "7 Wonders", "catalog_number": "PTW-008",
     "is_play_to_win": 1, "is_checked_out": 0, "is_in_circulation": 1,
     "min_play_time": 30, "max_play_time": 30, "min_players": 3, "max_players": 7,
     "checkout_count": 2, "_p2w_count": 3, "publisher_name": "Repos Production"},
    {"id": GAME_MYSTERIUM, "name": "Mysterium", "catalog_number": "LIB-009",
     "is_play_to_win": 0, "is_checked_out": 0, "is_in_circulation": 1,
     "min_play_time": 30, "max_play_time": 45, "min_players": 2, "max_players": 7,
     "checkout_count": 1, "_p2w_count": 0, "publisher_name": "Libellud"},
    {"id": GAME_DIXIT, "name": "Dixit", "catalog_number": "LIB-010",
     "is_play_to_win": 0, "is_checked_out": 0, "is_in_circulation": 1,
     "min_play_time": 20, "max_play_time": 30, "min_players": 3, "max_players": 8,
     "checkout_count": 0, "_p2w_count": 0, "publisher_name": "Libellud"},
]

MOCK_NOTIFICATIONS = [
    {"id": str(uuid.uuid4()), "type": "non_p2w",
     "message": "2 games in this library are not marked Play-to-Win.",
     "dismissed": False,
     "timestamp": datetime.now(timezone.utc).isoformat(),
     "details": ["Mysterium", "Dixit"]},
    {"id": str(uuid.uuid4()), "type": "warning",
     "message": "1 game checked out beyond threshold.",
     "dismissed": False,
     "timestamp": datetime.now(timezone.utc).isoformat(),
     "details": ["Azul (Jamie, 3.2h)"]},
]


# ── Monkey-patch TTEClient to return mock data ─────────────────────────

_original_init = TTEClient.__init__


def _mock_init(self, *args, **kwargs):
    _original_init(self, *args, **kwargs)
    self.session_id = "mock-session"


TTEClient.__init__ = _mock_init

# Make all API methods return sensible mock data

MOCK_BADGES = {
    "100": {"id": BADGE_B1, "name": "Jamie Rodriguez", "name_full": "Jamie Rodriguez", "badge_number": "100"},
    "205": {"id": BADGE_B2, "name": "Sam Chen", "name_full": "Sam Chen", "badge_number": "205"},
    "312": {"id": BADGE_B3, "name": "Alex Kim", "name_full": "Alex Kim", "badge_number": "312"},
}

def _mock_game_checkouts(game_id, **kw):
    """Return mock checkouts for a specific game."""
    azul_id = MOCK_GAMES[1]["id"]
    pandemic_id = MOCK_GAMES[4]["id"]
    catan_id = MOCK_GAMES[0]["id"]
    if game_id == azul_id:
        return [
            {"id": CO_AZUL, "librarygame_id": azul_id,
             "renter_name": "Jamie Rodriguez", "badge_id": "100",
             "date_created": "2026-03-25 06:00:00", "is_checked_in": 0},
            {"id": CO_AZUL_OLD, "librarygame_id": azul_id,
             "renter_name": "Sam Chen", "badge_id": "205",
             "date_created": "2026-03-24 14:00:00", "is_checked_in": 1,
             "checkin_date": "2026-03-24 16:30:00"},
        ]
    if game_id == pandemic_id:
        return [
            {"id": CO_PANDEMIC, "librarygame_id": pandemic_id,
             "renter_name": "Sam Chen", "badge_id": "205",
             "date_created": "2026-03-25 09:00:00", "is_checked_in": 0},
        ]
    if game_id == catan_id:
        return [
            {"id": CO_CATAN_OLD1, "librarygame_id": catan_id,
             "renter_name": "Alex Kim", "badge_id": "312",
             "date_created": "2026-03-24 10:00:00", "is_checked_in": 1,
             "checkin_date": "2026-03-24 12:00:00"},
            {"id": CO_CATAN_OLD2, "librarygame_id": catan_id,
             "renter_name": "Jamie Rodriguez", "badge_id": "100",
             "date_created": "2026-03-23 15:00:00", "is_checked_in": 1,
             "checkin_date": "2026-03-23 17:30:00"},
        ]
    return []


def _mock_game_playtowins(game_id, **kw):
    """Return mock P2W entries for a specific game."""
    azul_id = MOCK_GAMES[1]["id"]
    catan_id = MOCK_GAMES[0]["id"]
    pandemic_id = MOCK_GAMES[4]["id"]
    if game_id == azul_id:
        return [
            {"id": P2W_AZUL_1, "name": "Jamie Rodriguez", "badge_id": "100",
             "librarygame_id": azul_id, "date_created": "2026-03-25 07:00:00"},
            {"id": P2W_AZUL_2, "name": "Sam Chen", "badge_id": "205",
             "librarygame_id": azul_id, "date_created": "2026-03-24 15:00:00"},
            {"id": P2W_AZUL_3, "name": "Alex Kim", "badge_id": "312",
             "librarygame_id": azul_id, "date_created": "2026-03-24 11:00:00"},
        ]
    if game_id == catan_id:
        return [
            {"id": P2W_CATAN_1, "name": "Alex Kim", "badge_id": "312",
             "librarygame_id": catan_id, "date_created": "2026-03-24 11:30:00"},
            {"id": P2W_CATAN_2, "name": "Jamie Rodriguez", "badge_id": "100",
             "librarygame_id": catan_id, "date_created": "2026-03-23 16:00:00"},
        ]
    if game_id == pandemic_id:
        return [
            {"id": P2W_PAND_1, "name": "Sam Chen", "badge_id": "205",
             "librarygame_id": pandemic_id, "date_created": "2026-03-25 10:00:00"},
        ]
    return []


_ALL_CHECKOUTS = [
    {"id": CO_AZUL, "librarygame_id": MOCK_GAMES[1]["id"],
     "renter_name": "Jamie Rodriguez", "badge_id": "100",
     "date_created": "2026-03-25 06:00:00", "is_checked_in": 0},
    {"id": CO_PANDEMIC, "librarygame_id": MOCK_GAMES[4]["id"],
     "renter_name": "Sam Chen", "badge_id": "205",
     "date_created": "2026-03-25 09:00:00", "is_checked_in": 0},
    {"id": CO_AZUL_OLD, "librarygame_id": MOCK_GAMES[1]["id"],
     "renter_name": "Sam Chen", "badge_id": "205",
     "date_created": "2026-03-24 14:00:00", "is_checked_in": 1,
     "checkin_date": "2026-03-24 16:30:00"},
    {"id": CO_CATAN_OLD1, "librarygame_id": MOCK_GAMES[0]["id"],
     "renter_name": "Alex Kim", "badge_id": "312",
     "date_created": "2026-03-24 10:00:00", "is_checked_in": 1,
     "checkin_date": "2026-03-24 12:00:00"},
    {"id": CO_CATAN_OLD2, "librarygame_id": MOCK_GAMES[0]["id"],
     "renter_name": "Jamie Rodriguez", "badge_id": "100",
     "date_created": "2026-03-23 15:00:00", "is_checked_in": 1,
     "checkin_date": "2026-03-23 17:30:00"},
]


def _mock_library_checkouts(library_id, **kw):
    """Return mock checkouts, filtered by checked_in if provided."""
    checked_in = kw.get("checked_in")
    if checked_in is None:
        return list(_ALL_CHECKOUTS)
    target = 1 if checked_in else 0
    return [c for c in _ALL_CHECKOUTS if c.get("is_checked_in") == target]


_mock_methods = {
    "get_library_games": lambda *a, **kw: list(MOCK_GAMES),
    "get_library_game": lambda game_id, **kw: next(
        (g for g in MOCK_GAMES if g["id"] == game_id),
        {"id": game_id, "name": "Unknown Game", "is_checked_out": 0,
         "is_play_to_win": 1, "is_in_circulation": 1}),
    "get_library_checkouts": _mock_library_checkouts,
    "get_library_game_checkouts": _mock_game_checkouts,
    "get_library_game_playtowins": _mock_game_playtowins,
    "get_library_playtowins": lambda *a, **kw: [
        {"id": P2W_AZUL_1, "name": "Jamie Rodriguez", "badge_id": "100",
         "librarygame_id": MOCK_GAMES[1]["id"], "date_created": "2026-03-25 07:00:00"},
        {"id": P2W_AZUL_2, "name": "Sam Chen", "badge_id": "205",
         "librarygame_id": MOCK_GAMES[1]["id"], "date_created": "2026-03-24 15:00:00"},
        {"id": P2W_AZUL_3, "name": "Alex Kim", "badge_id": "312",
         "librarygame_id": MOCK_GAMES[1]["id"], "date_created": "2026-03-24 11:00:00"},
        {"id": P2W_CATAN_1, "name": "Alex Kim", "badge_id": "312",
         "librarygame_id": MOCK_GAMES[0]["id"], "date_created": "2026-03-24 11:30:00"},
        {"id": P2W_CATAN_2, "name": "Jamie Rodriguez", "badge_id": "100",
         "librarygame_id": MOCK_GAMES[0]["id"], "date_created": "2026-03-23 16:00:00"},
        {"id": P2W_PAND_1, "name": "Sam Chen", "badge_id": "205",
         "librarygame_id": MOCK_GAMES[4]["id"], "date_created": "2026-03-25 10:00:00"},
    ],
    "create_checkout": lambda *a, **kw: {"id": str(uuid.uuid4())},
    "checkin_game": lambda *a, **kw: {"id": str(uuid.uuid4())},
    "create_playtowin_entry": lambda *a, **kw: {"id": str(uuid.uuid4())},
    "delete_playtowin": lambda *a, **kw: {},
    "update_library_game": lambda *a, **kw: {},
    "search_badges": lambda conv_id, query, **kw: (
        [MOCK_BADGES[query]] if query in MOCK_BADGES else []
    ),
    "reset_checkout_time": lambda *a, **kw: {},
    "get_convention_playtowins": lambda *a, **kw: [
        {"id": P2W_AZUL_1, "name": "Jamie Rodriguez", "badge_id": "100",
         "librarygame_id": MOCK_GAMES[1]["id"], "date_created": "2026-03-25 07:00:00"},
        {"id": P2W_AZUL_2, "name": "Sam Chen", "badge_id": "205",
         "librarygame_id": MOCK_GAMES[1]["id"], "date_created": "2026-03-24 15:00:00"},
        {"id": P2W_AZUL_3, "name": "Alex Kim", "badge_id": "312",
         "librarygame_id": MOCK_GAMES[1]["id"], "date_created": "2026-03-24 11:00:00"},
        {"id": P2W_CATAN_1, "name": "Alex Kim", "badge_id": "312",
         "librarygame_id": MOCK_GAMES[0]["id"], "date_created": "2026-03-24 11:30:00"},
        {"id": P2W_CATAN_2, "name": "Jamie Rodriguez", "badge_id": "100",
         "librarygame_id": MOCK_GAMES[0]["id"], "date_created": "2026-03-23 16:00:00"},
        {"id": P2W_PAND_1, "name": "Sam Chen", "badge_id": "205",
         "librarygame_id": MOCK_GAMES[4]["id"], "date_created": "2026-03-25 10:00:00"},
    ],
}

for method_name, return_fn in _mock_methods.items():
    setattr(TTEClient, method_name, lambda self, *a, _fn=return_fn, **kw: _fn(*a, **kw))


# ── Seed session on first request ──────────────────────────────────────

_DEMO_VERSION = 3  # bump to force reseed on next visit

@app.before_request
def seed_demo_session():
    """Pre-populate session with mock data if not already set."""
    from flask import session
    if (session.get(SK.TTE_SESSION_ID) == "demo-session"
            and session.get("_demo_version") == _DEMO_VERSION):
        return  # already seeded with current data
    session[SK.TTE_SESSION_ID] = "demo-session"
    session["_demo_version"] = _DEMO_VERSION
    session[SK.TTE_USERNAME] = "demo_owner"
    session[SK.TTE_USER_ID] = "user-demo"
    session[SK.CONVENTION_ID] = "conv-demo"
    session[SK.CONVENTION_NAME] = "PawCon 2026"
    session[SK.LIBRARY_ID] = "lib-demo"
    session[SK.LIBRARY_NAME] = "PawCon Game Library"
    session[SK.APP_MODE] = "management"
    session[SK.AUTH_MODE] = "owner"
    session[SK.CACHED_GAMES] = list(MOCK_GAMES)
    session[SK.CACHED_ENTRIES] = [
        {"id": P2W_AZUL_1, "name": "Jamie Rodriguez", "badge_id": "100",
         "librarygame_id": MOCK_GAMES[1]["id"], "date_created": "2026-03-25 07:00:00"},
        {"id": P2W_AZUL_2, "name": "Sam Chen", "badge_id": "205",
         "librarygame_id": MOCK_GAMES[1]["id"], "date_created": "2026-03-24 15:00:00"},
        {"id": P2W_AZUL_3, "name": "Alex Kim", "badge_id": "312",
         "librarygame_id": MOCK_GAMES[1]["id"], "date_created": "2026-03-24 11:00:00"},
        {"id": P2W_CATAN_1, "name": "Alex Kim", "badge_id": "312",
         "librarygame_id": MOCK_GAMES[0]["id"], "date_created": "2026-03-24 11:30:00"},
        {"id": P2W_CATAN_2, "name": "Jamie Rodriguez", "badge_id": "100",
         "librarygame_id": MOCK_GAMES[0]["id"], "date_created": "2026-03-23 16:00:00"},
        {"id": P2W_PAND_1, "name": "Sam Chen", "badge_id": "205",
         "librarygame_id": MOCK_GAMES[4]["id"], "date_created": "2026-03-25 10:00:00"},
    ]
    session[SK.NOTIFICATIONS] = list(MOCK_NOTIFICATIONS)
    session[SK.PREMIUM_GAMES] = [g["id"] for g in MOCK_GAMES if g.get("is_play_to_win")]
    session[SK.PERSON_CACHE] = {
        "100": {"name": "Jamie Rodriguez", "badge_id": BADGE_B1},
        "205": {"name": "Sam Chen", "badge_id": BADGE_B2},
        "312": {"name": "Alex Kim", "badge_id": BADGE_B3},
    }
    session[SK.PLAY_GROUPS] = {
        "Jamie Rodriguez": ["Sam Chen", "Alex Kim"],
        "Sam Chen": ["Jamie Rodriguez"],
    }


if __name__ == "__main__":
    print("\n  PawDrawing Demo Mode")
    print("  ====================")
    print("  Open: http://localhost:5001/games")
    print("  10 mock games, 2 checked out, 2 notifications")
    print("  All API calls return mock data — no TTE needed\n")
    app.run(debug=True, port=5001)
