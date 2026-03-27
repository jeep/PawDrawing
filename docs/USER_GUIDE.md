# User Guide

## Overview

PawDrawing runs Play-to-Win prize drawings at tabletop gaming conventions. It connects to [tabletop.events](https://tabletop.events) to pull convention data, manage game checkouts, runs a randomized drawing, and pushes the winning entries back.

The app is available at:

> https://pawdrawing.azurewebsites.net

## Workflow

### 1. Log in

Navigate to the app and log in with your tabletop.events username (or email
address), password, and API key. Each user must provide their own API key from
their TTE account. If you check **"Remember API key on this device"** (on by
default), the API key is saved in your browser’s local storage so you don’t
have to re-enter it next time.

**To get your API key:** Log in to [tabletop.events](https://tabletop.events),
click your username in the upper-right corner, then click **API Keys**. If you
already have a key, you can use it. Otherwise, click **Create**, fill in a name
(and optionally a URL and reason), and copy the generated key to enter into
PawDrawing.

### 2. Select a source

The source selection page has two tabs:

**Convention tab** (default): Search for your convention by name, or paste the convention ID directly. The app fetches the convention details and its associated game library. Play-to-Win entries are scoped to the convention.

**Library Only tab**: If you want to draw from a library without a convention (or the library exists independently), switch to the "Library Only" tab. You can browse your libraries or paste a library ID directly. In library-only mode, all Play-to-Win entries in the library are included regardless of convention.

### 3. Navigation

All pages share a **mode selector** with four tabs:

- **Manage Games** — day-of-convention operations: checking games in and out, recording P2W entries, monitoring the library.
- **Manage Players** — review and manage player entries before running the drawing.
- **Drawing Prep** — pre-drawing checklist: refresh data, component check, stats overview, suspicious activity, and player removal summary.
- **Drawing** — run the drawing, resolve conflicts, track pickups, push results.

Click a tab to switch between views. The mode selector appears at the top of every page.

### 4. Management mode

After selecting a source, the app opens in **Manage Games** mode. This is the unified view for day-of-convention operations: checking games in and out, recording P2W entries, and monitoring the library.

#### Game list

The game list shows all Play-to-Win games with sortable columns and a search bar. Each game shows its checkout status, P2W entry count, and available actions.

#### Checking out a game

Click a game's **Check Out** button, enter the borrower's name and (optionally) badge number, then confirm. The app verifies the game is available before creating the checkout.

#### Checking in a game

Click the **Check In** button on a checked-out game to return it to the library.

#### Recording P2W entries

After checking out a P2W game, the app prompts you to record a Play-to-Win entry for the borrower. You can also add entries manually via the game detail panel.

#### Badge lookup

Enter a badge number to look up an attendee's name. The result is cached for the session so you don't need to look up the same badge twice.

#### Notifications

The notification panel shows alerts generated on refresh:

- **Suspicious checkouts:** Games checked out longer than the configured alert threshold. Configurable in Settings.
- **Partner patterns:** Groups of people who repeatedly check out and return games together (potential P2W gaming).
- **Non-P2W games:** Games in circulation that are not marked Play-to-Win.

Notifications can be dismissed individually.

#### Settings

Click the **Settings** gear icon to configure:

- **Checkout alert threshold:** Hours before a checkout triggers a suspicious alert (default: 3).
- **Include non-P2W games:** Whether to include non-P2W games in the management view.
- **Mark All Games as P2W:** Bulk-mark all non-P2W games as Play-to-Win in TTE.

### 5. Volunteer login

Library owners can delegate checkout duties to volunteers. Click **Volunteer Login** and enter the volunteer's TTE credentials. The app verifies they have checkout privileges on the library.

Volunteers can check out and check in games but cannot run drawings or push results. When a volunteer logs out, the library context is preserved so the next volunteer can log in without re-selecting the convention.

### 6. Review games and manage players

Switch to the **Manage Players** tab using the mode selector. This page lists every player who entered a Play-to-Win game, along with their badge ID, the number of games they entered, and which games.

To exclude a player from the drawing, click **Remove from Drawing** next to their name. To exclude them from a single game, expand their row and click **Remove from Game** on the specific game.

Removed players are shown with a "Removed" badge and can be restored at any time before running the drawing. Removals are cleared when you change the convention or library source.

### 7. Designate premium games

Toggle the "Premium" checkbox on any games that are premium prizes. Premium games get special treatment during conflict resolution — if a person wins one premium game and one or more non-premium games, they automatically keep the premium game.

Premium designations are auto-saved as you toggle them.

### 8. Drawing Prep

Switch to the **Drawing Prep** tab before running the drawing. This page provides a pre-drawing checklist:

- **Refresh Data** — click to fetch the latest games and entries from TTE. With a large library, this can take several seconds (typically 5+ API calls).
- **Drawing Overview** — shows total games, total entries, unique participants, and how many games have zero entries.
- **Component Check** — lists any Play-to-Win games currently checked out, with a **Force In** button to check them in. Also shows the full grid of available P2W games.
- **Suspicious Activity** — summarizes any alerts (long checkouts, partner patterns).
- **Player Removals** — shows how many players have been removed from the drawing.

Visiting this page marks prep as complete. If you navigate to the Drawing tab without visiting Drawing Prep first, a warning banner appears (you can still proceed).

### 9. Run the drawing

Switch to the **Drawing** tab using the mode selector. Click **Run Drawing**. The app:

1. Randomly shuffles all entries for each game.
2. Selects the first person in each shuffled list as the initial winner.
3. Detects conflicts (one person winning multiple games).
4. Auto-resolves premium conflicts where possible.

To pick up the latest data from TTE before drawing, use the **Refresh Data** button on the **Drawing Prep** tab.

### 10. Resolve conflicts

If any conflicts remain after auto-resolution, you'll see conflict panels at the top of the results page. For each conflicting person, select which game they should keep, or click **🎲 Random** to choose randomly.

You can also click the **dismiss (✕)** button on a specific game to remove that person from it and advance to the next candidate. If there are no more candidates, the game is marked **"No winner (redraw eligible)"** — it remains available in the redraw rather than being sent to the box.

Resolution may cascade — new conflicts can appear when an alternate winner is selected. Repeat until all conflicts are resolved.

### 11. Track pickups

As winners come to claim their prizes, click **Mark Picked Up** next to each game. The button turns green. Click again to undo if needed. The pickup counter in the summary bar updates in real time.

The results page has two views:

- **By Game** — three sections: Awaiting Pickup, Picked Up, and No Entries.
- **By Winner** — the same three sections sorted by winner name instead of game name.

Both views support a search bar to filter by game name, winner name, or badge ID. The active tab is preserved across page reloads.

### 12. Redraw Mode

Click **Enter Redraw Mode** in the action bar to reveal advanced actions for managing unclaimed games. Click **Exit Redraw Mode** to hide them again.

While in Redraw Mode, three additional controls are available:

#### Award to Next

Click **Award to Next** on any awaiting game to advance to the next person in the shuffled entry list. This is useful when a winner declines their prize or cannot be reached.

If there are no more eligible players for a game, the app shows a **"To the box!"** alert and moves the game to the No Entries section.

#### Gone

Click **Gone** to mark a winner as absent. This advances **all** of their unpicked-up games to the next person in the shuffled list and prevents them from being selected again in any future advances.

#### Redraw All Unclaimed

Click **Redraw All Unclaimed** to run a fresh drawing for all games that have not been picked up. The redraw:

- Re-shuffles entries for each unclaimed game.
- Excludes anyone marked as "Gone."
- Places original drawing winners last in the shuffle order — they can only win if no other eligible entrants remain for that game.

The one-win-per-person rule does **not** apply during the redraw by default. Check the **"Apply one-win rules"** checkbox before redrawing to enforce the one-win limit.

### 13. Push results to TTE

Click **Push to TTE** to write the win flags back to tabletop.events. Only picked-up games are pushed. The app shows a confirmation dialog with the count, then pushes each winner individually.

Results:
- **Success**: All games updated.
- **Partial success**: Some failed — review the error list and retry.
- **Network error**: Check connectivity and try again.

### 14. Export CSV

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
- **Refresh Data** on the **Drawing Prep** tab fetches the latest entries from TTE. Use this if new entries have been added since you loaded the page.
- **Re-run Drawing** discards the current results and starts fresh. If games have already been picked up, the app warns you and suggests using Redraw Mode instead.
- Refreshing the browser is safe at any point — all state is preserved on the server.
- Each browser/device has its own independent session.

## Using Multiple Devices

Multiple volunteers can use PawDrawing on separate devices simultaneously for checkout duties. Keep these things in mind:

- **Checkouts and checkins are shared.** When a volunteer checks out or checks in a game on one device, other devices update automatically within about 30 seconds — no manual refresh needed. (The checkout is also sent to TTE immediately, so a full Refresh will always show the latest state.)
- **Ejections, notifications, and settings are shared.** Removing a player from the drawing, dismissing a notification, or changing settings on one device is visible on all other devices working with the same library.
- **Person cache and play groups are shared.** Badge lookups and P2W co-entrant tracking accumulate across all devices, so you don't need to repeat lookups.
- **The game list can be stale.** Each device caches its own copy of the game list. Checkout statuses auto-update every 30 seconds, but new P2W entries or newly added games require a manual **Refresh**. The app checks availability before each checkout to prevent double-checkouts.
- **Premium designations are per-device.** These are set on each device independently, or designate one device as the "primary."
- **Component checks are per-device.** If a volunteer marks a game's components as checked on their device, other devices won't see that record.
- **Run the drawing from one device.** Drawing results, pickup tracking, and redraw operations exist only on the device that ran the drawing. Use the library owner's device for the drawing.
- **Refreshing is not instant.** A refresh fetches data from TTE (typically 5+ API calls). With a large library, this can take several seconds.

## Troubleshooting

| Message | Cause | What to do |
|---------|-------|------------|
| **Session expired — please log in again.** | Your session timed out. | Log in again. |
| **Request timed out.** | The TTE server is slow or busy. | Retry the action. |
| **Could not load games / entries** | Error fetching data from TTE. | Check the convention ID is correct and retry. |
| **No library found for this convention.** | The convention doesn't have a game library. | Verify you selected the correct convention. |
| **Login failed** | Invalid username or password. | Verify your TTE credentials. |
| **Your account does not have checkout privileges** | Volunteer lacks checkout permission on this library. | Ask the library owner to grant checkout access in TTE. |
| **This game is already checked out.** | Another volunteer checked it out since your last refresh. | Click **Refresh** and try again. |
| **"Error — Retry"** on buttons | Network issue. | Click the button again. |
| **Partial push failures** | Some games failed to update in TTE. | Click **Push to TTE** again — it's safe to retry. |
