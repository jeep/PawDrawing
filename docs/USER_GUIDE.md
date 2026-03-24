# User Guide

## Overview

PawDrawing runs Play-to-Win prize drawings at tabletop gaming conventions. It connects to [tabletop.events](https://tabletop.events) to pull convention data, runs a randomized drawing, and pushes the winning entries back.

The app is available at:

> https://pawdrawing.azurewebsites.net

## Workflow

### 1. Log in

Navigate to the app and log in with your tabletop.events username (or email
address), password, and API key. Each user must provide their own API key from
their TTE account.

**To get your API key:** Log in to [tabletop.events](https://tabletop.events),
click your username in the upper-right corner, then click **API Keys**. If you
already have a key, you can use it. Otherwise, click **Create**, fill in a name
(and optionally a URL and reason), and copy the generated key to enter into
PawDrawing.

### 2. Select a source

The source selection page has two tabs:

**Convention tab** (default): Search for your convention by name, or paste the convention ID directly. The app fetches the convention details and its associated game library. Play-to-Win entries are scoped to the convention.

**Library Only tab**: If you want to draw from a library without a convention (or the library exists independently), switch to the "Library Only" tab. You can browse your libraries or paste a library ID directly. In library-only mode, all Play-to-Win entries in the library are included regardless of convention.

### 3. Review games

The games page shows all Play-to-Win games in the selected source, along with the number of entries (people who played) for each game.

The game list supports **sortable columns** (click headers to sort by game name, entries, etc.) and a **search bar** to filter games by name.

Large conventions with many games and entries may take a minute or two to load.

### 4. Manage players (optional)

Click **Manage Players** on the games page to open the player management screen. This page lists every player who entered a Play-to-Win game, along with their badge ID, the number of games they entered, and which games.

To exclude a player from the drawing, click **Remove from Drawing** next to their name. To exclude them from a single game, expand their row and click **Remove from Game** on the specific game.

Removed players are shown with a "Removed" badge and can be restored at any time before running the drawing. Removals are cleared when you change the convention or library source.

### 5. Designate premium games

Toggle the "Premium" checkbox on any games that are premium prizes. Premium games get special treatment during conflict resolution — if a person wins one premium game and one or more non-premium games, they automatically keep the premium game.

Premium designations are auto-saved as you toggle them.

### 6. Run the drawing

Click **Run Drawing**. The app:

1. Randomly shuffles all entries for each game.
2. Selects the first person in each shuffled list as the initial winner.
3. Detects conflicts (one person winning multiple games).
4. Auto-resolves premium conflicts where possible.

To pick up the latest data from TTE before drawing, click **Refresh Data** on the games page first.

### 7. Resolve conflicts

If any conflicts remain after auto-resolution, you'll see conflict panels at the top of the results page. For each conflicting person, select which game they should keep, or click **🎲 Random** to choose randomly.

You can also click the **dismiss (✕)** button on a specific game to remove that person from it and advance to the next candidate. If there are no more candidates, the game is marked **"No winner (redraw eligible)"** — it remains available in the redraw rather than being sent to the box.

Resolution may cascade — new conflicts can appear when an alternate winner is selected. Repeat until all conflicts are resolved.

### 8. Track pickups

As winners come to claim their prizes, click **Mark Picked Up** next to each game. The button turns green. Click again to undo if needed. The pickup counter in the summary bar updates in real time.

The results page has two views:

- **By Game** — three sections: Awaiting Pickup, Picked Up, and No Entries.
- **By Winner** — the same three sections sorted by winner name instead of game name.

Both views support a search bar to filter by game name, winner name, or badge ID. The active tab is preserved across page reloads.

### 9. Redraw Mode

Click **Enter Redraw Mode** in the action bar to reveal advanced actions for managing unclaimed games. Click **Exit Redraw Mode** to hide them again.

While in Redraw Mode, three additional controls are available:

#### Award to Next

Click **Award to Next** on any awaiting game to advance to the next person in the shuffled entry list. This is useful when a winner declines their prize or cannot be reached.

If there are no more eligible players for a game, the app shows a **"To the box!"** alert and moves the game to the No Entries section.

#### Not Here

Click **Not Here** to mark a winner as absent. This advances **all** of their unpicked-up games to the next person in the shuffled list and prevents them from being selected again in any future advances.

#### Redraw All Unclaimed

Click **Redraw All Unclaimed** to run a fresh drawing for all games that have not been picked up. The redraw:

- Re-shuffles entries for each unclaimed game.
- Excludes anyone marked as "Not Here."
- Places original drawing winners last in the shuffle order — they can only win if no other eligible entrants remain for that game.

The one-win-per-person rule does **not** apply during the redraw by default. Check the **"Apply one-win rules"** checkbox before redrawing to enforce the one-win limit.

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
| Winner's Name | Winner's name (empty if no winner) |
| Winner's Badge | Winner's badge ID (empty if no winner) |

Rows are sorted alphabetically by game name. The filename follows the pattern `PawDrawing_ConventionName_2026-03-21.csv`.

## Tips

- **Export CSV before pushing** as a record of the drawing.
- Drawing results are not pushed to TTE until you explicitly click **Push to TTE**.
- **Refresh Data** on the games page fetches the latest entries from TTE. Use this if new entries have been added since you loaded the page.
- **Re-run Drawing** discards the current results and starts fresh. If games have already been picked up, the app warns you and suggests using Redraw Mode instead.
- Refreshing the browser is safe at any point — all state is preserved on the server.
- Each browser/device has its own independent session.

## Troubleshooting

| Message | Cause | What to do |
|---------|-------|------------|
| **Session expired — please log in again.** | Your session timed out. | Log in again. |
| **Request timed out.** | The TTE server is slow or busy. | Retry the action. |
| **Could not load games / entries** | Error fetching data from TTE. | Check the convention ID is correct and retry. |
| **No library found for this convention.** | The convention doesn't have a game library. | Verify you selected the correct convention. |
| **Login failed** | Invalid username or password. | Verify your TTE credentials. |
| **"Error — Retry"** on buttons | Network issue. | Click the button again. |
| **Partial push failures** | Some games failed to update in TTE. | Click **Push to TTE** again — it's safe to retry. |
