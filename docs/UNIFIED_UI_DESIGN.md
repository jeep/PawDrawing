# PawDrawing — Unified UI Design

## Philosophy

One app. One login. One game list. Three modes that progressively unlock as the convention flows. The UI stays consistent — same header, same game table, same expand/collapse — while the *actions available* change based on context.

---

## Global Layout (All Modes)

```
┌─────────────────────────────────────────────────────────────────┐
│  HEADER                                                         │
│  ┌──────────────────────────────────┐            ┌────────────┐ │
│  │         PawDrawing (centered)    │            │   Logout ▸  │ │
│  └──────────────────────────────────┘            └────────────┘ │
│  [🔔 Notifications badge]                                       │
├─────────────────────────────────────────────────────────────────┤
│  TOP MATTER                                                     │
│  PawCon 2026 · Main Library                                     │
│  42 games · 187 participants · 1,204 entries     [⟳ Refresh]   │
│                                                  [⚙ Settings]  │
├─────────────────────────────────────────────────────────────────┤
│  ACTION BAR                                                     │
│  [MODE SELECTOR: ▾ Management ○ | Drawing ○ | Redraw ○ ]       │
│  [Run Drawing] [Manage Players] [Reports]                       │
├─────────────────────────────────────────────────────────────────┤
│  SEARCH BAR                                                     │
│  [ 🔍 Search games... ]                         24 of 42 shown │
├─────────────────────────────────────────────────────────────────┤
│  GAME TABLE                                                     │
│  (content varies by mode — see below)                           │
└─────────────────────────────────────────────────────────────────┘
```

### Header
- Dark bar (`#2c3e50`), centered "PawDrawing" title.
- Notification bell icon (left of logout) with unread count badge. Clicking opens a dropdown listing alerts (non-P2W games, overdue checkouts, etc.). Matches current notification system.
- "Logout (username)" link — far right.

### Top Matter
- Convention name + Library name on one line.
- Stats row: game count, participant count, entry count. Same `.stat` badges as today.
- **Refresh** button — reloads data from TTE (same as current Refresh Data).
- **Settings** button — opens settings panel (see Settings section).

### Action Bar
- **Mode Selector** — pill-style toggle with three states. Active mode is highlighted. Clicking changes mode instantly (no page reload):
  - **Management** — default after login; checkout/checkin operations.
  - **Drawing** — run and resolve the drawing; track pickups.
  - **Redraw** — game-by-game manual awarding for unclaimed prizes.
- **Action Buttons** — context-sensitive, shown/hidden per mode:
  - **Management**: *Run Drawing*, *Manage Players*
  - **Drawing**: *Push to TTE*, *Export CSV*, *Enter Redraw Mode*, *Re-run Drawing*
  - **Redraw**: *Redraw All Unclaimed*, *Push to TTE*, *Export CSV*, *Back to Drawing*
- *Manage Players* opens the existing players management page.
- *Reports* — available in all modes (future placeholder).

### Search Bar
- Same as current implementation: live-filter game rows, show match count.
- Consistent across all modes.

---

## Mode 1: Management

The default mode after login and convention/library selection. The operator manages the physical game library throughout the convention.

### Game Table — Management Mode

```
┌──────────────────────────────────────────────────────────────┐
│ ▸ Game                  │ ID        │ Status       │ Action  │
├─────────────────────────┼───────────┼──────────────┼─────────┤
│ ▸ Catan                 │ PTW-001 ⭐│ Available    │ [Check  │
│                         │           │              │   Out]  │
├─────────────────────────┼───────────┼──────────────┼─────────┤
│ ▾ Azul                  │ PTW-002 ⭐│ Jamie R.     │ [Check  │
│  ├─ Jamie Rodriguez #100│           │  (3.2h)      │    In]  │
│  │  [remove from draw]  │           │              │         │
│  ├─ Sam Chen #205       │           │              │         │
│  │  [remove from draw]  │           │              │         │
│  └─ Alex Kim #312       │           │              │         │
│     [remove from draw]  │           │              │         │
├─────────────────────────┼───────────┼──────────────┼─────────┤
│ ▸ Wingspan              │ PTW-003 ⭐│ Available    │ [Check  │
│                         │           │              │   Out]  │
├─────────────────────────┼───────────┼──────────────┼─────────┤
│ ▸ Mysterium             │ LIB-009   │ Available    │ [Check  │
│                         │           │              │   Out]  │
└──────────────────────────────────────────────────────────────┘
```

**Columns**:
| Column | Content |
|--------|---------|
| **Game** | Expand arrow + game name. Arrow expands to show P2W entrants. |
| **ID** | Catalog number (e.g., PTW-001). ⭐ icon if marked premium/P2W. |
| **Status** | "Available" or renter's name + duration (e.g., "Jamie R. (3.2h)"). Red text if duration > threshold. |
| **Action** | Single button: **Check Out** (available games) or **Check In** (checked-out games). |

**Expansion** (same chevron pattern as current games page):
- Shows P2W entrants for that game in indented rows.
- Each entrant row: `Name #BadgeNumber` with a subtle "remove from drawing" link.
- Removing an entrant ejects them from *that specific game's* drawing (same as current per-game eject).

### Check Out Dialog

Triggered by clicking **Check Out** on an available game. No separate confirmation step.

```
┌──────────────────────────────────────────────────┐
│  Check Out: Catan                                │
│                                                  │
│  Badge #  [ 100        ]                         │
│  Name     [ Jamie Rodriguez    ] (auto-filled)   │
│                                                  │
│           [Cancel]  [Check Out]                   │
└──────────────────────────────────────────────────┘
```

- Badge number field: on blur, auto-lookup via `/badge-lookup`. If found, auto-fills name.
- Name field: editable (for walk-ups without badges).
- **Check Out** → POST, update game row to show renter name + "Check In" button. No page reload.
- On success: game row updates inline; toast confirmation.

### Check In Dialog

Triggered by clicking **Check In** on a checked-out game. No confirmation dialog.

```
┌──────────────────────────────────────────────────────────────┐
│  Check In: Azul                                              │
│  Returning from Jamie Rodriguez                              │
│                                                              │
│  ┌─ Add to Drawing for Azul? ──────────────────────────────┐ │
│  │                                                          │ │
│  │  ☑ Jamie Rodriguez (renter)                              │ │
│  │                                                          │ │
│  │  Suggested:                                              │ │
│  │  ☐ Sam Chen                                              │ │
│  │  ☐ Alex Kim                                              │ │
│  │                                                          │ │
│  │  Badge # [ 312    ]  Name [ Alex Kim     ]  [+ Add]      │ │
│  │                                                          │ │
│  └──────────────────────────────────────────────────────────┘ │
│                                                              │
│           [Cancel]  [Enter into Drawing]  [Skip]             │
└──────────────────────────────────────────────────────────────┘
```

- Title shows game name and who's returning it.
- **P2W entry section** (only shown for P2W games):
  - Renter pre-checked but uncheckable (optional, not forced).
  - Suggested players: people the renter frequently plays with (from play-group data). Limit 10.
  - Manual add row: badge # + name (with auto-fill) + Add button.
- **Three buttons**:
  - *Cancel* — close dialog, game stays checked out.
  - *Enter into Drawing* — check in + create P2W entries for all checked people.
  - *Skip* — check in without P2W entries.
- For non-P2W games: simplified dialog with just Cancel and Check In (no P2W section).
- On success: game row updates to "Available" + "Check Out" button. Toast confirmation.

---

## Mode 2: Drawing

Entered by clicking **Run Drawing** or by switching the mode selector after a drawing has been run. This is the current drawing results page, integrated into the unified layout.

### Pre-Drawing (no results yet)

If no drawing has been run, the game table stays in Management Mode layout but the action bar shows:

```
[MODE: ● Drawing]   [Run Drawing (green)]   [Manage Players]
```

Clicking **Run Drawing** runs the algorithm and transitions to Drawing Results view.

### Drawing Results View

Replaces the game table area with drawing results. Same visual structure as current `drawing_results.html`.

```
┌──────────────────────────────────────────────────────────────┐
│  ACTION BAR                                                  │
│  [MODE: ● Drawing]                                           │
│  [Re-run Drawing]  [Enter Redraw Mode]  [Push to TTE]       │
│  [Export CSV]                                                │
├──────────────────────────────────────────────────────────────┤
│  CONFLICT PANELS (if any — same as current)                  │
│  ┌────────────────────────────────────────────────────────┐  │
│  │ Premium Game Conflicts                                 │  │
│  │ Jamie Rodriguez — Badge: 100                           │  │
│  │  ○ Catan  ○ Azul  [🎲 Random]                         │  │
│  └────────────────────────────────────────────────────────┘  │
├──────────────────────────────────────────────────────────────┤
│  VIEW TABS: [ By Game | By Winner ]                          │
├──────────────────────────────────────────────────────────────┤
│  SEARCH BAR (same as Management mode)                        │
├──────────────────────────────────────────────────────────────┤
│  RESULTS TABLE                                               │
│  ▸ Game          │ Winner         │ Status          │ Action │
│  ▸ Catan ⭐      │ Alex Kim #312  │ Awaiting Pickup │[Picked │
│                  │                │                 │   Up]  │
│  ▸ Azul ⭐       │ Jamie R. #100  │ ✓ Picked Up    │        │
│  ▸ Pandemic ⭐   │ —              │ No entries      │        │
│  ▸ Mysterium     │ Sam Chen #205  │ Awaiting Pickup │[Picked │
│                  │                │                 │   Up]  │
└──────────────────────────────────────────────────────────────┘
```

**Conflict resolution** — identical to current: radio buttons per person, random option, batch resolve. Conflicts appear above the results table and collapse once resolved.

**View tabs** — same By Game / By Winner toggle as current.

**Results table** — same expand/collapse pattern. Expanded rows show shuffled entrant list with position numbers.

**Pickup tracking** — "Mark Picked Up" button per game, toggles to "✓ Picked Up" green state.

---

## Mode 3: Redraw

Activated from Drawing mode via "Enter Redraw Mode". For games where the winner didn't show up to claim their prize.

### Redraw Table

```
┌──────────────────────────────────────────────────────────────┐
│  ACTION BAR                                                  │
│  [MODE: ● Redraw]                                            │
│  [Redraw All Unclaimed]  [Push to TTE]  [Export CSV]         │
│  [☐ Apply one-win rules]  [Back to Drawing]                  │
├──────────────────────────────────────────────────────────────┤
│  SEARCH BAR                                                  │
├──────────────────────────────────────────────────────────────┤
│  UNCLAIMED GAMES                                             │
│  ▸ Game          │ Current       │ Next Up        │ Action   │
│  ▸ Catan ⭐      │ Alex Kim #312 │ Sam Chen #205  │[Skip]    │
│                  │               │                │[Gone]    │
│                  │               │                │[Award ▸] │
│  ▸ Mysterium     │ Sam Chen #205 │ Jamie R. #100  │[Skip]    │
│                  │               │                │[Gone]    │
│                  │               │                │[Award ▸] │
├──────────────────────────────────────────────────────────────┤
│  CLAIMED / TO THE BOX                                        │
│  ▸ Pandemic ⭐   │ —             │ —              │ To the   │
│                  │               │                │   box    │
└──────────────────────────────────────────────────────────────┘
```

**Workflow per unclaimed game**:
1. Call out the current winner's name.
2. If they're present → **Award** → moves to Picked Up.
3. If not at the moment → **Skip** → advances to next person in the shuffled list for *this game only*. The person stays eligible for their other games (they may just be in the bathroom, getting food, etc.).
4. If they've left the convention → **Gone** → removes the person from *all* remaining unclaimed games. Future games skip them automatically so the operator doesn't have to keep calling a name that will never answer.
5. If entire list exhausted → "To the box" (no winner).

**Skip vs Gone**:
| Action | This game | Other games | Use when |
|--------|-----------|-------------|----------|
| **Skip** | Advance to next | No change | "Not here right now" — might show up later |
| **Gone** | Advance to next | Auto-skip everywhere | "Left the convention" — won't be back |

**Expansion** — shows remaining entrant list with current position highlighted. Skipped people are shown with a subtle strikethrough; Gone people are dimmed across all games.

---

## Components Check (Before Drawing)

Before running the drawing, the operator does a "completeness check" to verify the physical library.

### Trigger

In Management mode, before clicking **Run Drawing**, a **Components Check** button (or prompt when Run Drawing is clicked) opens the check view:

```
┌──────────────────────────────────────────────────────────────┐
│  Components Check                                            │
│  Verify all games are accounted for before running the draw. │
│                                                              │
│  ┌─ CHECKED OUT (2) ────────────────────────────────────────┐│
│  │  Azul         │ Jamie Rodriguez │ 3.2h  │ [Force In]    ││
│  │  Pandemic     │ Sam Chen        │ 1.5h  │ [Force In]    ││
│  └──────────────────────────────────────────────────────────┘│
│                                                              │
│  ┌─ AVAILABLE (40) ─────────────────────────────────────────┐│
│  │  ✓ Catan               ✓ Wingspan                       ││
│  │  ✓ Ticket to Ride      ✓ Codenames                      ││
│  │  ... (scrollable)                                        ││
│  └──────────────────────────────────────────────────────────┘│
│                                                              │
│  2 games still out.                                          │
│  [Cancel]  [Proceed — Run Drawing]                           │
└──────────────────────────────────────────────────────────────┘
```

- Checked-out games appear at the top with a **Force In** button (auto-check-in without contacting the renter).
- Available games listed in a compact grid with checkmarks.
- The operator can proceed with checked-out games still out (they just won't be in the drawing).

---

## Player Management

Accessed via **Manage Players** button. Same page as current `players.html`, integrated into the unified layout.

```
┌──────────────────────────────────────────────────────────────┐
│  HEADER (same)                                               │
├──────────────────────────────────────────────────────────────┤
│  ← Back to Games                                             │
├──────────────────────────────────────────────────────────────┤
│  SEARCH: [ 🔍 Search players... ]                            │
├──────────────────────────────────────────────────────────────┤
│  PLAYER TABLE                                                │
│  Player           │ Entries │ Status      │ Action           │
│  Jamie R. #100    │ 5       │ Active      │ [Remove from All]│
│  Sam Chen #205    │ 3       │ Active      │ [Remove from All]│
│  Alex Kim #312    │ 4       │ Removed (2) │ [Restore]        │
│  Staff1 #999      │ 1       │ Staff       │ [Remove from All]│
└──────────────────────────────────────────────────────────────┘
```

- Remove from All = eject from entire drawing (staff, unethical behavior, opt-out).
- Per-game removal available from the expanded game view (back on main page).
- "Removed" players show up with a muted style and a Restore button to undo.

---

## Settings Panel

Opened via the ⚙ Settings button in top matter. Slides in as a side panel or modal.

```
┌──────────────────────────────────────────────────┐
│  Settings                                    [✕] │
│                                                  │
│  Convention                                      │
│  PawCon 2026 · Main Library                      │
│  [Change Source]                                  │
│                                                  │
│  Checkout Alerts                                 │
│  Warn after: [ 3 ] hours                         │
│                                                  │
│  Volunteer Access                                │
│  [Manage Volunteer PINs]                         │
└──────────────────────────────────────────────────┘
```

- **Change Source** moves here (out of the main game page).
- Volunteer PIN management (existing feature) accessible here.

---

## End-to-End Workflow

### Phase 1 — Setup (Day 0 / Morning of Day 1)

```
Login ──▸ Pick Convention & Library ──▸ Games Page (Management Mode)
                                            │
                                            ▼
                                     Review game list
                                     Mark non-P2W games
                                     Mark premiums (⭐)
                                     Verify game count
```

1. Operator logs in with TTE credentials (same login as today).
2. Selects convention and library (same picker as today).
3. Lands on **Management Mode** — sees all games.
4. Scrolls through, notices some games aren't marked P2W → toggles them (or notes for TTE update).
5. Marks some games as Premium via ⭐ toggle in ID column.

### Phase 2 — Convention Runtime (Days 1–3)

```
Management Mode (ongoing)
    │
    ├──▸ Check out game ──▸ Update row to show renter
    ├──▸ Check in game ──▸ P2W entry prompt ──▸ Update row to Available
    ├──▸ Expand game ──▸ See entrants ──▸ Remove suspicious entries
    ├──▸ Notifications ──▸ Overdue checkout alerts
    └──▸ Refresh ──▸ Pull latest from TTE
```

1. Attendee borrows a game → operator clicks **Check Out**, scans/enters badge, submits.
2. Attendee returns game → operator clicks **Check In**, adds P2W entrants (renter + group), submits.
3. Operator periodically checks notifications for overdue games.
4. Operator can expand any game to see who's entered the drawing and remove bad actors.

### Phase 3 — Pre-Drawing (End of Convention)

```
Management Mode
    │
    ▼
Components Check ──▸ Force-in stragglers ──▸ Manage Players
    │                                            │
    │         (remove staff, opt-outs)           │
    ▼                                            ▼
Run Drawing ─────────────────────────────────────┘
```

1. Operator clicks **Run Drawing** (or is prompted with Components Check).
2. Components Check shows which games are still out — **Force In** or leave out.
3. **Manage Players** — remove staff, people who opted out, rule violators.
4. Click **Run Drawing** → algorithm runs → mode switches to **Drawing**.

### Phase 4 — Drawing & Conflicts

```
Drawing Mode
    │
    ├──▸ Resolve premium conflicts (radio buttons)
    ├──▸ Resolve multi-win conflicts
    ├──▸ Announce winners
    └──▸ Track pickups ──▸ [Mark Picked Up] per game
```

1. Conflict panels appear at top (same as current).
2. Operator resolves premium conflicts first, then standard.
3. Results table shows all games with winners.
4. As winners come to claim, operator clicks **Mark Picked Up**.
5. Operator can print list or show it on a screen.

### Phase 5 — Redraw

```
Drawing Mode
    │
    ▼
Enter Redraw Mode ──▸ Redraw Mode
    │
    ├──▸ Per game: call name ──▸ Present? ──▸ [Award]
    │                         ──▸ Not here? ──▸ [Not Here] ──▸ advance
    │                         ──▸ No one left? ──▸ To the box
    └──▸ [Redraw All Unclaimed] for fresh shuffle
```

1. After pickup period ends, unclaimed games need redrawing.
2. Operator enters **Redraw Mode**.
3. Goes game-by-game: calls the current winner, awards if present, marks "Not Here" and advances if not.
4. If entire list is exhausted, game goes to the box.
5. "Redraw All Unclaimed" does a fresh shuffle for all remaining games at once.

### Phase 6 — Finalize

```
Redraw Mode / Drawing Mode
    │
    ▼
Push to TTE ──▸ Done!
```

1. Once all games are accounted for (picked up, awarded, or boxed), operator clicks **Push to TTE**.
2. Results are uploaded. Confirmation toast.
3. Operator can **Export CSV** for records.

---

## Visual Design Notes

### Keep from Current Drawing UI
- Dark header bar (`#2c3e50`) with white text.
- White card containers with subtle shadows.
- Blue accent (`#3498db`) for primary actions.
- Green accent (`#27ae60`) for success / Run Drawing.
- Expand/collapse chevrons for game detail.
- Premium highlight (light yellow `#fef9e7` row + ⭐ label).
- Eject chips with undo (pink `#fdecea`).
- Modal overlay pattern (fixed + centered white card).
- `.stat` badges for counts.
- Live search with result count.
- Sortable table headers with arrow indicators.
- Toggle sliders for premium marking.
- Toast notifications for async feedback.

### New Visual Elements
- **Mode selector** — pill-style toggle, similar to current view tabs (By Game / By Winner). Active mode has solid background, inactive has outline.
- **Status column** — uses color to convey state:
  - Green text = Available
  - Dark text + duration = checked out normally
  - Red text + duration = checked out past threshold
- **Action column** — single contextual button per game row. Blue for Check Out, orange for Check In.
- **Settings side panel** — slides in from right, same card styling, ✕ close button in top-right corner.
- **Notifications dropdown** — absolute-positioned card below bell icon, max-height with scroll, dismiss buttons per notification.

### Responsive Considerations
- On narrow screens: hide ID column, collapse Status into an icon.
- Touch targets remain 44px minimum (existing library CSS).
- Modal dialogs go full-width on mobile.
- Mode selector stacks vertically on small screens.

---

## Technical Notes

### Route Structure (Proposed)
All routes stay under the existing structure. No new blueprints needed. Mode is a session variable, not a URL path.

```
GET  /games                 — main page (mode from session)
POST /games/checkout        — check out a game
POST /games/checkin         — check in a game
POST /games/p2w-entry       — add P2W entries
GET  /games/entrants/<id>   — get entrants (existing)
POST /games/premium         — toggle premium (existing)
POST /games/eject           — eject player (existing)
POST /games/uneject         — restore player (existing)
GET  /games/players         — player management (existing)
POST /drawing               — run drawing (existing)
GET  /drawing/results       — drawing results (existing)
POST /drawing/push          — push to TTE (existing)
GET  /settings              — settings panel content
POST /settings/source       — change convention/library
```

### Session Keys
- `app_mode` — `"management"` | `"drawing"` | `"redraw"` (drives UI rendering)
- All existing session keys remain unchanged.

### Migration Path
1. Merge checkout/checkin routes from `routes/library/` into `routes/` main routes.
2. Integrate the library game table columns (Status, Action) into `games.html`.
3. Move change-source into settings panel.
4. Add Components Check as a modal/interstitial before Run Drawing.
5. Add mode selector UI + session toggle.
6. Retire separate library templates (dashboard, game_list, game_detail, nav).
