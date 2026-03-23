# PawDrawing

A web application for managing Play-to-Win drawings at tabletop gaming conventions. Integrates with the [tabletop.events](https://tabletop.events) API.

## Live App

> https://pawdrawing.azurewebsites.net

Log in with your tabletop.events credentials to get started.

## What It Does

1. **Pull convention data** — select a convention or library from tabletop.events and load all Play-to-Win games and entries.
2. **Manage players** — optionally remove players from the drawing before running it.
3. **Run a fair drawing** — randomly shuffles entries, picks winners, and detects one-person-winning-multiple-games conflicts.
4. **Resolve conflicts** — auto-resolves premium game priority; manually resolve the rest.
5. **Track pickups** — mark games as picked up as winners claim their prizes.
6. **Redraw unclaimed** — re-draw any games that haven't been picked up, with original winners deprioritized.
7. **Push results** — write winning entries back to tabletop.events.
8. **Export CSV** — download a spreadsheet of the results.

For the full workflow walkthrough, see the [User Guide](docs/USER_GUIDE.md).

## Documentation

- [User Guide](docs/USER_GUIDE.md) — workflow, features, and troubleshooting
- [Developer Guide](docs/DEVELOPER.md) — setup, architecture, testing, and deployment
