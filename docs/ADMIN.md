# Administrator Guide

## Overview

PawDrawing runs Play-to-Win prize drawings at tabletop gaming conventions. It connects to [tabletop.events](https://tabletop.events) to pull convention data, runs a randomized drawing, and pushes the winning entries back.

This guide covers installation, configuration, the operational workflow for running a drawing, and troubleshooting.

## Installation

### System requirements

- Python 3.12 or later
- Network access to `https://tabletop.events/api`
- A tabletop.events account with an API key

### Install from source

```bash
git clone git@github.com:jeep/PawDrawing.git
cd PawDrawing
python3 -m venv venv
source venv/bin/activate
pip install -r Requirements.txt
```

### Development server

```bash
cp .env.example .env
# Edit .env — see Configuration below
python run.py
```

The app runs at `http://127.0.0.1:5000`.

### Production deployment

For production, use a WSGI server instead of the built-in Flask development server:

```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:8000 "app:create_app()"
```

Place behind a reverse proxy (nginx, Caddy, etc.) that terminates TLS. Do **not** expose the Flask dev server to the internet.

## Configuration

All configuration is done through environment variables. Copy `.env.example` to `.env` and fill in the values.

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `FLASK_SECRET_KEY` | **Yes** | `dev-key-change-me` | Signs session cookies. Must be a long random string in production. |
| `TTE_API_KEY` | **Yes** | *(empty)* | Your tabletop.events API key. Obtain from your TTE account settings. |

The TTE API base URL is hardcoded to `https://tabletop.events/api` and is not configurable via environment variables.

### Generating a secret key

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Copy the output into your `.env` file as `FLASK_SECRET_KEY`.

## Operational Workflow

This is the step-by-step process for running a Play-to-Win drawing at a convention.

### 1. Log in

Navigate to the app and log in with your tabletop.events credentials. The app creates a session with the TTE API using your credentials and the configured API key.

### 2. Select a source

The source selection page has two tabs:

**Convention tab** (default): Search for your convention by name, or paste the convention ID directly. The app fetches the convention details and its associated game library. Play-to-Win entries are scoped to the convention.

**Library Only tab**: If you want to draw from a library without a convention (or the library exists independently), switch to the "Library Only" tab. You can browse your libraries (libraries associated with your TTE account) or paste a library ID directly. In library-only mode, all Play-to-Win entries in the library are included regardless of convention.

### 3. Review games

The games page shows all Play-to-Win games in the selected source (convention library or standalone library), along with the number of entries (people who played) for each game.

### 4. Eject players (optional)

If a player needs to be excluded from the drawing (e.g., rule violation), click the **View Entrants** button for a game, then click **Eject** next to the player. You can eject a player from a single game or from all games.

Ejected players are excluded when the drawing is run. Ejections can be undone at any time before running the drawing.

Ejections are cleared when you change the convention or library source.

### 5. Designate premium games

Toggle the "Premium" checkbox on any games that are premium prizes. Premium games get special treatment during conflict resolution — if a person wins one premium game and one or more non-premium games, they automatically keep the premium game.

Premium designations are auto-saved as you toggle them.

### 6. Run the drawing

Click **Run Drawing**. The app:

1. Re-fetches current game and entry data from TTE (to capture any last-minute entries).
2. Randomly shuffles all entries for each game.
3. Selects the first person in each shuffled list as the initial winner.
4. Detects conflicts (one person winning multiple games).
5. Auto-resolves premium conflicts where possible.

### 7. Resolve conflicts

If any conflicts remain after auto-resolution, you'll see conflict panels at the top of the results page. For each conflicting person, select which game they should keep. Click **Resolve** to apply.

Resolution may cascade — new conflicts can appear when an alternate winner is selected. Repeat until all conflicts are resolved.

### 8. Track pickups

As winners come to claim their prizes, click **Mark Picked Up** next to each game. The button turns green. Click again to undo if needed. The pickup counter in the summary bar updates in real time.

If a winner is absent, you can click **Not Here** to mark them. This advances all their unpicked-up games to the next person in the shuffled list, and prevents them from being selected again in any future advances.

### 9. Redraw unclaimed games

After the claiming period, click **Redraw Unclaimed** to run a fresh drawing for all games that have not been picked up. The redraw:

- Re-shuffles entries for each unclaimed game.
- Excludes anyone marked as "Not Here."
- Excludes anyone who won in the original drawing (regardless of whether they picked up).

The one-win-per-person rule does **not** apply during the redraw — a person who already picked up another game may win an unclaimed game.

New winners appear in the results. Mark them as picked up as they claim their prizes.

### 10. Push results to TTE

Click **Push to TTE** to write the win flags back to tabletop.events. Only picked-up games are pushed. The app shows a confirmation dialog with the count, then pushes each winner individually.

Results:
- **Success**: All games updated.
- **Partial success**: Some failed — review the error list and retry.
- **Network error**: Check connectivity and try again.

### 11. Export CSV

Click **Export CSV** to download a spreadsheet of the results. The CSV includes:

| Column | Description |
|--------|-------------|
| Game | Game name |
| Premium | Yes/No |
| Entries | Number of people who entered |
| Winner | Winner's name |
| Badge | Winner's badge ID |
| Picked Up | Yes/No |

The filename follows the pattern `PawDrawing_ConventionName_2026-03-21.csv`.

## Security Considerations

### Session management

- All application state (drawing data, login session) is stored in Flask's signed cookie-based sessions.
- Sessions are signed with `FLASK_SECRET_KEY`. Anyone with this key can forge sessions.
- If the TTE API returns 401 or 403, the entire Flask session is cleared and the user must log in again.

### Secret key

- **Never** use the default `dev-key-change-me` in production.
- Rotate the key by changing `FLASK_SECRET_KEY` and restarting the app. All active sessions will be invalidated.
- Store the key securely — do not commit `.env` to version control.

### API key

- The TTE API key is loaded from the `TTE_API_KEY` environment variable.
- It's sent to the TTE API during login only (not on every request — the session ID is used instead).
- Keep the API key confidential. If compromised, regenerate it in your TTE account settings.

### HTTPS

- Always deploy behind a reverse proxy with TLS termination.
- Session cookies should be transmitted over HTTPS only in production.
- The TTE API endpoint uses HTTPS by default.

### Credentials

- User passwords are sent to the TTE API for authentication and are not stored locally.
- The TTE session ID is stored in the Flask session cookie (signed, not encrypted).

## Troubleshooting

### Common error messages

| Message | Cause | Resolution |
|---------|-------|------------|
| **Session expired — please log in again.** | TTE API returned 401 or 403. The session timed out or was invalidated. | Log in again. TTE sessions expire after a period of inactivity. |
| **Request timed out. The server may be busy — please try again.** | A TTE API request took longer than 30 seconds. | Retry the action. If persistent, check your network or TTE server status. |
| **Could not load games / entries** | API error when fetching game or entry data. | Check that the convention ID is correct and the convention has a library with P2W games. Retry. |
| **No library found for this convention.** | The selected convention doesn't have an associated game library. | Verify you selected the correct convention. The convention must have a library configured in TTE. |
| **Could not load your libraries** | API error when browsing user's libraries. | Check your network connection and try again. If the issue persists, paste the library ID directly instead of browsing. |
| **Network error** | No network connectivity or DNS resolution failure. | Check your internet connection and that `tabletop.events` is reachable. |
| **Login failed** | Invalid username, password, or API key. | Verify credentials. Check that `TTE_API_KEY` in `.env` is correct. |
| **No games marked as picked up** (Push to TTE) | Attempted to push with no games in the picked-up list. | Mark at least one game as picked up before pushing. |
| **Search failed — please try again** | Convention search returned an error. | Verify your network connection and try again. |

### AJAX errors

AJAX actions (pickup toggle, conflict resolution, redistribution, push) show inline error feedback:

- **"Error — Retry"** on pickup buttons: network failure. Click again to retry.
- **"Network error — try again"** on redistribution: the claim/decline request failed. Try again.
- **"Network error — please try again"** on push: the push request failed entirely. Try again.

### Partial push failures

If some games fail to push while others succeed, the push result panel shows which games failed with their error messages. You can click **Push to TTE** again — successfully pushed games will be re-pushed (idempotent), and failed ones will be retried.

## Backup and Recovery

### Session state

All application state lives in the browser's session cookie. There is no server-side database.

**Implications:**
- Closing the browser tab preserves the session (cookies persist until expiration).
- Clearing browser cookies or cookies expiring will lose all drawing state.
- Each browser/device has its own independent session.

### Re-running a drawing

Clicking **Re-run Drawing** discards the current drawing state and starts fresh. This:
- Re-fetches all games and entries from TTE.
- Performs a new random shuffle.
- Resets pickup tracking, redraw state, and conflict resolution.

**Warning:** Re-running is irreversible. If you've already done significant pickup tracking or redistribution, you'll lose that progress.

### What happens on page refresh

- **Login, convention select, games pages:** Safe to refresh. These re-render from session data or re-fetch from TTE.
- **Drawing results page:** Safe to refresh. The results are stored in session and rendered via a GET request.
- **Redistribution page:** Safe to refresh. Current redistribution state (claims, declines) is preserved in the session.

### Data safety

- Drawing results are not pushed to TTE until you explicitly click **Push to TTE**.
- The Export CSV button allows you to save a local copy of results at any time.
- It's good practice to **export CSV before pushing** as a record of the drawing.
