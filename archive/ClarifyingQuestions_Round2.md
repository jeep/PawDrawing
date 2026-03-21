# PawDrawing — Follow-Up Questions (Round 2)

Based on your answers, a few things need clarification. Please answer on the lines after "**Answer:**".

---

## Picked Up / Redistribution Workflow (from Q8)

### Q19: Picked Up Tracking
When the admin marks a game as "picked up," should that status also be written back to TTE (e.g., updating the PlayToWin `win` field), or is it tracked only within PawDrawing?

**Answer:**
track it locally, but allow the admin to push it back to tte. Maybe as a cleanup step at the end "push picked up games to tte"?

### Q20: Redistribution — One-Win Rule
When redistributing unclaimed games, does the "one win per person" rule still apply? For example, if Person A already won and picked up Game X, can they also win an unclaimed Game Y during redistribution?

**Answer:**
No, for the second chance drawing it will be given to the top person in the list who is in attendance

### Q21: Redistribution — Admin Choice
When the admin clicks an unclaimed game to redistribute, the full shuffled list is shown. Can the admin pick *anyone* from that list as the new winner, or should they always go to the next person in order?

**Answer:**
they should always start at the top and work down until someone claims it or all who played it are not there

### Q22: Redistribution — Timing
When does redistribution happen?
- (a) At the convention, as games go unclaimed during pickup (one at a time, over hours/days)
- (b) In a single batch session after a pickup deadline has passed
- (c) Either

**Answer:**
In a single batch after the pickup deadline

---

## Data Clarifications

### Q23: Missing Badge ID
You said entries should be matched by `badge_id`. What if some PlayToWin entries have no `badge_id` (it's nullable in TTE)? Should those entries be:
- (a) Excluded from the drawing entirely
- (b) Included but treated as separate/unique entrants (no de-duplication possible)
- (c) Something else

**Answer:**
a

### Q24: De-duplication Confirmation
You said each person gets only one entry per game regardless of play count. The TTE API may return multiple PlayToWin entries for the same person + same game. Should the app:
- (a) De-duplicate on load (keep only one entry per badge_id per game)
- (b) Count them as one during the drawing but show the original play count somewhere

**Answer:**
a

### Q25: Results Save Location
You said "locally, but with an option to save results." Does this mean:
- (a) Results are shown in the browser during the session, and there's a "Save" button to export/download (CSV per Q11)
- (b) Results are auto-saved to a file/database on the server, and can be reloaded on next visit
- (c) Both

**Answer:**
a

---

### Q26: Convention ID Entry
You said convention_id should be "entered." Should this be:
- (a) A text field where the admin pastes a convention ID
- (b) Part of the convention search/select flow (search by name, then the app uses the selected convention's ID)
- (c) Both options available

**Answer:**
c

---

*After these are answered, I'll finalize the requirements document.*
