# PawDrawing — Play and Win Drawing Management System

## Requirements Document

**Version:** 2.0
**Date:** 2026-03-21
**Status:** Final — all clarifying questions resolved

---

## 1. Overview

PawDrawing is a web application for managing Play-and-Win drawings at tabletop gaming conventions. It integrates with the **tabletop.events (TTE) API** to retrieve game library and player entry data, then performs a randomized drawing to determine winners according to configurable rules.

---

## 2. Goals

- Automate the Play-and-Win drawing process for convention game libraries.
- Provide a clear, user-friendly interface to view drawing results.
- Handle the multi-round conflict resolution process when one person wins multiple games.
- Support "premium" game designation to expedite conflict resolution.

---

## 3. External System Integration

### 3.1 Tabletop.Events API

- **Base URL:** `https://tabletop.events/api/`
- **Authentication:** Session-based. Login via `POST /api/session` requires `username`, `password`, and `api_key_id`.
- **API Key:** Stored in `Application API Key.txt` (not committed to version control in production).
- **Rate Limit:** Max 1 request per second.
- **Response Format:** JSON with `{ "result": { ... } }` wrapper. Paginated lists return `{ "result": { "paging": {...}, "items": [...] } }`.

### 3.2 Relevant API Endpoints

| Endpoint | Method | Purpose |
|---|---|---|
| `POST /api/session` | POST | Authenticate and obtain `session_id` |
| `DELETE /api/session/{id}` | DELETE | End session |
| `GET /api/convention/{id}` | GET | Read convention details (includes `library` related object) |
| `GET /api/convention/{id}/playtowins` | GET | List all PlayToWin entries for a convention |
| `GET /api/library/{id}` | GET | Read library details |
| `GET /api/library/{id}/games` | GET | List games in a library (filterable by `is_play_to_win=1`) |
| `GET /api/library/{id}/playtowins` | GET | List all PlayToWin entries for a library |
| `GET /api/librarygame/{id}` | GET | Read a specific library game |
| `GET /api/librarygame/{id}/playtowins` | GET | List PlayToWin entries for a specific game |
| `GET /api/playtowin/{id}` | GET | Read a PlayToWin entry |
| `PUT /api/playtowin/{id}` | PUT | Update a PlayToWin entry (e.g., set `win` flag) |

### 3.3 Key Data Models

#### PlayToWin Entry
| Field | Type | Description |
|---|---|---|
| `id` | char (GUID) | Unique ID |
| `name` | varchar | Entrant's name (required) |
| `library_id` | char | Library this entry belongs to (required) |
| `librarygame_id` | char | Game entered for (required) |
| `badge_id` | char | Badge of entrant (nullable) |
| `convention_id` | char | Convention (nullable) |
| `user_id` | char | TTE user ID (nullable) |
| `email_address` | varchar | Entrant email (owner-visible only) |
| `phone_number` | varchar | Entrant phone (owner-visible only) |
| `win` | tinyint | Winner flag (default: 0) |
| `date_created` | datetime | Entry timestamp |

#### LibraryGame (relevant fields)
| Field | Type | Description |
|---|---|---|
| `id` | char (GUID) | Unique ID |
| `name` | varchar | Game name |
| `catalog_number` | varchar | Catalog/reference number |
| `is_play_to_win` | tinyint | Whether game is in the Play-to-Win program |
| `publisher_name` | varchar | Publisher |
| `description` | mediumtext | Game description |
| `bgg_id` | int | BoardGameGeek ID |
| `min_players` | tinyint | Min player count |
| `max_players` | tinyint | Max player count |

---

## 4. Functional Requirements

### 4.1 Authentication

- **FR-AUTH-01:** The system shall present a login screen where the administrator enters their TTE username and password.
- **FR-AUTH-02:** The system shall authenticate with the TTE API using the entered credentials and the pre-configured API key.
- **FR-AUTH-03:** The session ID shall be stored securely in the server-side session and used for all subsequent API calls.
- **FR-AUTH-04:** The system shall handle session expiration gracefully and re-authenticate when necessary.

### 4.2 Convention & Library Selection

- **FR-SEL-01:** The system shall allow the administrator to search for conventions by name or paste a convention ID directly.
- **FR-SEL-02:** The system shall retrieve the library associated with the selected convention (the convention's `library` related object).
- **FR-SEL-03:** The system shall retrieve all LibraryGames marked with `is_play_to_win=1` from the convention's library.
- **FR-SEL-04:** The system shall optionally allow filtering PlayToWin entries by `convention_id`. If a convention ID is provided, only entries matching that convention are included; otherwise, all entries for the library are included.

### 4.3 Drawing Data Retrieval

- **FR-DATA-01:** The system shall retrieve all PlayToWin entries for the selected convention/library.
- **FR-DATA-02:** PlayToWin entries without a `badge_id` shall be excluded from the drawing.
- **FR-DATA-03:** The system shall de-duplicate entries on load: only one entry per `badge_id` per `librarygame_id` shall be kept, regardless of how many times the person played.
- **FR-DATA-04:** The system shall group de-duplicated entries by `librarygame_id` to determine which unique players entered the drawing for each game.
- **FR-DATA-05:** The "number of entries" displayed for each game shall be the count of unique entrants (unique `badge_id` values).
- **FR-DATA-06:** The system shall handle paginated API responses, fetching all pages as needed.
- **FR-DATA-07:** The system shall respect the TTE rate limit of 1 request per second.

### 4.4 Drawing Algorithm

- **FR-DRAW-01:** For each game, the list of unique entrants (by `badge_id`) shall be randomly shuffled. A one-time random shuffle is sufficient (no need for reproducible seeds).
- **FR-DRAW-02:** The full shuffled list for each game shall be preserved for use in redistribution (Section 4.7).
- **FR-DRAW-03:** The first player in the shuffled list for each game shall be the initial winner.
- **FR-DRAW-04:** Entrant identity across games shall be matched by `badge_id` to detect multi-game winners.
- **FR-DRAW-05:** If a person (by `badge_id`) wins multiple games, the administrator shall be prompted to choose which game that person will keep.
- **FR-DRAW-06:** For games the multi-winner did not keep, the next player in the shuffled list shall become the winner.
- **FR-DRAW-07:** The conflict resolution process (steps FR-DRAW-05 and FR-DRAW-06) shall repeat iteratively until each game has exactly one unique winner.
- **FR-DRAW-08:** The administrator may designate games as "premium" via the UI before running the drawing. When a person wins multiple games including a premium game, the premium game is automatically selected for them.
- **FR-DRAW-09:** If a person wins multiple premium games, the administrator shall choose which premium game the person keeps, and the other premium games cascade to their next eligible player.
- **FR-DRAW-10:** The drawing algorithm shall continue iterating until there are no remaining conflicts (each game has a unique winner).
- **FR-DRAW-11:** The drawing may be re-run by the administrator if there is an issue. Re-running generates a new random shuffle.

### 4.5 Results Display

- **FR-DISP-01:** The system shall display results in two views:
  - **By Game:** For each game, show the game name, number of unique entries, and the winner's name.
  - **By Winner:** For each winner, show the game they won.
- **FR-DISP-02:** The interface shall clearly indicate games that are still in conflict resolution.
- **FR-DISP-03:** The interface shall highlight "premium" games distinctly.
- **FR-DISP-04:** Games with zero entries shall be displayed with a "No entries" indicator.
- **FR-DISP-05:** Results are displayed in the browser during the active session.
- **FR-DISP-06:** The system shall provide a "Save" / "Export" button to download results as a CSV file.

### 4.6 Pickup & Redistribution

- **FR-PICK-01:** After the drawing is complete, the administrator shall be able to mark each won game as "picked up" when the winner collects the game.
- **FR-PICK-02:** Pickup status shall be tracked locally within the PawDrawing session.
- **FR-PICK-03:** After the pickup deadline has passed, the administrator shall be able to initiate a **redistribution** of all unclaimed (not picked up) games in a single batch session.
- **FR-PICK-04:** For each unclaimed game, the system shall display the original shuffled entrant list for that game, starting from the top.
- **FR-PICK-05:** During redistribution, the one-win-per-person rule does **not** apply. A person who already won and picked up another game may also claim an unclaimed game.
- **FR-PICK-06:** The admin shall work down the shuffled list in order. The first person in attendance who claims the game becomes the new winner. If no one claims it, the game remains unclaimed.
- **FR-PICK-07:** The system shall provide a "Push to TTE" action that writes the `win` flag back to TTE (via `PUT /api/playtowin/{id}`) for all picked-up games. This is intended as a cleanup step after the drawing and pickup process is complete.

### 4.7 Error Handling

- **FR-ERR-01:** The system shall display user-friendly error messages when API requests fail.
- **FR-ERR-02:** The system shall handle invalid or unexpected API responses gracefully (e.g., missing fields, empty result sets).
- **FR-ERR-03:** The system shall handle the case where a game has zero entries (display "No entries").
- **FR-ERR-04:** The system shall handle network timeouts and offer retry options.

---

## 5. Non-Functional Requirements

- **NFR-01:** The application shall be built as a web application using an appropriate web framework (framework choice is open — e.g., Flask, Django, Express.js, or similar).
- **NFR-02:** The user interface shall be simple, clean, and accessible on desktop browsers.
- **NFR-03:** API credentials (API key, session tokens) shall not be exposed to the client-side browser.
- **NFR-04:** The API key shall not be committed to version control.
- **NFR-05:** The system shall comply with TTE rate limiting (max 1 request per second).
- **NFR-06:** The application shall support running both locally (on a laptop at the convention) and on a hosted server.
- **NFR-07:** Only one administrator is expected to use the system at a time; concurrent multi-user access is not required.

---

## 6. User Roles

| Role | Description |
|---|---|
| **Administrator** | Runs the drawing, resolves conflicts, designates premium games. Full access. |

---

## 7. User Workflow

### 7.1 Drawing Phase

1. Administrator opens the application and enters TTE credentials (username/password) on the login screen.
2. Administrator searches for a convention by name or pastes a convention ID. Optionally provides a `convention_id` filter for PlayToWin entries.
3. System loads all play-to-win games and entries from TTE, de-duplicates (one entry per badge_id per game), and excludes entries without a badge_id.
4. Administrator optionally marks games as "premium" in the UI.
5. Administrator initiates the drawing.
6. System performs randomized shuffle for each game and identifies initial winners.
7. If conflicts exist (one person winning multiple games):
   a. Premium games are auto-assigned first.
   b. If a person won multiple premium games, the admin chooses which one they keep.
   c. Administrator resolves remaining non-premium conflicts by choosing which game each multi-winner keeps.
   d. Unclaimed games cascade to next player in shuffled order.
   e. Process repeats until all conflicts resolved.
8. Final results displayed by game and by winner.

### 7.2 Pickup Phase

9. As winners collect their games at the convention, the administrator marks each game as "picked up" in the app.

### 7.3 Redistribution Phase

10. After the pickup deadline passes, the administrator initiates redistribution of all unclaimed games.
11. For each unclaimed game, the system shows the original shuffled list of entrants.
12. The admin works down the list in order; the first person present who claims the game becomes the new winner.
13. The one-win-per-person rule does not apply during redistribution.

### 7.4 Finalization

14. Administrator optionally exports results as CSV.
15. Administrator clicks "Push to TTE" to write the `win` flag for all picked-up games back to TTE.
16. Session ends.

---

## 8. API Flow Diagram

```
[Admin Browser] --> [PawDrawing Server]
                          |
           LOGIN:         |--> POST /api/session (authenticate, get session_id)
                          |
           SETUP:         |--> GET /api/convention?query=... (search conventions)
                          |    or GET /api/convention/{id} (direct lookup)
                          |--> GET /api/convention/{id}?_include_related_objects=library
                          |--> GET /api/library/{id}/games?is_play_to_win=1 (get P2W games)
                          |       (paginated, all pages)
                          |--> GET /api/convention/{id}/playtowins (get entries)
                          |    or GET /api/library/{id}/playtowins
                          |       (paginated, all pages)
                          |
           DRAWING:       |--> [Drawing Algorithm runs server-side]
                          |    (shuffle, conflict resolution, admin choices)
                          |
           PICKUP:        |--> [Local tracking of picked-up games]
                          |
           REDISTRIBUTE:  |--> [Admin walks shuffled lists for unclaimed games]
                          |
           PUSH TO TTE:   |--> PUT /api/playtowin/{id} (set win=1 for picked-up entries)
                          |       (for each picked-up game, respecting rate limits)
                          |
           LOGOUT:        |--> DELETE /api/session/{id}
```

---

## 9. Assumptions

1. The TTE API will remain stable and accessible during use of this application.
2. The administrator has a TTE account with sufficient privileges to read PlayToWin data for the target convention/library.
3. Entrant identity is matched by `badge_id` for detecting multi-game winners. Entries without a `badge_id` are excluded.
4. Each person gets one drawing entry per game regardless of how many times they played (de-duplicated by `badge_id` + `librarygame_id`).
5. The drawing and pickup phases may span the duration of a convention but are managed within a single browser session (or with CSV export to preserve state).
6. During redistribution, the one-win-per-person rule does not apply.
