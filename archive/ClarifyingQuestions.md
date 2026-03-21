# PawDrawing — Clarifying Questions

Please answer each question below. Type your answer on the line(s) after "**Answer:**".

---

## Authentication & Access

### Q1: TTE Login Credentials
The API requires a `username` and `password` (plus the API key) to create an authenticated session. Should the app:
- (a) Have a login screen where the admin enters their TTE credentials each time?
- (b) Use pre-configured credentials stored in a config/env file on the server?

**Answer:**
a

### Q2: Convention Identification
Do you have a specific convention ID you'll always use, or should the app let you search/select from available conventions?

**Answer:**
Let the app search

### Q3: Library
Is the library always the one associated with the convention (via the convention's `library` related object), or might you need to specify a different library?

**Answer:**
It should always be associated with the convention

---

## Drawing Logic

### Q4: Entrant Identity Matching
When detecting if one person won multiple games, how should entrants be matched?
- (a) By `user_id` (TTE account — most reliable, but may not always be present)
- (b) By `name` field (string matching — could have typos/variants)
- (c) By `badge_id` (convention badge)
- (d) Some combination?

**Answer:**
badge id

### Q5: Premium Game Designation
How should "premium" games be identified?
- (a) Manually selected by the admin in the app's UI before each drawing
- (b) Based on a field/tag in the TTE data (if so, which field?)
- (c) From a pre-configured list (file or database)

**Answer:**
a

### Q6: Randomization Seed
Should the randomization be reproducible (i.e., save a seed so the same shuffle can be recreated for auditing), or is a one-time random shuffle sufficient?

**Answer:**
a one time shuffle is sufficient

### Q7: Multiple Drawings
Can the drawing be run multiple times for the same convention (e.g., re-run if there's an issue), or is it a one-time event?

**Answer:**
the admin can rerun if there is an issue

### Q8: Write Results Back to TTE
After the drawing is complete, should the app update the `win` field on PlayToWin entries in TTE (via `PUT /api/playtowin/{id}`)? Or are results only displayed/exported locally?

**Answer:**
It should display locally, then give the admin the option to update the win fields as the games are picked up. I.e. there is a new requirement to allow the admin to mark a game which has been not only won, but picked up by the user.

Additionally, there should be an option to distribute the games that have not been picked up. the admin should be given the choice to redraw the games that have not been picked up. The redraw will simply be the initial randomly generated list. I.e. the admin will click the game that was not picked up, and the list will be displayed. 

---

## Data & Display

### Q9: Games with Zero Entries
How should games with zero Play-to-Win entries be handled?
- (a) Show them in results as "No entries"
- (b) Hide them entirely
- (c) Show a warning

**Answer:**
a

### Q10: Results Persistence
Should drawing results be saved locally (e.g., to a file or database) so they can be reviewed later, or is a live browser-only view sufficient?

**Answer:**
locally, but with an option to save results

### Q11: Export Format
Do you need to export results to any particular format (e.g., CSV, PDF, printable page)?

**Answer:**
export to CSV

### Q12: Number of Entries Display
When showing "number of entries" per game, should this be a count of unique entrants, or total entries (if a person can enter the same game multiple times)?

**Answer:**
count of unique entrants. and to be clear, no matter how many times the entrant played the game, they only get one entry

---

## Application Architecture

### Q13: Web Framework Preference
Do you have a preference for the web framework? Some options:
- (a) Python/Flask (lightweight, easy to set up)
- (b) Python/Django (more batteries included)
- (c) Node.js/Express (JavaScript based)
- (d) No preference — choose what's best

**Answer:**
d

### Q14: Deployment Environment
Where will this app run?
- (a) Locally on your laptop only (during the convention)
- (b) On a hosted server (e.g., cloud VM, Heroku, etc.)
- (c) Either — should support both

**Answer:**
c

### Q15: Multiple Admins
Will only one person run the drawing at a time, or could multiple administrators use the app simultaneously?

**Answer:**
only one at a time

---

## Edge Cases

### Q16: Tie-Breaking for Non-Premium Conflicts
If after automatic premium assignment, a person still wins multiple non-premium games, and they keep choosing — is there a limit to how many rounds of conflict resolution the admin expects? Or should the system just keep iterating until resolved?

**Answer:**
iterate until resolved. 

### Q17: Entrant Disqualification
Is there ever a need to disqualify or exclude specific entrants from the drawing (e.g., staff, sponsors)?

**Answer:**
No

### Q18: Convention Scope for PlayToWin Entries
PlayToWin entries have an optional `convention_id`. Should the app only include entries matching the selected convention, or all entries for the library regardless of convention?

**Answer:**
we should allow a convention_id to be entered and if provided limit to that convention, otherwise unlimited

---

*Once these questions are answered, the Requirements.md document will be updated accordingly.*
