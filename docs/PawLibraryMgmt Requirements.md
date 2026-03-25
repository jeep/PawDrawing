# PawLibraryMgmt — Convention Game Library Checkout Management

## Requirements Document

**Version:** 1.0
**Date:** 2026-03-25
**Status:** Draft

---

## 1. Overview

PawLibraryMgmt is a mode within the PawDrawing application for managing game library checkouts at tabletop gaming conventions. It replaces the clunky checkout workflow on tabletop.events with a streamlined, multi-volunteer interface optimized for convention-floor speed. It integrates with the **tabletop.events (TTE) API** for all checkout, check-in, and Play-to-Win entry operations.

This feature shares authentication, TTE client infrastructure, and deployment with the existing PawDrawing module. A mode toggle in the UI switches between "Library Management" (this feature) and "Drawing" (the existing PawDrawing feature).

---

## 2. Goals

- Provide a fast, intuitive checkout/check-in workflow that improves on TTE's built-in interface.
- Support up to 5 concurrent volunteers operating the library at a single convention.
- Minimize expensive TTE API calls by loading the game catalog once and refreshing individual games on demand.
- Support both convention-linked libraries and independent (standalone) libraries.
- Enable quick Play-to-Win drawing entry at checkout time, with smart suggestions for who to enter.
- Enable game and person lookup for real-time library status visibility.
- Provide operational tools: low-play/low-checkout game lists, component check tracking, and suspicious checkout detection.
- Share the game list between Library Management and Drawing modes so both operate on the same data.

---

## 3. External System Integration

### 3.1 Tabletop.Events API

- **Base URL:** `https://tabletop.events/api/`
- **Authentication:** Session-based. Login via `POST /api/session` requires `username`, `password`, and `api_key_id`.
- **API Key:** Stored in `Application API Key.txt` (not committed to version control in production).
- **Rate Limit:** Max 1 request per second.
- **Response Format:** JSON with `{ "result": { ... } }` wrapper. Paginated lists return `{ "result": { "paging": {...}, "items": [...] } }`.

See [PawDrawing Requirements](Requirements.md) §3.1 for shared API details.

### 3.2 Relevant API Endpoints

| Endpoint | Method | Purpose |
|---|---|---|
| **Session** | | |
| `POST /api/session` | POST | Authenticate and obtain `session_id` |
| `DELETE /api/session/{id}` | DELETE | End session |
| **Library & Games** | | |
| `GET /api/library/{id}` | GET | Read library details |
| `GET /api/library/{id}/games` | GET | List games in a library (searchable, filterable) |
| `GET /api/library/{id}/checkouts` | GET | List all checkouts for a library (filterable by `is_checked_in`) |
| `GET /api/librarygame/{id}` | GET | Read a specific library game |
| `GET /api/librarygame/{id}/checkouts` | GET | List checkouts for a specific game |
| `GET /api/librarygame/{id}/playtowins` | GET | List Play-to-Win entries for a specific game |
| **Checkouts** | | |
| `GET /api/librarygamecheckout` | GET | Search checkouts across libraries (by `query` on `renter_name`) |
| `POST /api/librarygamecheckout` | POST | Create a checkout (requires `library_id`, `librarygame_id`, `renter_name`) |
| `GET /api/librarygamecheckout/{id}` | GET | Read a checkout |
| `PUT /api/librarygamecheckout/{id}` | PUT | Update a checkout |
| `DELETE /api/librarygamecheckout/{id}` | DELETE | Delete a checkout |
| `POST /api/librarygamecheckout/{id}/checkin` | POST | Check in a game (return to library) |
| **Play-to-Win Entries** | | |
| `POST /api/playtowin` | POST | Create a P2W entry (requires `library_id`, `librarygame_id`, `renter_name`) |
| `GET /api/playtowin/{id}` | GET | Read a P2W entry |
| **Convention & Badges** | | |
| `GET /api/convention/{id}` | GET | Read convention details (includes `library` related object) |
| `GET /api/convention/{id}/badges` | GET | Search badges (by `query` on name/email/badge_number) |
| **Library Privileges** | | |
| `GET /api/libraryprivilege/{id}` | GET | Read a library privilege |
| `POST /api/libraryprivilege` | POST | Create a library privilege (requires `library_id`, `user_id`) |

### 3.3 Key Data Models

#### LibraryGameCheckout
| Field | Type | Description |
|---|---|---|
| `id` | char (GUID) | Unique ID |
| `renter_name` | varchar | Person who checked out the game (required) |
| `library_id` | char | Library this checkout belongs to (required) |
| `librarygame_id` | char | Game checked out (required) |
| `badge_id` | char | Badge of renter (nullable) |
| `convention_id` | char | Convention (nullable) |
| `user_id` | char | TTE user ID (nullable) |
| `email_address` | varchar | Renter email (owner-visible only) |
| `phone_number` | varchar | Renter phone (owner-visible only) |
| `date_of_birth` | varchar | Renter DOB (owner-visible only) |
| `postal_code` | varchar | Renter postal code (owner-visible only) |
| `notes` | mediumtext | Checkout notes (owner-visible only) |
| `is_checked_in` | int | 0 = currently out, 1 = returned (default: 0) |
| `checkin_date` | datetime | When the game was returned (nullable) |
| `checkedout_seconds` | int | Duration of checkout in seconds (default: 0) |
| `date_created` | datetime | Checkout timestamp |

#### LibraryGame (relevant fields)
| Field | Type | Description |
|---|---|---|
| `id` | char (GUID) | Unique ID |
| `name` | varchar | Game name |
| `catalog_number` | varchar | Catalog/reference number |
| `is_play_to_win` | tinyint | Whether game is in the Play-to-Win program |
| `is_checked_out` | tinyint | Whether game is currently checked out |
| `is_in_circulation` | tinyint | Whether game is available for checkout |
| `publisher_name` | varchar | Publisher |
| `min_players` | tinyint | Min player count |
| `max_players` | tinyint | Max player count |
| `min_play_time` | int | Minimum play time in minutes (nullable) |
| `max_play_time` | int | Maximum play time in minutes (nullable) |
| `checkout_count` | int | Total number of checkouts |

#### LibraryPrivilege
| Field | Type | Description |
|---|---|---|
| `id` | char (GUID) | Unique ID |
| `library_id` | char | Library this privilege belongs to (required) |
| `user_id` | char | User granted the privilege (required) |
| `catalog` | tinyint | Can manage game catalog (default: 1) |
| `checkouts` | tinyint | Can manage checkouts (default: 1) |
| `settings` | tinyint | Can manage library settings and privileges (default: 1) |

#### Badge (relevant fields)
| Field | Type | Description |
|---|---|---|
| `id` | char (GUID) | Unique ID |
| `name_full` | varchar | Attendee full name |
| `badge_number` | varchar | Convention badge number |
| `convention_id` | char | Convention this badge belongs to |
| `user_id` | char | TTE user ID |

#### PlayToWin Entry
See [PawDrawing Requirements](Requirements.md) §3.3 for the full PlayToWin data model.

---

## 4. Functional Requirements

### 4.1 Authentication

- **FR-AUTH-01:** The system shall support two login modes:
  - **Owner Login:** The library owner logs in with their TTE credentials. All volunteers share this session. This is the recommended mode for most use cases.
  - **Volunteer Login:** Each volunteer logs in with their own TTE credentials and API key. Requires each volunteer to have a TTE account and their own API key.
- **FR-AUTH-02:** The default mode shall be Owner Login. Volunteer Login shall be available as an option in the UI.
- **FR-AUTH-03:** In Owner Login mode, the single TTE session is shared across all connected browsers. The server manages one `session_id` for the library.
- **FR-AUTH-04:** In Volunteer Login mode, each volunteer authenticates independently and the server manages separate TTE sessions.
- **FR-AUTH-05:** The system shall use the TTE `LibraryPrivilege` API to verify that a volunteer's account has the `checkouts` privilege on the selected library before allowing checkout operations.

### 4.2 Library Selection

- **FR-SEL-01:** The system shall support two library source modes:
  - **Convention Library:** Select a convention, and the system retrieves its associated library.
  - **Independent Library:** Select a library directly by browsing the user's libraries or pasting a library ID.
- **FR-SEL-02:** For convention-linked libraries, the system shall have access to convention badge data for badge lookups.
- **FR-SEL-03:** For independent libraries, the system shall not assume badge data is available (see §4.4 for person identification).

### 4.3 Game Catalog Loading

- **FR-CAT-01:** On library selection, the system shall perform a one-time full fetch of all games from `GET /api/library/{id}/games`. By default, only Play-to-Win games (`is_play_to_win=1`) are loaded for checkout management. The user may opt in to include non-P2W games via a setting. This loading operation may take 2–3 minutes for large libraries.
- **FR-CAT-02:** The system shall display a loading indicator with progress information during the initial catalog fetch.
- **FR-CAT-03:** The game catalog shall be cached server-side and shared across all volunteers using the same library. This is the same game list used by Drawing mode — both modes operate on a single shared catalog.
- **FR-CAT-04:** When a specific game is selected for checkout or lookup, the system shall fetch fresh data for that single game from `GET /api/librarygame/{id}` to get current availability and checkout status.
- **FR-CAT-05:** The system shall provide a manual "Refresh Catalog" action to re-fetch the full game list from TTE.
- **FR-CAT-06:** The game catalog cache shall include, at minimum: game ID, name, catalog number, player counts, play time range, Play-to-Win status, checked-out status, and circulation status.
- **FR-CAT-07:** If the library contains non-P2W games, the system shall create a notification after initial load informing the user (e.g., "12 games in this library are not marked Play-to-Win"). The notification shall be expandable to show the list of non-P2W games (when the count is reasonable). This alerts the user in case the full library was intended to be P2W.
- **FR-CAT-08:** The system shall provide a "Mark All as Play-to-Win" action that sets `is_play_to_win=1` on all **in-circulation** games (`is_in_circulation=1`) in the library via `PUT /api/librarygame/{id}`. Games not in circulation shall not be affected. This action shall require explicit confirmation with a clear warning (e.g., "This will mark all N in-circulation games as Play-to-Win. This cannot be easily undone. Are you sure?").

### 4.4 Person Identification

- **FR-PERSON-01:** For **convention-linked libraries**, the system shall identify people by badge number. The volunteer enters a badge number, and the system looks up the attendee's name via the convention's badge API (`GET /api/convention/{id}/badges?query={badge_number}&query_field=badge_number`).
- **FR-PERSON-02:** For **independent libraries**, the system shall collect both a **badge number** (or other ID) and a **name** from the renter.
- **FR-PERSON-03:** When a person is seen for the first time, the system shall store the badge-number-to-name mapping in a local cache for the session.
- **FR-PERSON-04:** On subsequent encounters, entering the badge number shall auto-populate the person's name from the cache.
- **FR-PERSON-05:** The person cache shall persist for the duration of the library session (not just a single browser tab).

### 4.5 Game Checkout

- **FR-CHKOUT-01:** The volunteer shall search for a game by name or catalog number.
- **FR-CHKOUT-02:** The system shall use `GET /api/library/{id}/games?query={search_term}` for name search and `GET /api/library/{id}/games?query={number}&query_field=catalog_number` for catalog number search.
- **FR-CHKOUT-03:** The search results shall show game availability status (available, checked out, not in circulation).
- **FR-CHKOUT-04:** The volunteer shall identify the renter (per §4.4).
- **FR-CHKOUT-05:** On checkout, the system shall call `POST /api/librarygamecheckout` with `library_id`, `librarygame_id`, and `renter_name`. If a convention is linked, `convention_id` and `badge_id` shall also be included.
- **FR-CHKOUT-06:** After a successful checkout, the system shall update the local game catalog cache to reflect the game as checked out.
- **FR-CHKOUT-07:** If the game is a Play-to-Win game (`is_play_to_win=1`), the system shall prompt the volunteer to enter players into the P2W drawing (see §4.7).

### 4.6 Game Check-In

- **FR-CHKIN-01:** The volunteer shall be able to search for a game to check in by name or catalog number.
- **FR-CHKIN-02:** The system shall show which games are currently checked out and who has them.
- **FR-CHKIN-03:** On check-in, the system shall call `POST /api/librarygamecheckout/{id}/checkin`.
- **FR-CHKIN-04:** After a successful check-in, the system shall update the local game catalog cache to reflect the game as available.
- **FR-CHKIN-05:** If the game is a Play-to-Win game, the system shall prompt the volunteer to enter players into the P2W drawing (see §4.7). The renter should be pre-suggested.

### 4.7 Play-to-Win Entry at Checkout/Check-In

- **FR-P2W-01:** When a P2W game is checked out or checked in, the system shall offer an "Enter into Drawing" prompt.
- **FR-P2W-02:** The **renter** shall always be pre-suggested as a drawing entrant.
- **FR-P2W-03:** The system shall provide **smart suggestions** for additional entrants: people who have previously been entered into P2W drawings alongside the renter (i.e., both were entered for the same game in this session).
- **FR-P2W-04:** The volunteer shall be able to add additional people manually (by badge number or name).
- **FR-P2W-05:** For each selected entrant, the system shall call `POST /api/playtowin` with `library_id`, `librarygame_id`, and `renter_name`. If a convention is linked, `convention_id` and `badge_id` shall also be included.
- **FR-P2W-06:** The system shall prevent duplicate P2W entries (same person + same game) by checking the local cache or querying `GET /api/librarygame/{id}/playtowins` before creating.
- **FR-P2W-07:** The "play group" data for smart suggestions shall be built from P2W entry history during this session — tracking which people were entered into drawings for the same game together. This is distinct from checkout overlap.

### 4.8 Game Search & Status

- **FR-SEARCH-01:** The system shall provide a game search page where a volunteer can look up any game by name or catalog number.
- **FR-SEARCH-02:** The game detail view shall show:
  - Current status (available / checked out / not in circulation)
  - If checked out: who has it and when it was checked out
  - Checkout history (recent checkouts for this game)
  - Play-to-Win entry count (if applicable)
- **FR-SEARCH-03:** Game detail data shall be fetched fresh from TTE (`GET /api/librarygame/{id}` with related objects and `GET /api/librarygame/{id}/checkouts`) to ensure accuracy.

### 4.9 Person Lookup

- **FR-PRSN-01:** The system shall provide a person search by badge number or name.
- **FR-PRSN-02:** The person detail view shall show:
  - Currently checked-out games
  - Checkout history for this session/convention
  - Play-to-Win entries
- **FR-PRSN-03:** For currently checked-out games, the system shall query `GET /api/library/{id}/checkouts?is_checked_in=0` filtered by the person's badge or name.
- **FR-PRSN-04:** For checkout history, the system shall use the local session cache supplemented by `GET /api/library/{id}/checkouts` filtered to the person.
- **FR-PRSN-05:** The person lookup shall work without requiring a full library download. It shall query TTE on demand for the specific person's data.

### 4.10 Low-Play & Low-Checkout Filters

- **FR-LOWPLAY-01:** The shared game list (§4.13) shall include P2W entry count and checkout count columns, both sortable.
- **FR-LOWPLAY-02:** The shared game list shall provide threshold filter controls that allow a volunteer to show only games with fewer than N P2W entries or fewer than N checkouts. The volunteer sets the threshold value.
- **FR-LOWPLAY-03:** These filters are additive to any existing search or sort on the game list, allowing a volunteer to quickly identify under-played games that need more attention or promotion on the convention floor.
- **FR-LOWPLAY-04:** Entry counts shall come from the cached P2W data; checkout counts shall come from the `checkout_count` field on `LibraryGame`.

### 4.11 Component Check Tracking

- **FR-COMP-01:** At the end of a convention, each game goes through a component check (verifying all pieces are present). The system shall provide a checklist to track this.
- **FR-COMP-02:** For each game, the checklist shall record: whether the component check has been completed, who performed it (volunteer name/badge), and a timestamp.
- **FR-COMP-03:** The component check status shall be stored locally in the server-side session (not pushed to TTE unless a suitable TTE field is identified). Note: on Azure Free tier, the app may restart and clear session data. The system shall persist component check progress to a local file (JSON) so it survives server restarts.
- **FR-COMP-04:** The system shall provide a summary view showing total games, how many have been checked, and how many remain.
- **FR-COMP-05:** The checklist shall support filtering to show only unchecked games.

### 4.12 Suspicious Checkout Detection

- **FR-SUSPCHK-01:** The system shall flag checkouts that exceed a smart duration threshold as potentially suspicious. The threshold for each game shall be 2× the game's maximum play time (from TTE's `max_play_time` field), with a minimum of 1 hour. If play time data is not available for a game, the default threshold shall be 4 hours. The threshold is per session (one session per convention/drawing).
- **FR-SUSPCHK-02:** The system shall detect patterns of extended checkouts across play partners — e.g., person A checks out a game for an unusually long time, then person B (a frequent co-player of A) checks out the same game for an unusually long time the next day. This may indicate collusion to keep a game out of circulation.
- **FR-SUSPCHK-03:** Suspicious checkouts shall be especially highlighted for games marked as premium (the `premium` designation used by PawDrawing for the drawing).
- **FR-SUSPCHK-04:** Suspicious checkout alerts shall appear in the notification system (see §4.14), not as intrusive pop-ups.
- **FR-SUSPCHK-05:** The game detail view (§4.8) shall show a warning flag if the game has been flagged for suspicious checkout patterns, so a volunteer can review before the drawing.

### 4.13 Shared Game List with Drawing Mode

- **FR-SHARED-01:** The game catalog loaded in Library Management mode shall be the same data structure used by Drawing mode. There shall not be separate game lists.
- **FR-SHARED-02:** Flags set during Library Management (e.g., suspicious checkout warnings) shall carry over and be visible in Drawing mode.
- **FR-SHARED-03:** Premium game designations set in Drawing mode shall be visible in Library Management mode (e.g., for suspicious checkout prioritization).

### 4.14 Notifications

- **FR-NOTIF-01:** The system shall provide a notifications tab accessible from the main navigation. A badge count shall show the number of unread notifications.
- **FR-NOTIF-02:** Notifications shall be generated for:
  - Non-P2W games detected in the library at load time (§4.3 FR-CAT-07)
  - Long-duration checkouts exceeding the configured threshold (§4.12)
  - Suspicious checkout patterns detected (§4.12)
- **FR-NOTIF-03:** Notifications shall be non-intrusive — no pop-ups or modals. Volunteers check them at their own pace via the notifications tab.
- **FR-NOTIF-04:** Each notification shall be dismissable. Dismissed notifications shall not reappear.
- **FR-NOTIF-05:** The notification volume shall be kept low to avoid overwhelming volunteers. The system shall batch related alerts (e.g., "3 games have been checked out for over 4 hours") rather than creating one notification per game.

### 4.15 Error Handling

- **FR-ERR-01:** The system shall display user-friendly error messages when API requests fail.
- **FR-ERR-02:** The system shall handle the case where a game is no longer available (checked out by someone else between search and checkout attempt) with a clear message.
- **FR-ERR-03:** The system shall handle network timeouts and offer retry options.
- **FR-ERR-04:** The system shall gracefully handle TTE rate limiting by queuing requests and showing a "please wait" indicator when the rate limit is being approached.

---

## 5. Non-Functional Requirements

- **NFR-01:** The application shall be part of the existing PawDrawing Flask application, sharing infrastructure (TTE client, auth, config, deployment).
- **NFR-02:** The user interface shall be optimized for speed on tablets and laptops used on a convention floor. Touch-friendly controls are preferred.
- **NFR-03:** The system shall support up to 5 concurrent volunteers operating on the same library simultaneously.
- **NFR-04:** API credentials shall not be exposed to the client-side browser.
- **NFR-05:** The system shall comply with TTE rate limiting (max 1 request per second). With multiple concurrent volunteers, requests shall be serialized through the server to respect this limit.
- **NFR-06:** The initial game catalog load (2–3 minutes for large libraries) shall happen once per library session. Subsequent operations shall use the cached catalog plus targeted single-game refreshes.
- **NFR-07:** Individual checkout and check-in operations shall complete within 3 seconds (excluding network latency to TTE).

---

## 6. User Roles

| Role | Description |
|---|---|
| **Library Owner** | Logs in, selects library, manages settings. Full access. |
| **Volunteer** | Performs checkouts, check-ins, P2W entries. May use owner's session or their own login. |

---

## 7. User Workflow

### 7.1 Setup

1. Library owner opens the application and logs in with TTE credentials.
2. Owner selects the mode toggle to "Library Management."
3. Owner selects a convention (to get its library) or selects a library directly.
4. System loads the P2W game catalog from TTE (loading indicator shown; 2–3 min for large libraries). If non-P2W games exist, a notification is created.
5. Owner optionally enables non-P2W game management, or uses "Mark All as P2W" if the entire library should be P2W.
6. Owner shares the app URL with volunteers (using the same session) or volunteers log in with their own credentials.

### 7.2 Checkout Flow

7. Volunteer searches for a game by name or catalog number.
8. Volunteer identifies the renter by badge number (convention) or badge + name (independent library).
9. System creates the checkout on TTE.
10. If the game is Play-to-Win:
    a. System suggests the renter for P2W entry.
    b. System suggests people who have been entered into P2W drawings with the renter.
    c. Volunteer confirms or adds/removes entrants.
    d. System creates P2W entries on TTE.

### 7.3 Check-In Flow

11. Volunteer searches for the game or looks up the person returning it.
12. System shows the active checkout for that game.
13. Volunteer confirms check-in; system calls the checkin endpoint.
14. If the game is Play-to-Win, volunteer is prompted to add P2W entries for the returning group.

### 7.4 Lookup Flows

15. **Game lookup:** Volunteer searches by name or catalog number. System shows status, current renter (if checked out), and history. Suspicious checkout flags are visible here.
16. **Person lookup:** Volunteer searches by badge number or name. System shows current checkouts and history.

### 7.5 End-of-Convention

17. **Low-play review:** Volunteer uses the threshold filters on the shared game list to surface under-played games (e.g., "show games with fewer than 3 P2W entries").
18. **Component checks:** Volunteers work through the component check checklist, marking each game as checked with their name.
19. **Drawing prep:** Suspicious checkout flags from Library Management carry into Drawing mode for review before running the drawing.

---

## 8. API Flow Diagram

```
[Volunteer Browser] --> [PawDrawing Server]
                              |
               LOGIN:         |--> POST /api/session (authenticate, get session_id)
                              |
               SETUP:         |--> GET /api/convention/{id}?_include_related_objects=library
                              |    or GET /api/library/{id}
                              |--> GET /api/library/{id}/games (full catalog, paginated)
                              |       (2-3 min for large libraries; cached server-side)
                              |
               CHECKOUT:      |--> GET /api/library/{id}/games?query=...  (search game)
                              |--> GET /api/librarygame/{id}  (fresh status for selected game)
                              |--> GET /api/convention/{id}/badges?query=...  (badge lookup)
                              |--> POST /api/librarygamecheckout  (create checkout)
                              |--> POST /api/playtowin  (P2W entry, if applicable; per entrant)
                              |
               CHECK-IN:      |--> GET /api/librarygame/{id}/checkouts?is_checked_in=0
                              |--> POST /api/librarygamecheckout/{id}/checkin
                              |--> POST /api/playtowin  (P2W entry, if applicable)
                              |
               GAME LOOKUP:   |--> GET /api/librarygame/{id}
                              |--> GET /api/librarygame/{id}/checkouts
                              |
               PERSON LOOKUP: |--> GET /api/library/{id}/checkouts?query=...
                              |    or GET /api/convention/{id}/badges?query=...
                              |
               LOGOUT:        |--> DELETE /api/session/{id}
```

---

## 9. Concurrency Design

### 9.1 Shared Session Model (Owner Login)

- All volunteers share the same server-side session and TTE `session_id`.
- The game catalog cache is stored once in the server session and read by all connected browsers.
- TTE API calls are serialized through the server's rate limiter (1 req/sec) regardless of which volunteer triggered them.
- Checkout/check-in operations use optimistic concurrency: if TTE rejects an operation (e.g., game already checked out), the system refreshes the game status and reports the conflict.

### 9.2 Individual Login Model (Volunteer Login)

- Each volunteer has their own TTE session.
- The game catalog cache is still shared (stored by library ID, not by user session).
- Rate limiting applies per TTE API key. Since all users share the same application API key, the 1 req/sec limit is global. The server serializes all TTE requests regardless of which volunteer session initiated them.

---

## 10. Smart Suggestion Algorithm

### 10.1 Play Group Detection

The system builds a "play group" model from P2W entry history during the session:
1. When person A and person B are both entered into the P2W drawing for the same game, record an association between A and B.
2. Over time, people who frequently appear in the same P2W entries build stronger associations.
3. When entering P2W entries for a new game checked out by person A, suggest people with the strongest drawing co-entry associations with A.

### 10.2 Suggestion Priority

When suggesting P2W entrants at checkout/check-in time:
1. **Always suggest:** The renter (auto-selected).
2. **Strongly suggest:** People who were most recently entered into a P2W drawing with the renter.
3. **Also suggest:** Other people who have been entered into any P2W drawing alongside the renter during this session, ranked by frequency.

---

## 11. Assumptions

1. The TTE API will remain stable and accessible during use of this application.
2. The library owner's TTE account has sufficient privileges to create and manage checkouts.
3. The TTE rate limit of 1 request per second is global per API key, not per session. The server must serialize all requests.
4. Volunteer Login mode requires each volunteer to have a TTE account. The library owner must grant them `LibraryPrivilege` with `checkouts=1` on the library in advance.
5. The game catalog cache is adequate for search/display purposes. Individual game status is refreshed from TTE before any checkout or check-in operation to avoid stale data.
6. For independent libraries without badge data, the person identification relies on manually entered badge numbers and names; the system does not validate these against TTE.
7. The "smart suggestions" for P2W entries are session-local — they do not persist across server restarts or library changes.
8. Component check tracking is local to the session and is not written back to TTE.
9. Only Play-to-Win games are managed by default. Non-P2W game checkout management is opt-in.

---

## 12. Resolved Questions

1. **Checkout time adjustment:** Yes — the UI shall support correcting checkout duration via `POST /api/librarygamecheckout/{id}/reset-checkout-time`. The UI should make this simple: on the game detail or checkout history view, a volunteer can tap a checkout and adjust the end time. A note field explains why.
2. **Offline resilience:** Yes — the system shall queue checkout/check-in operations locally when TTE is unreachable and sync when connectivity returns. The UI shall clearly warn that it is operating offline and suggest the volunteer also track manually as a backup.
3. **Game weight tracking:** Not at this time. May revisit in a future version.
4. **Notifications:** Yes — implemented as a non-intrusive notifications tab with a badge count (see §4.14). No pop-ups. Batched to keep volume low.
5. **Suspicious checkout thresholds:** Smart thresholds — 2× the game's max play time (from TTE `max_play_time` field), with a 1-hour minimum. Falls back to 4 hours if play time data is unavailable. Applied per session (one session per convention/drawing).
6. **Component check persistence:** Session loss is possible on Azure Free tier (app restarts clear server-side sessions). The system persists component check progress to a local JSON file so it survives restarts. CSV export is not needed at this time.
7. **Mark All as P2W scope:** Only in-circulation games (`is_in_circulation=1`). The non-P2W notification shall be expandable to show the game list.

---

## 13. Open Questions

No open questions at this time.