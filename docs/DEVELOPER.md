# Developer & Architecture Guide

## Project Overview

PawDrawing is a web application for running Play-to-Win (P2W)/Play and Win (PAW) prize drawings at tabletop gaming conventions. It integrates with the [tabletop.events](https://tabletop.events) (TTE) API to pull convention data, run a randomized drawing, and push win results back.

**Tech stack:**

- **Python 3** with **Flask 3.x** (app factory pattern, Blueprint routing)
- **Flask-WTF** for CSRF protection on all POST routes
- **requests** for HTTP communication with the TTE REST API
- **python-dotenv** for environment variable management
- **pytest** for testing (with `unittest.mock`)
- Server-side session storage via **flask-session** with **cachelib** (`FileSystemCache`)
- **Application logging** via Python's `logging` module across all route modules and the TTE client

## Project Structure

```
PawDrawing/
├── app.py                  # App factory (create_app), CSRF init, session cleanup
├── config.py               # Config class (env vars)
├── run.py                  # Dev server entry point
├── session_keys.py         # SK class — constants for all Flask session keys
├── tte_client.py           # TTE API client with rate limiting & pagination
├── drawing.py              # Drawing algorithm (shuffle, conflicts, resolution)
├── data_processing.py      # Entry validation, de-duplication, grouping
├── shared_state.py         # Library-scoped shared state (cross-device persistence)
├── populate_library.py     # Test data generator for TTE libraries
├── run_demo.py             # Demo mode with mock data (no TTE needed)
├── requirements.txt        # pip dependencies
├── .env.example            # Template for environment variables
├── startup.sh              # Azure App Service startup command
├── routes/
│   ├── __init__.py             # Blueprint definition & module imports
│   ├── helpers.py              # Shared utilities (auth, client, error handler, validators)
│   ├── auth.py                 # Login, logout, health check, index redirect
│   ├── convention.py           # Convention search & library selection
│   ├── drawing.py              # Drawing execution, results, conflict resolution
│   ├── drawing_actions.py      # AJAX: pickup, award-to, award-next, not-here, redraw, push, export
│   ├── games.py                # Unified game/library management, checkout, P2W, volunteer login
│   └── suspicious.py           # Suspicious checkout detection (long checkouts, partner patterns)
├── static/
│   ├── css/
│   │   ├── drawing.css         # Styles for drawing results page
│   │   └── games.css           # Styles for games & players pages
│   └── js/
│       ├── drawing.js          # Client-side logic for drawing results
│       └── games.js            # Client-side logic for games page
├── templates/
│   ├── base.html               # Base layout with flash messages & loading overlay
│   ├── login.html              # Login form (username, password, API key)
│   ├── volunteer_login.html    # Volunteer login form (checkout privilege required)
│   ├── convention_select.html  # Convention search & library browse
│   ├── convention_confirm.html # Confirm selected convention
│   ├── library_confirm.html    # Confirm selected library (no convention)
│   ├── games.html              # Game list with management controls (checkout, P2W, settings)
│   ├── players.html            # Player management with remove/restore controls
│   ├── drawing_prep.html       # Pre-drawing checklist (component check, stats, alerts)
│   └── drawing_results.html    # Results with conflicts, pickup, push, export
├── tests/
│   ├── conftest.py             # Disables CSRF for test client
│   ├── test_routes.py          # Route/view tests (197)
│   ├── test_library_mgmt.py    # Library management route tests (62)
│   ├── test_drawing.py         # Drawing algorithm tests (43)
│   ├── test_tte_client.py      # API client tests (22)
│   └── test_data_processing.py # Data processing tests (21)
├── .githooks/
│   └── commit-msg          # Conventional Commits hook
├── .github/
│   └── workflows/
│       └── deploy.yml      # CI/CD: test + deploy to Azure App Service
└── docs/
    ├── DEVELOPER.md                    # This file
    ├── USER_GUIDE.md                   # User guide
    ├── Requirements.md                 # Drawing requirements document
    ├── PawLibraryMgmt Requirements.md  # Library management requirements document
    └── UNIFIED_UI_DESIGN.md            # Unified UI design spec
```

## Module Reference

### `app.py`

App factory. `create_app()`:

1. Instantiates Flask and loads `Config`.
2. Initializes server-side sessions via `Session(app)`.
3. Initializes CSRF protection via `CSRFProtect(app)` from `flask-wtf`.
4. Registers the `main_bp` blueprint from the `routes` package.
5. Runs `_cleanup_old_sessions()` to delete expired session files on startup.

No database or migration.

### `config.py`

Loads `.env` via `python-dotenv`, then exposes:

| Attribute | Env Var | Default | Purpose |
|-----------|---------|---------|---------|
| `SECRET_KEY` | `FLASK_SECRET_KEY` | *(required — raises `RuntimeError` if unset)* | Flask session signing |
| `TTE_API_KEY` | `TTE_API_KEY` | `""` | Fallback TTE API key (per-user key from login takes precedence) |
| `TTE_BASE_URL` | — | `https://tabletop.events/api` | API base URL (hardcoded) |
| `SESSION_TYPE` | — | `"cachelib"` | flask-session backend type |
| `SESSION_CACHELIB` | — | `FileSystemCache("flask_session")` | Server-side session storage; directory overridden via `SESSION_FILE_DIR` env var |
| `SESSION_PERMANENT` | — | `True` | Sessions persist across browser restarts |
| `PERMANENT_SESSION_LIFETIME` | — | `30 days` | Session expiry |
| `SHARED_STATE_DIR` | `SHARED_STATE_DIR` | `"shared_state"` | Directory for library-scoped shared state files |

### `session_keys.py`

The `SK` class defines string constants for every Flask session key used in the application. All route modules import from `SK` instead of using raw strings.

### `routes/` package

Routes are organized into a Blueprint package. `routes/__init__.py` creates `main_bp` and imports all route modules. Shared utilities live in `routes/helpers.py`.

#### `routes/helpers.py`

- `login_required(f=None, *, api=False)` — decorator that checks for a valid session. Returns 401 JSON for API routes or redirects to login for page routes.
- `_get_client()` — creates a `TTEClient` with the user's per-session API key and session ID.
- `_handle_api_error(exc, fallback_url, action)` — handles `TTEAPIError` uniformly: clears session on 401/403, flashes a descriptive message, logs the error, and redirects.
- `is_valid_tte_id(value)` — validates that a TTE entity ID matches UUID format.
- `is_valid_badge_id(value)` — validates that a badge ID is a non-empty alphanumeric string.

#### Route modules

| Module | Responsibility |
|--------|---------------|
| `auth.py` | Login, logout, health check (`/health`), index redirect |
| `convention.py` | Convention search, convention/library selection, library browsing |
| `drawing.py` | Run drawing, display results, dismiss conflict games, resolve conflicts |
| `drawing_actions.py` | Pickup toggle, award-to, award-next, not-here, redraw unclaimed, push to TTE, CSV export |
| `games.py` | Unified game/library management: game list, premium toggles, eject/uneject, entrants, checkout/checkin, P2W entry, badge lookup, notifications, settings, suspicious detection, mark-all-P2W, drawing prep, volunteer login/logout |
| `suspicious.py` | Suspicious checkout detection: long-checkout threshold, partner pattern analysis |

**All routes:**

| Method | Path | Module | Function | Purpose |
|--------|------|--------|----------|---------|
| GET | `/health` | auth | `health` | Health check (returns JSON) |
| GET | `/` | auth | `index` | Redirect to login or convention select |
| GET/POST | `/login` | auth | `login` | Login form and TTE authentication |
| POST | `/logout` | auth | `logout` | Destroy session |
| GET | `/convention` | convention | `convention_select` | Convention search page |
| GET | `/convention/search` | convention | `convention_search` | AJAX: search conventions |
| POST | `/convention/select` | convention | `convention_select_route` | Fetch and confirm convention |
| GET | `/library/browse` | convention | `library_browse` | AJAX: list user's libraries |
| POST | `/library/select` | convention | `library_select_route` | Fetch and confirm library (no convention) |
| GET | `/games` | games | `games` | Load and display games (Management tab) |
| POST | `/games/mode` | games | `switch_mode` | Switch mode and redirect (management/players/prep/drawing) |
| GET | `/games/players` | games | `players` | Player management (list, remove, restore) |
| GET | `/games/prep` | games | `drawing_prep` | Drawing Prep checklist (component check, stats, alerts) |
| POST | `/games/premium` | games | `set_premium_games` | AJAX: save premium designations |
| POST | `/games/eject` | games | `eject_player` | AJAX: eject player from drawing |
| POST | `/games/uneject` | games | `uneject_player` | AJAX: undo an ejection |
| GET | `/games/entrants/<game_id>` | games | `get_entrants` | AJAX: list entrants for a game |
| GET | `/games/badge-lookup` | games | `badge_lookup` | AJAX: look up attendee by badge number |
| GET | `/games/active-checkout` | games | `active_checkout` | AJAX: get active checkout for a game |
| POST | `/games/checkout` | games | `create_checkout` | AJAX: check out a game |
| POST | `/games/checkin` | games | `checkin` | AJAX: check in a game |
| GET | `/games/checkout-status` | games | `checkout_status` | AJAX: poll shared state for checkout changes (no TTE calls) |
| POST | `/games/p2w-entry` | games | `create_p2w_entry` | AJAX: create P2W entry for a game |
| GET | `/games/p2w-suggestions` | games | `p2w_suggestions` | AJAX: suggest P2W entries after checkout |
| POST | `/games/manual-entry` | games | `add_manual_entry` | AJAX: add manual P2W entry (name + badge) |
| DELETE | `/games/manual-entry/<entry_id>` | games | `remove_manual_entry` | AJAX: remove a manual P2W entry |
| POST | `/games/component-check` | games | `component_check` | AJAX: mark game component check complete |
| POST | `/games/component-uncheck` | games | `component_uncheck` | AJAX: clear game component check |
| POST | `/games/reset-checkout-time` | games | `reset_checkout_time` | AJAX: reset checkout timestamp |
| GET | `/games/notifications` | games | `get_notifications` | AJAX: get notification list |
| POST | `/games/notifications/dismiss` | games | `dismiss_notification` | AJAX: dismiss a notification |
| POST | `/games/settings` | games | `update_settings` | AJAX: update library settings |
| POST | `/games/mark-all-p2w` | games | `mark_all_p2w` | AJAX: mark all games as P2W via TTE API |
| GET/POST | `/volunteer-login` | games | `volunteer_login` | Volunteer login form and authentication |
| POST | `/volunteer-logout` | games | `volunteer_logout` | Volunteer logout (preserves library context) |
| POST | `/drawing` | drawing | `run_drawing_route` | Execute drawing algorithm (redirects to results) |
| GET | `/drawing/results` | drawing | `drawing_results` | Display drawing results from session |
| POST | `/drawing/dismiss-game` | drawing | `dismiss_conflict_game` | AJAX: dismiss a game from conflict resolution |
| POST | `/drawing/resolve` | drawing | `resolve_conflicts` | AJAX: apply conflict resolutions |
| POST | `/drawing/pickup` | drawing_actions | `toggle_pickup` | AJAX: toggle pickup status |
| POST | `/drawing/award-next` | drawing_actions | `award_next` | AJAX: advance to next winner |
| POST | `/drawing/award-to` | drawing_actions | `award_to` | AJAX: award game to a specific entrant |
| GET | `/drawing/entrants/<game_id>` | drawing_actions | `drawing_entrants` | AJAX: list entrants for a game in drawing context |
| POST | `/drawing/not-here` | drawing_actions | `mark_not_here` | AJAX: mark person absent, advance their games |
| POST | `/drawing/redraw-unclaimed` | drawing_actions | `redraw_all_unclaimed` | AJAX: redraw all unclaimed games |
| POST | `/drawing/push` | drawing_actions | `push_to_tte` | AJAX: push wins to TTE API |
| GET | `/drawing/export` | drawing_actions | `export_csv` | Download results as CSV |

### `tte_client.py`

REST client for the tabletop.events API.

**Classes:**

- `TTEAPIError(message, status_code=None)` — base exception for all API errors.
- `TTETimeoutError()` — subclass raised on request timeout (30 s).
- `TTEClient(base_url=None, api_key_id=None)` — the client.

**Key behaviors:**

- **Rate limiting:** `_throttle()` enforces a minimum 1-second gap between requests (TTE's API requirement).
- **Pagination:** `_get_all_pages(path, params)` fetches 100 items per page and loops until `total_pages` is reached.
- **Authentication:** `login()` POSTs to `/session` with the API key and stores the returned session ID and `user_id`. The session ID is passed as a query parameter on all subsequent requests. Each user provides their own API key at login.
- **Error handling:** 401/403 clears the client's session ID and raises. Timeouts raise `TTETimeoutError`. Network errors and bad JSON raise `TTEAPIError`. All errors are logged.

**Available methods:**

| Method | Endpoint | Paginated |
|--------|----------|-----------|
| `login(username, password)` | POST `/session` | No |
| `logout()` | DELETE `/session/{id}` | No |
| `get_user_libraries(user_id)` | GET `/user/{id}/libraries` | Yes |
| `search_conventions(query)` | GET `/convention` | Yes |
| `get_convention(id, include_library)` | GET `/convention/{id}` | No |
| `get_library(library_id)` | GET `/library/{id}` | No |
| `get_library_games(id, play_to_win_only)` | GET `/library/{id}/games` | Yes |
| `get_library_playtowins(id)` | GET `/library/{id}/playtowins` | Yes |
| `get_library_game(game_id)` | GET `/librarygame/{id}` | No |
| `get_library_game_playtowins(game_id)` | GET `/librarygame/{id}/playtowins` | Yes |
| `get_convention_playtowins(id)` | GET `/convention/{id}/playtowins` | Yes |
| `get_playtowin(playtowin_id)` | GET `/playtowin/{id}` | No |
| `update_playtowin(id, data)` | PUT `/playtowin/{id}` | No |
| `delete_playtowin(playtowin_id)` | DELETE `/playtowin/{id}` | No |
| `get_library_checkouts(id, checked_in)` | GET `/library/{id}/checkouts` | Yes |
| `get_library_game_checkouts(game_id, checked_in)` | GET `/librarygame/{id}/checkouts` | Yes |
| `search_checkouts(query)` | GET `/checkout` | Yes |
| `create_checkout(library_id, game_id, ...)` | POST `/checkout` | No |
| `checkin_game(checkout_id)` | PUT `/checkout/{id}` | No |
| `get_checkout(checkout_id)` | GET `/checkout/{id}` | No |
| `delete_checkout(checkout_id)` | DELETE `/checkout/{id}` | No |
| `create_playtowin_entry(library_id, game_id, ...)` | POST `/playtowin` | No |
| `update_library_game(game_id, data)` | PUT `/librarygame/{id}` | No |
| `search_badges(convention_id, query, ...)` | GET `/convention/{id}/badges` | Yes |
| `get_library_privileges(library_id)` | GET `/library/{id}/privileges` | Yes |
| `reset_checkout_time(checkout_id)` | PUT `/checkout/{id}` | No |

### `drawing.py`

Core drawing algorithm. Pure functions operating on data structures (no I/O).

**Functions:**

- `shuffle_entries(game_data, rng)` — randomizes entry order per game. Returns drawing state.
- `get_current_winners(drawing_state)` — extracts `game_id → winner entry` from state.
- `detect_conflicts(drawing_state)` — finds badge IDs that won multiple games.
- `resolve_premium_auto(conflicts, premium_ids)` — auto-resolves when a person won exactly one premium game (they keep the premium game).
- `advance_winner(drawing_state, game_id, not_here)` — moves to the next person in the shuffled list, skipping badge IDs in the `not_here` set.
- `apply_resolution(drawing_state, keep_map)` — applies admin choices, advancing winners on relinquished games.
- `_resolve_conflicts_loop(state, premium_set)` — runs the conflict detection / premium auto-resolution loop. Returns unresolved conflicts and auto-resolved assignments.
- `run_drawing(game_data, premium_ids, rng)` — orchestrates the full algorithm (see Drawing Algorithm below).
- `redraw_unclaimed(drawing_state, unclaimed_game_ids, not_here, original_winners, same_rules, premium_game_ids, rng)` — re-shuffles unclaimed games excluding absent and original-draw winners.

### `data_processing.py`

- `process_entries(entries)` — filters entries without a usable identifier and de-duplicates by `(badge_id, librarygame_id)`. Falls back to `user_id` then `name` when `badge_id` is absent.
- `apply_ejections(entries, ejected_entries)` — removes ejected entries. Supports per-game ejection or wildcard (`"*"`) for all games.
- `group_entries_by_game(entries, games)` — groups entries by game, attaches game metadata. Games with zero entries are included.

### `shared_state.py`

Library-scoped shared state that persists across browser sessions. Stores data that must be visible to all devices working with the same library: ejections, notifications, settings, person cache, play groups. Each library gets a separate JSON file in the `shared_state/` directory.

**Functions:**

- `init_dir()` — creates the shared state directory if it doesn't exist.
- `load(library_id)` — loads the full shared state dict for a library. Returns `{}` if no file exists.
- `save(library_id, state)` — replaces the entire shared state file for a library.
- `update(library_id, key, value)` — atomically sets a single key in the shared state file. Uses `fcntl.flock()` file locking.
- `merge_dict(library_id, key, updates)` — atomically merges a dict into a shared state key. Used for `person_cache` and `play_groups` to prevent concurrent writes from overwriting each other.
- `delete(library_id)` — removes a library's shared state and lock files.

## Cross-Cutting Concerns

### CSRF Protection

All POST routes are protected by Flask-WTF's `CSRFProtect`. Templates include `{{ csrf_token() }}` in forms and AJAX requests include the token via a meta tag in `base.html`. Tests disable CSRF globally via `conftest.py` (`WTF_CSRF_ENABLED = False`).

### Input Validation

Route handlers validate TTE entity IDs (UUID format) and badge IDs (alphanumeric) at the boundary using `is_valid_tte_id()` and `is_valid_badge_id()` from `routes/helpers.py`. Invalid IDs return 400 with a descriptive error.

### Logging

Each route module and `tte_client.py` creates a module-level logger via `logging.getLogger(__name__)`. Key events logged include:

- Login success/failure, logout
- Unauthenticated access attempts and API auth errors
- Library/convention selection and data loading
- Drawing execution stats (games, conflicts, auto-resolved)
- TTE push lifecycle (start, per-failure, completion summary)
- Session cleanup on startup

### Session Scoping

When the user switches libraries or conventions, all library-scoped session keys (cached data, drawing state, ejections, pickups, etc.) are cleared to prevent stale data from the previous library.

## Data Flow

```
Login                          POST /login
  │                              └─ TTEClient.login() → session_id
  ▼
Source Select                  GET /convention
  │                              ├─ Convention tab:
  │                              │    └─ Search: AJAX GET /convention/search
  │                              │         └─ TTEClient.search_conventions()
  │                              └─ Library Only tab:
  │                                   └─ Browse: AJAX GET /library/browse
  │                                        └─ TTEClient.get_user_libraries()
  ▼
Convention Confirm             POST /convention/select
  │                              └─ TTEClient.get_convention(include_library=True)
  │                              └─ Stores convention_id, library_id in session
  ▼
Library Confirm                POST /library/select  (alternative path)
  │                              └─ TTEClient.get_library(library_id)
  │                              └─ Stores library_id, library_name in session
  │                              └─ Clears convention_id, convention_name
  ▼
Games Page                     GET /games (or GET /games?refresh=1)
  │  On first load or refresh:
  │   ├─ [1] TTEClient.get_library_games()        → cached_games
  │   ├─ [2] TTEClient.get_convention_playtowins() → cached_entries
  │   │       (or get_library_playtowins in library-only mode)
  │   ├─ [3] TTEClient.get_library_checkouts(checked_in=False)
  │   │       → enrich games with renter names & checkout IDs
  │   ├─ [4] TTEClient.get_library_checkouts(checked_in=False)
  │   │       → suspicious: long checkout detection
  │   ├─ [5] TTEClient.get_library_checkouts(checked_in=True)
  │   │       → suspicious: partner pattern analysis
  │   └─ process_entries() + apply_ejections() + group_entries_by_game()
  │  On cached load: no API calls, uses session data
  │
  │  Management mode actions (AJAX):
  │   ├─ Badge lookup:        GET  /games/badge-lookup → [1] search_badges()
  │   ├─ Game checkout:       POST /games/checkout     → [1] get_library_game()
  │   │                                                  [2] create_checkout()
  │   ├─ Game checkin:        POST /games/checkin      → [1] checkin_game()
  │   ├─ P2W entry:           POST /games/p2w-entry    → [1] get_library_game_playtowins()
  │   │                                                  [2] create_playtowin_entry()
  │   ├─ Active checkout:     GET  /games/active-checkout → [1] get_library_game_checkouts()
  │   ├─ Reset checkout time: POST /games/reset-checkout-time → [1] reset_checkout_time()
  │   ├─ Mark All P2W:        POST /games/mark-all-p2w → [N] update_library_game() per game
  │   ├─ Settings/premium:    POST /games/settings, /games/premium → session only
  │   └─ Eject/uneject:       POST /games/eject, /games/uneject   → session only
  ▼
Run Drawing                    POST /drawing → 302 → GET /drawing/results
  │                              ├─ Uses cached games + entries from session (no API calls)
  │                              └─ apply_ejections() → run_drawing() → drawing_state
  ▼
Results & Redraw               GET /drawing/results
  │   ├─ Resolve conflicts:   POST /drawing/resolve       → session only
  │   ├─ Track pickups:       POST /drawing/pickup         → session only
  │   ├─ Award next:          POST /drawing/award-next     → session only
  │   ├─ Award to:            POST /drawing/award-to       → session only
  │   ├─ Gone (not here):     POST /drawing/not-here       → session only
  │   ├─ Redraw unclaimed:    POST /drawing/redraw-unclaimed → session only
  │   ├─ Push to TTE:         POST /drawing/push           → [N] update_playtowin()
  │   └─ Export CSV:           GET /drawing/export          → no API calls
```

## Session State Reference

All application state lives in the server-side Flask session (`FileSystemCache`), with a signed cookie referencing the session file.

| Key | Type | Set By | Purpose |
|-----|------|--------|---------|
| `tte_session_id` | `str` | Login | TTE API session ID |
| `tte_username` | `str` | Login | Display username |
| `tte_user_id` | `str` | Login | TTE user ID (for library browsing) |
| `tte_api_key` | `str` | Login | Per-user TTE API key |
| `convention_id` | `str` | Convention select | Selected convention (absent in library-only mode) |
| `convention_name` | `str` | Convention select | Convention display name (absent in library-only mode) |
| `library_id` | `str` | Convention/library select | Associated library ID |
| `library_name` | `str` | Convention/library select | Library display name |
| `app_mode` | `str` | Mode switch | Current UI mode: `"management"`, `"players"`, `"prep"`, or `"drawing"` |
| `prep_completed` | `bool` | Drawing Prep | Whether Drawing Prep has been visited (shows warning on Drawing tab if not) |
| `auth_mode` | `str` | Login / volunteer login | `"owner"` or `"volunteer"` |
| `volunteer_name` | `str` | Volunteer login | Display name for current volunteer |
| `has_checkout_privilege` | `bool` | Volunteer login | Whether volunteer has checkout privilege (cached at login) |
| `cached_games` | `list[dict]` | Games page refresh | Cached game data from TTE |
| `cached_entries` | `list[dict]` | Games page refresh | Cached entry data from TTE |
| `premium_games` | `list[str]` | Premium toggle | Game IDs marked as premium |
| `ejected_entries` | `list[list]` | Eject player | Pairs of `[badge_id, game_id]` (`"*"` = all games) |
| `person_cache` | `dict` | Badge lookup / checkout | `{badge_number: {name, badge_id, user_id}}` |
| `checkout_cache` | `list` | Checkout actions | List of active checkouts |
| `play_groups` | `dict` | P2W entry | `{person_key: [co-entrant keys]}` for partner detection |
| `notifications` | `list[dict]` | Refresh / actions | `[{id, type, message, dismissed, timestamp, details}]` |
| `component_checks` | `dict` | Component check modal | `{game_id: {checked, volunteer, timestamp}}` |
| `library_settings` | `dict` | Settings modal | `{include_non_p2w: bool, checkout_alert_hours: int, ...}` |
| `manual_entry_ids` | `list[str]` | Manual entry | TTE entry IDs created via manual entry (tracked for removal) |
| `drawing_state` | `list[dict]` | Drawing | Full shuffled state with winner indices |
| `drawing_conflicts` | `list[dict]` | Drawing | Unresolved multi-win conflicts |
| `drawing_timestamp` | `str` | Drawing | When the drawing was executed |
| `auto_resolved` | `list[dict]` | Drawing | Auto-resolved premium conflicts |
| `picked_up` | `list[str]` | Pickup toggle | Game IDs marked as picked up |
| `not_here` | `list[str]` | Gone | Badge IDs marked as absent |
| `not_here_warning_dismissed` | `bool` | Gone | Whether the confirmation warning was dismissed |
| `solo_dismissed_games` | `list[str]` | Dismiss conflict | Games dismissed during conflict resolution |

Session is cleared entirely on auth errors (401/403) and on logout. All library-scoped keys (everything below `tte_api_key` in the table above) are cleared when the convention or library source changes.

## Data Architecture: Session vs TTE

Application data falls into three categories based on where it lives and how it's shared:

### TTE-Synced (Authoritative)

These operations write to the TTE API. Changes are visible to all users/devices immediately.

| Data | Write Operation | Read Back |
|------|----------------|-----------|
| Game checkouts | `create_checkout()` | On refresh: `get_library_checkouts()` |
| Game checkins | `checkin_game()` | On refresh: `get_library_checkouts()` |
| P2W entries | `create_playtowin_entry()` | On refresh: `get_convention_playtowins()` |
| P2W win flags | `update_playtowin({win: 1})` | — (push is the final step) |
| Game P2W flag | `update_library_game({is_play_to_win: 1})` | On refresh: `get_library_games()` |
| Checkout timestamps | `reset_checkout_time()` | On refresh: `get_library_checkouts()` |

### Shared State (Library-Scoped)

These values are stored in library-scoped JSON files (via `shared_state.py`) and synced into the session on page loads. Changes made on one device are visible to all devices working with the same library.

| Data | Shared Mechanism |
|------|-----------------|
| `ejected_entries` | `shared_state.update()` — atomic replace |
| `notifications` | `shared_state.update()` — atomic replace |
| `library_settings` | `shared_state.update()` — atomic replace |
| `person_cache` | `shared_state.merge_dict()` — concurrent-safe merge |
| `play_groups` | `shared_state.merge_dict()` — concurrent-safe merge || `checkout_map` | `shared_state.merge_dict()` — concurrent-safe merge |
| `manual_entry_ids` | `shared_state.update()` — atomic replace |
### Session-Only (Per-Browser)

These values exist only in the server-side session for one browser. They are **not shared** between devices or browser tabs with different session cookies.

| Data | Impact If Not Shared |
|------|---------------------|
| `cached_games`, `cached_entries` | Each browser has its own snapshot; stale until manually refreshed |
| `premium_games` | Premium designations set on one device are not visible on another |
| `drawing_state`, `drawing_conflicts` | Drawing results exist only in the session that ran the drawing |
| `picked_up`, `not_here` | Pickup tracking and absent markers are per-session |
| `component_checks` | Component check records are per-session |

### Derived (Computed on Refresh)

Computed from TTE data during a refresh and cached in session:

| Data | Computed From |
|------|--------------|
| Renter names on games | `get_library_checkouts()` → merged into `cached_games` |
| Suspicious flags on games | `check_long_checkouts()` + `check_partner_patterns()` → flags on `cached_games` |
| Non-P2W notifications | Scanned from `cached_games` after refresh |

### Multi-Device Implications

When multiple volunteers use separate devices (each with their own browser session):

- **Consistent across devices:** Checkouts, checkins, P2W entries, and game data — because these are written to TTE and re-fetched on refresh. Also ejections, notifications, settings, person cache, and play groups — because these are stored in library-scoped shared state files and synced on every page load.
- **Not shared across devices:** Premium designations, drawing state, pickup tracking, and component checks. Each device has its own copy.
- **Staleness risk:** The JS polls `checkout-status` every 30 seconds (paused when the tab is hidden), so checkout changes from other devices appear within ~30 seconds. New P2W entries, newly added games, and other game-level changes still require a manual Refresh.
- **Drawing must run on one device:** Only the device that runs the drawing has the results. Pushing to TTE writes win flags, but the pickup tracking and redraw workflow are session-local.

> **Recommendation for operators:** Run the drawing from the library owner's device. Volunteers can use separate devices for checkouts. Premium designations and component checks should be set on each device independently (or use a single shared device for these).

## Rate Limiting

### TTE API Limit

The TTE API enforces a rate limit of **1 request per second**. The `TTEClient._throttle()` method enforces this client-side via `time.sleep()`.

The throttle timestamp is stored in the Flask session (`_tte_last_request`) so it persists across `TTEClient` instances within the same request context. Each browser session has its own throttle — multiple devices do **not** share the rate limit counter.

### API Calls Per Operation

| Operation | API Calls | Trigger | Notes |
|-----------|-----------|---------|-------|
| **Page load / Refresh** | **5** | User clicks Refresh or first visit | Most expensive operation |
|  ↳ Get games | 1+ (paginated) | Automatic | 100 games/page |
|  ↳ Get P2W entries | 1+ (paginated) | Automatic | 100 entries/page |
|  ↳ Get active checkouts (renter enrichment) | 1+ (paginated) | Automatic | |
|  ↳ Get active checkouts (suspicious detection) | 1+ (paginated) | Automatic | Duplicate of above — could be optimized |
|  ↳ Get checkout history (partner patterns) | 1+ (paginated) | Automatic | Can be large for active libraries |
| **Single checkout** | 2 | User action | `get_library_game` (verify) + `create_checkout` |
| **Single checkin** | 1 | User action | `checkin_game` |
| **P2W entry** | 2 | User action | `get_library_game_playtowins` (dup check) + `create_playtowin_entry` |
| **Badge lookup** | 1 | User action | `search_badges` |
| **Active checkout lookup** | 1 | User action | `get_library_game_checkouts` |
| **Reset checkout time** | 1 | User action | `reset_checkout_time` |
| **Mark All P2W** | N | User action | 1 `update_library_game` per non-P2W game |
| **Push wins to TTE** | N | User action | 1 `update_playtowin` per picked-up game |
| **Volunteer login** | 2 | User action | `login` + `get_library_privileges` |
| **Run drawing** | 0 | User action | Uses cached session data only |
| **All redraw actions** | 0 | User action | Session-only operations |
| **Checkout status poll** | 0 | Automatic (30s) | Reads shared state only — no TTE calls; pauses when tab hidden |

### Rate Limit Scenarios

**Refresh with a large library:** A library with 200 games and 500 P2W entries triggers at minimum 5 API calls (possibly more with pagination). At 1 req/sec, this takes ~5 seconds. Very large libraries with extensive checkout histories could take 10–15 seconds.

**Mark All P2W on 50 non-P2W games:** 50 sequential API calls at 1 req/sec = ~50 seconds. The UI should indicate progress.

**Push wins for 30 games:** 30 calls at 1 req/sec = ~30 seconds.

**Multiple volunteers refreshing simultaneously:** Each device has its own rate limiter, so two devices refreshing at the same time make 2× the API calls. The TTE server may enforce a per-API-key or per-IP limit beyond the client-side throttle — this is not documented by TTE.

### Optimization Opportunities

1. **Deduplicate checkout fetches on refresh:** The active checkout list is fetched twice (once for renter enrichment, once for suspicious detection). This could be fetched once and reused.
2. **Batch P2W updates:** Mark All P2W makes N sequential calls. If TTE supports batch updates, this could be a single call.
3. **Lazy suspicious detection:** Partner pattern analysis fetches the full checkout history. This could be deferred to a background task or triggered less frequently.

## Drawing Algorithm

1. **Shuffle:** Each game's entries are randomly shuffled. The first entry in each shuffled list is the initial winner (`winner_index = 0`).

2. **Conflict detection:** Scan all winners for any `badge_id` appearing in multiple games.

3. **Premium auto-resolution:** If a conflicting person won exactly one premium game:
   - They keep the premium game.
   - Their non-premium wins are relinquished (winner index advances).
   - This may cascade — the new winner for a relinquished game might themselves have a conflict.

4. **Manual resolution:** If a person won zero or 2+ premium games, admin must choose which game they keep. The UI presents radio buttons for each conflicting game.

5. **Cascading:** After each resolution round, conflicts are re-detected. The loop (`_resolve_conflicts_loop`) runs up to 100 iterations (safety bound).

6. **Exhaustion:** If `winner_index` exceeds the shuffled list length, the game has no eligible winner.

7. **Redraw unclaimed:** After pickup, unclaimed games can be redrawn. `redraw_unclaimed` re-shuffles entries for unclaimed games, excluding absent badge IDs and original-draw winners.

## TTE API Client Details

- **Base URL:** `https://tabletop.events/api`
- **Auth:** Session-based. Login returns a `session_id` which is sent as a query parameter on all requests. Each user provides their own API key at login; the client falls back to `Config.TTE_API_KEY` if none is provided.
- **Rate limit:** 1 request per second, enforced client-side via `time.sleep()`.
- **Pagination:** 100 items per page. The client loops through `_page_number` until `total_pages` is reached.
- **Timeout:** 30 seconds per request. Raises `TTETimeoutError` on timeout.
- **Error mapping:**
  - 401/403 → session cleared, `TTEAPIError` with status code
  - Other HTTP errors → `TTEAPIError` with status code and truncated body
  - Network errors → `TTEAPIError` with message
  - Invalid JSON → `TTEAPIError`
  - Missing `result` key → `TTEAPIError`

## Testing

### Running tests

```bash
python -m pytest tests/ -v
```

### Test structure

| File | Tests | Covers |
|------|-------|--------|
| `test_routes.py` | 205 | All routes, auth guards, AJAX endpoints, error handling, ID validation, manual entries |
| `test_library_mgmt.py` | 70 | Library management: checkout, checkin, P2W entry, badge lookup, suspicious detection, volunteer login/logout, privilege gates, notifications, settings, component checks |
| `test_drawing.py` | 45 | Shuffle, conflicts, resolution, cascading, redraw, conflict gating |
| `test_tte_client.py` | 22 | Rate limiting, auth, error handling, pagination, endpoints |
| `test_data_processing.py` | 21 | Entry processing, ejection filtering, grouping |

### Test configuration

`tests/conftest.py` monkey-patches `create_app` to disable CSRF (`WTF_CSRF_ENABLED = False`) so tests can POST without tokens.

### Mocking patterns

- **TTEClient in routes:** `@patch("routes.auth.TTEClient")` or `@patch("routes.helpers.TTEClient")` — mock the class where it's imported, configure the instance via `MockClient.return_value`. Used for routes that call the TTE API directly (login, convention/library select).
- **TTEClient from local import:** `@patch("tte_client.TTEClient")` — for routes that import TTEClient inside the function body (e.g., volunteer login/logout), mock at the source module.
- **_get_client in games.py:** `@patch("routes.games._get_client")` — mock the helper that creates TTEClient instances. Used for checkout, checkin, P2W entry, and other game management routes. Configure the mock client's method return values.
- **Cached session data in routes:** Drawing and player routes use cached session data (`cached_games`, `cached_entries`) instead of API calls. Tests populate these keys via `session_transaction()` rather than mocking TTEClient.
- **requests in tte_client:** `@patch("tte_client.requests.Session.send", ...)` or `@patch("tte_client.requests.request")` — mock the raw HTTP call, return a `MagicMock` response with `.status_code`, `.ok`, `.json()`, `.text`.
- **Session setup:** Use `self.client.session_transaction()` context manager to pre-populate Flask session keys before making requests.
- **Drawing randomness:** Pass a seeded `random.Random` instance to `run_drawing()` / `shuffle_entries()` for deterministic tests.

## Local Development Setup

### Prerequisites

- Python 3.12+
- A tabletop.events account with an API key

### Setup

```bash
# Clone the repository
git clone git@github.com:jeep/PawDrawing.git
cd PawDrawing

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env — set FLASK_SECRET_KEY (required) and optionally TTE_API_KEY

# Configure git hooks
git config core.hooksPath .githooks

# Run the development server
python run.py
```

The app will be available at `http://127.0.0.1:5000`.

### Running tests

```bash
source venv/bin/activate
python -m pytest tests/ -v
```

## Git Conventions

### Commit message format

Enforced by `.githooks/commit-msg`. Format:

```
<type>[optional scope]: <description> (#<issue>)
```

- **Max subject length:** 72 characters
- **Issue number required:** `(#N)` at end of subject line
- **Merge commits** are allowed without the format check

**Allowed types:** `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, `revert`

**Examples:**

```
feat: add login page (#3)
fix(api): handle rate limit errors (#5)
docs: update README with setup steps (#1)
```

### Branch strategy

All work is done on `main`. Each commit references a GitHub issue number.

## Deployment

### Azure App Service

The app is deployed to **Azure App Service** (Linux, Python 3.12, F1 free tier):

> https://pawdrawing.azurewebsites.net

### CI/CD Pipeline

The GitHub Actions workflow (`.github/workflows/deploy.yml`) runs on every push to `main`:

1. **Test job:** Checks out code, installs dependencies, runs `python -m pytest`.
2. **Deploy job:** (only if tests pass) Logs into Azure via service principal (`azure/login@v2`) and deploys with `az webapp up`.

The workflow can also be triggered manually via `workflow_dispatch`.

### Azure Configuration

Environment variables are set as **Azure App Settings** (not committed to source):

| Setting | Purpose |
|---------|--------|
| `FLASK_SECRET_KEY` | Session cookie signing key |
| `SESSION_FILE_DIR` | `/home/flask_session` — persists across deploys |

The startup command is defined in `startup.sh`:

```bash
gunicorn --bind=0.0.0.0:8000 --timeout=120 --workers=2 run:app
```

### GitHub Secrets

| Secret/Variable | Purpose |
|-----------------|--------|
| `AZURE_CREDENTIALS` | Service principal JSON for `azure/login@v2` |
| `AZURE_WEBAPP_NAME` (variable) | App Service name (used in `az webapp up`) |
