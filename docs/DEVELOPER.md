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
├── populate_library.py     # Test data generator for TTE libraries
├── requirements.txt        # pip dependencies
├── .env.example            # Template for environment variables
├── startup.sh              # Azure App Service startup command
├── routes/
│   ├── __init__.py             # Blueprint definition & module imports
│   ├── helpers.py              # Shared utilities (auth, client, error handler, validators)
│   ├── auth.py                 # Login, logout, health check, index redirect
│   ├── convention.py           # Convention search & library selection
│   ├── drawing.py              # Drawing execution, results, conflict resolution
│   ├── drawing_actions.py      # AJAX: pickup, award-next, not-here, redraw, push, export
│   └── games.py                # Game list, premium toggles, eject/uneject, entrants
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
│   ├── convention_select.html  # Convention search & library browse
│   ├── convention_confirm.html # Confirm selected convention
│   ├── library_confirm.html    # Confirm selected library (no convention)
│   ├── games.html              # Game list with premium toggles, sorting & search
│   ├── players.html            # Player management with remove/restore controls
│   └── drawing_results.html    # Results with conflicts, pickup, push, export
├── tests/
│   ├── conftest.py             # Disables CSRF for test client
│   ├── test_routes.py          # Route/view tests
│   ├── test_tte_client.py      # API client tests
│   ├── test_drawing.py         # Drawing algorithm tests
│   └── test_data_processing.py # Data processing tests
├── .githooks/
│   └── commit-msg          # Conventional Commits hook
├── .github/
│   └── workflows/
│       └── deploy.yml      # CI/CD: test + deploy to Azure App Service
└── docs/
    ├── DEVELOPER.md        # This file
    ├── USER_GUIDE.md       # User guide
    └── Requirements.md     # Project requirements document
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
| `PERMANENT_SESSION_LIFETIME` | — | `8 hours` | Session expiry |

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
| `drawing_actions.py` | Pickup toggle, award-next, not-here, redraw unclaimed, push to TTE, CSV export |
| `games.py` | Game list, player management, premium toggles, eject/uneject, entrant list |

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
| GET | `/games` | games | `games` | Load and display P2W games |
| GET | `/games/players` | games | `players` | Player management (list, remove, restore) |
| POST | `/games/premium` | games | `set_premium_games` | AJAX: save premium designations |
| POST | `/games/eject` | games | `eject_player` | AJAX: eject player from drawing |
| POST | `/games/uneject` | games | `uneject_player` | AJAX: undo an ejection |
| GET | `/games/entrants/<game_id>` | games | `get_entrants` | AJAX: list entrants for a game |
| POST | `/drawing` | drawing | `run_drawing_route` | Execute drawing algorithm (redirects to results) |
| GET | `/drawing/results` | drawing | `drawing_results` | Display drawing results from session |
| POST | `/drawing/dismiss-game` | drawing | `dismiss_conflict_game` | AJAX: dismiss a game from conflict resolution |
| POST | `/drawing/resolve` | drawing | `resolve_conflicts` | AJAX: apply conflict resolutions |
| POST | `/drawing/pickup` | drawing_actions | `toggle_pickup` | AJAX: toggle pickup status |
| POST | `/drawing/award-next` | drawing_actions | `award_next` | AJAX: advance to next winner |
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
Games Page                     GET /games
  │                              ├─ TTEClient.get_library_games()
  │                              ├─ Convention mode:
  │                              │    └─ TTEClient.get_convention_playtowins()
  │                              ├─ Library-only mode:
  │                              │    └─ TTEClient.get_library_game_playtowins() per game
  │                              └─ process_entries() + apply_ejections() + group_entries_by_game()
  │                              └─ Caches all_games and entries in session for reuse
  │                              └─ Sortable columns & search/filter bar
  │                              └─ Premium toggles: AJAX POST /games/premium
  │                              └─ Manage Players: GET /games/players
  │                              └─ Remove player: AJAX POST /games/eject
  │                              └─ Restore player: AJAX POST /games/uneject
  │                              └─ View entrants: AJAX GET /games/entrants/<game_id>
  ▼
Run Drawing                    POST /drawing → 302 → GET /drawing/results
  │                              ├─ Uses cached games + entries from session (no API calls)
  │                              └─ apply_ejections() → run_drawing() → drawing_state, conflicts, auto_resolved
  │                              └─ Stores drawing_state in session, redirects (PRG pattern)
  ▼
Resolve Conflicts              AJAX POST /drawing/resolve
  │                              └─ apply_resolution() → detect_conflicts() (cascading)
  ▼
Track Pickups                  AJAX POST /drawing/pickup
  │                              └─ Toggles game_id in session["picked_up"]
  ▼
Award to Next / Not Here       AJAX POST /drawing/award-next
  │                              AJAX POST /drawing/not-here
  │                              └─ Advances winner_index, skips not_here badges
  ▼
Redraw Unclaimed               AJAX POST /drawing/redraw-unclaimed
  │                              └─ Reshuffles unclaimed games excluding not_here & original winners
  ▼
Push to TTE                    AJAX POST /drawing/push
  │                              └─ TTEClient.update_playtowin(id, {win: 1})
  ▼
Export CSV                     GET /drawing/export
                                 └─ Downloads CSV with results
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
| `cached_games` | `list[dict]` | Games page | Cached game data from TTE (cleared on source change) |
| `cached_entries` | `list[dict]` | Games page | Cached entry data from TTE (cleared on source change) |
| `premium_games` | `list[str]` | Premium toggle | Game IDs marked as premium |
| `ejected_entries` | `list[list]` | Eject player | Pairs of `[badge_id, game_id]` (`"*"` = all games) |
| `drawing_state` | `list[dict]` | Drawing | Full shuffled state with winner indices |
| `drawing_conflicts` | `list[dict]` | Drawing | Unresolved multi-win conflicts |
| `drawing_timestamp` | `str` | Drawing | When the drawing was executed |
| `auto_resolved` | `list[dict]` | Drawing | Auto-resolved premium conflicts |
| `picked_up` | `list[str]` | Pickup toggle | Game IDs marked as picked up |
| `not_here` | `list[str]` | Not Here | Badge IDs marked as absent |
| `not_here_warning_dismissed` | `bool` | Not Here | Whether the confirmation warning was dismissed |
| `solo_dismissed_games` | `list[str]` | Dismiss conflict | Games dismissed during conflict resolution |

Session is cleared entirely on auth errors (401/403) and on logout. All library-scoped keys (everything below `tte_api_key` in the table above) are cleared when the convention or library source changes.

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
| `test_routes.py` | 191 | All routes, auth guards, AJAX endpoints, error handling, ID validation |
| `test_drawing.py` | 40 | Shuffle, conflicts, resolution, cascading, redraw |
| `test_tte_client.py` | 22 | Rate limiting, auth, error handling, pagination, endpoints |
| `test_data_processing.py` | 21 | Entry processing, ejection filtering, grouping |

### Test configuration

`tests/conftest.py` monkey-patches `create_app` to disable CSRF (`WTF_CSRF_ENABLED = False`) so tests can POST without tokens.

### Mocking patterns

- **TTEClient in routes:** `@patch("routes.auth.TTEClient")` or `@patch("routes.helpers.TTEClient")` — mock the class where it's imported, configure the instance via `MockClient.return_value`. Used for routes that call the TTE API directly (games, login, convention/library select).
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
