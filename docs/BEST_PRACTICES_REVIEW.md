# Best Practices Review

**Date:** 2026-03-23  
**Scope:** Full codebase review of PawDrawing

---

## Security Issues

### 1. No CSRF Protection

**Severity:** High  
**Files:** `routes.py`

All `POST` routes that accept JSON (`/games/eject`, `/drawing/resolve`, `/drawing/pickup`, `/drawing/dismiss-game`, etc.) have no CSRF protection. A malicious site could craft requests on behalf of an authenticated user.

**Recommendation:** Add CSRF protection via Flask-WTF or a custom token. At minimum, verify the `X-Requested-With: XMLHttpRequest` header on AJAX endpoints. The proper fix is generating a CSRF token in templates and validating it server-side on every state-changing request.

---

### 2. `SECRET_KEY` Falls Back to Insecure Default

**Severity:** High  
**File:** `config.py`, line 12

```python
SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "dev-key-change-me")
```

If the environment variable is missing in production, the app silently starts with a weak, publicly-known secret key. This allows session forgery.

**Recommendation:** Fail loudly when the key is absent:

```python
SECRET_KEY = os.environ.get("FLASK_SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("FLASK_SECRET_KEY environment variable is required")
```

---

### 3. Debug Mode Hardcoded in `run.py`

**Severity:** High  
**File:** `run.py`, line 5

```python
app.run(debug=True)
```

Anyone running `python run.py` gets the Werkzeug interactive debugger, which can execute arbitrary Python code and exposes stack traces with local variables.

**Recommendation:**

```python
app.run(debug=os.environ.get("FLASK_DEBUG", "0") == "1")
```

---

### 4. API Key Stored in Plaintext File

**Severity:** High  
**File:** `Application API Key.txt`

The TTE API key is stored in a plaintext file in the project root. While `.gitignore` prevents it from being committed, it's still at risk from accidental copies, backups, file shares, or someone browsing the directory.

**Recommendation:** Delete `Application API Key.txt` entirely. The key already exists in `.env`, which is the correct place for secrets. Use a password manager or secure notes for backup copies.

---

### 5. No Input Validation on IDs

**Severity:** Medium  
**Files:** `routes.py`, `tte_client.py`

User-submitted values like `convention_id`, `library_id`, and `game_id` are taken directly from form data or JSON and interpolated into API URL paths (`f"/convention/{convention_id}"`). While `requests` handles URL encoding, there is no validation that these conform to an expected format.

**Recommendation:** Validate that IDs match an expected pattern (e.g., UUID, alphanumeric, or numeric) before using them:

```python
import re
if not re.match(r'^[A-Za-z0-9_-]+$', convention_id):
    flash("Invalid convention ID.", "error")
    return redirect(url_for("main.convention_select"))
```

---

## Architecture & Code Organization

### 6. `routes.py` Is a 1,117-Line Monolith

**Severity:** Medium  
**File:** `routes.py`

All route handlers, helper functions, and conflict-resolution logic live in a single file. This makes navigation difficult and increases merge conflict risk.

**Recommendation:** Split into focused Blueprint modules:

- `routes/auth.py` — login, logout, index
- `routes/convention.py` — convention/library search and selection
- `routes/games.py` — game loading, player management, ejections
- `routes/drawing.py` — drawing execution, results, resolution, export

---

### 7. No Authentication Decorator — Repeated Inline Checks

**Severity:** Medium  
**File:** `routes.py`

Every route manually checks `session.get("tte_session_id")` and handles the unauthenticated case with either a redirect or a 401 JSON response. This is repeated ~20 times. A missed check on any new route creates an auth bypass.

**Recommendation:** Create a `@login_required` decorator:

```python
from functools import wraps

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("tte_session_id"):
            if request.is_json:
                return jsonify({"error": "Not authenticated"}), 401
            flash("Please log in first.", "error")
            return redirect(url_for("main.login"))
        return f(*args, **kwargs)
    return decorated
```

---

### 8. Duplicated Conflict-Building Logic

**Severity:** Medium  
**Files:** `routes.py` (in `resolve_conflicts()`, `dismiss_conflict_game()`, `redraw_all_unclaimed()`), `drawing.py` (in `_resolve_conflicts_loop()`)

The code to construct conflict info dicts — assembling `badge_id`, `winner_name`, `game_ids`, `game_names`, `is_premium_conflict` — is repeated nearly identically in four places.

**Recommendation:** Extract a shared helper:

```python
def build_conflict_info(drawing_state, conflicts_dict, premium_games):
    """Build display-friendly conflict dicts from raw conflict data."""
    winners = get_current_winners(drawing_state)
    game_name_map = {
        item["game"]["id"]: item["game"].get("name", "Unknown")
        for item in drawing_state
    }
    result = []
    for badge_id, game_ids in conflicts_dict.items():
        premium_wins = [gid for gid in game_ids if gid in premium_games]
        winner_name = "Unknown"
        for gid in game_ids:
            w = winners.get(gid)
            if w and w.get("name"):
                winner_name = w["name"]
                break
        result.append({
            "badge_id": badge_id,
            "winner_name": winner_name,
            "game_ids": game_ids,
            "game_names": {gid: game_name_map.get(gid, "Unknown") for gid in game_ids},
            "is_premium_conflict": len(premium_wins) > 1,
        })
    return result
```

---

### 9. `TTEClient` Creates New Connections Per Request

**Severity:** Low  
**File:** `tte_client.py`

Each call to `_get_client()` in `routes.py` creates a new `TTEClient`, which calls `requests.request()` directly. This means no HTTP connection reuse (no keep-alive).

**Recommendation:** Use `requests.Session()` inside `TTEClient` to enable connection pooling:

```python
def __init__(self, ...):
    ...
    self._http = requests.Session()

def _request(self, method, path, ...):
    ...
    resp = self._http.request(method, url, ...)
```

---

## Correctness & Robustness

### 10. Rate Limiter Is Per-Instance, Not Per-User

**Severity:** Medium  
**File:** `tte_client.py`, lines 44–49

`_last_request_time` is an instance variable on `TTEClient`, but a new client is created for each HTTP request. The 1-second throttle therefore never carries over between requests.

**Recommendation:** Store the last request timestamp in the Flask session, or use a shared store (e.g., file lock, Redis, or an in-memory global keyed by user). Example with session:

```python
def _throttle(self):
    last = session.get("_tte_last_request", 0.0)
    elapsed = time.monotonic() - last
    if elapsed < 1.0:
        time.sleep(1.0 - elapsed)
    session["_tte_last_request"] = time.monotonic()
```

Note: `time.monotonic()` values aren't meaningful across processes. For multi-worker setups, use wall-clock time or a shared store.

---

### 11. `logout()` Silently Swallows Errors

**Severity:** Low  
**File:** `tte_client.py`, lines 139–148

```python
def logout(self):
    if not self.session_id:
        return
    try:
        self._request("DELETE", f"/session/{self.session_id}")
    except TTEAPIError:
        pass  # Best-effort logout
```

While best-effort logout is reasonable, the error is completely invisible. If TTE API issues arise, there's no way to tell from logs.

**Recommendation:** Add logging:

```python
except TTEAPIError as exc:
    logger.warning("Logout failed for session %s: %s", self.session_id, exc)
```

---

### 12. Large Data Stored in Sessions with No Cleanup

**Severity:** Medium  
**Files:** `config.py`, `routes.py`

The session stores `cached_games`, `cached_entries`, and `drawing_state` — potentially hundreds of game objects with all their entries. Combined with `threshold=0` (unlimited cache entries in `FileSystemCache`), old session files never get garbage collected. The `flask_session/` directory already contains thousands of files.

**Recommendation:**
- Set a reasonable `threshold` (e.g., 500) or configure `SESSION_PERMANENT = False` with a short lifetime.
- Add a cleanup script or cron job to purge old session files.
- For production, consider a TTL-based store like Redis.

---

## Configuration & Deployment

### 13. No `.env.example` File

**Severity:** Low

New developers have no way to know which environment variables are required without reading `config.py` and `routes.py`.

**Recommendation:** Create `.env.example`:

```
FLASK_SECRET_KEY=generate-a-random-64-char-hex-string
TTE_API_KEY=your-api-key-here
FLASK_DEBUG=0
SESSION_FILE_DIR=flask_session
```

---

### 14. `gunicorn --workers=2` with File-Based Sessions

**Severity:** Low  
**File:** `startup.sh`

Multiple gunicorn workers with file-backed sessions works — but only because `FileSystemCache` handles concurrent access. If sessions are ever changed to in-memory storage, this would silently break.

**Recommendation:** Document this dependency in a comment in `startup.sh` or `config.py`.

---

## Code Quality

### 15. Inconsistent Error Response Patterns

**Severity:** Low  
**File:** `routes.py`

HTML routes use `flash()` + `redirect()`. JSON/AJAX routes return `jsonify({"error": ...})`. The `_handle_api_error()` helper only covers the HTML case. There's no equivalent for JSON routes, leading to repeated inline error handling.

**Recommendation:** Add a parallel helper for JSON API errors, or unify with a single helper that detects the expected response type.

---

### 16. Magic Strings for Session Keys

**Severity:** Low  
**File:** `routes.py`

Session keys like `"tte_session_id"`, `"drawing_state"`, `"premium_games"`, `"ejected_entries"`, `"cached_games"`, etc. appear as raw strings in dozens of places. A typo in any one would cause a subtle bug.

**Recommendation:** Define constants:

```python
class SK:
    TTE_SESSION_ID = "tte_session_id"
    DRAWING_STATE = "drawing_state"
    PREMIUM_GAMES = "premium_games"
    EJECTED_ENTRIES = "ejected_entries"
    CACHED_GAMES = "cached_games"
    CACHED_ENTRIES = "cached_entries"
    PICKED_UP = "picked_up"
    NOT_HERE = "not_here"
    # ...
```

---

### 17. No Application Logging

**Severity:** Medium  
**Files:** All Python files

The application has zero `logging` calls. API errors, authentication failures, drawing executions, TTE push operations, and session expirations are all invisible in production unless the user happens to see the flash message.

**Recommendation:** Add structured logging:

```python
import logging
logger = logging.getLogger(__name__)

# In routes:
logger.info("Drawing executed for library %s — %d games, %d conflicts",
            library_id, len(game_data), len(conflicts))
logger.warning("TTE push failed for game %s: %s", game_id, exc)
logger.error("Session expired during API call for user %s", session.get("tte_username"))
```

---

### 18. Templates Embed Large CSS/JS Inline

**Severity:** Low  
**Files:** `templates/drawing_results.html` (1,337 lines), `templates/games.html` (668 lines)

Styles and JavaScript are embedded directly in template files. This prevents browser caching, makes the templates harder to maintain, and mixes presentation with structure.

**Recommendation:** Extract into static files:

- `static/css/drawing.css`
- `static/js/drawing.js`
- `static/css/games.css`
- `static/js/games.js`

---

## Strengths

These aspects of the codebase are done well:

- **Test coverage:** 3,000+ lines of tests covering routes, drawing logic, data processing, and the TTE client. Tests use seeded RNG for reproducibility.
- **Clean domain separation:** `tte_client.py`, `data_processing.py`, and `drawing.py` are well-focused modules with clear responsibilities.
- **PRG pattern:** Form submissions redirect to GET endpoints, preventing double-submit issues.
- **Error handling on API calls:** Consistent try/except around TTE API calls with user-friendly flash messages.
- **`.gitignore` coverage:** Secrets (`.env`, API key file), IDE files, virtual environments, and session data are all excluded from version control.
- **Rate limiting design:** The TTE client has rate limiting built in (even though the per-instance issue means it doesn't persist across requests).
- **Algorithm correctness:** The drawing algorithm handles edge cases (zero entries, exhausted lists, cascading conflicts, not-here players) with iterative resolution and safety bounds.

---

## Summary

| # | Issue | Severity | Effort |
|---|-------|----------|--------|
| 1 | No CSRF protection | High | Medium |
| 2 | Insecure `SECRET_KEY` fallback | High | Low |
| 3 | Debug mode hardcoded | High | Low |
| 4 | API key in plaintext file | High | Low |
| 5 | No input validation on IDs | Medium | Low |
| 6 | `routes.py` monolith | Medium | Medium |
| 7 | No `@login_required` decorator | Medium | Low |
| 8 | Duplicated conflict-building logic | Medium | Low |
| 9 | No HTTP connection reuse | Low | Low |
| 10 | Rate limiter per-instance | Medium | Low |
| 11 | `logout()` swallows errors | Low | Low |
| 12 | Session data bloat / no cleanup | Medium | Medium |
| 13 | No `.env.example` | Low | Low |
| 14 | Multi-worker session caveat | Low | Low |
| 15 | Inconsistent error patterns | Low | Medium |
| 16 | Magic session key strings | Low | Low |
| 17 | No application logging | Medium | Medium |
| 18 | Inline CSS/JS in templates | Low | Medium |
