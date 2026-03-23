# PawDrawing

A web application for managing Play-to-Win drawings at tabletop gaming conventions. Integrates with the [tabletop.events](https://tabletop.events) API.

## Setup

### Prerequisites

- Python 3.12+

### Installation

```bash
# Clone the repo
git clone git@github.com:jeep/PawDrawing.git
cd PawDrawing

# Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r Requirements.txt
```

### Configuration

```bash
# Copy the example env file
cp .env.example .env
```

Edit `.env` and set:
- `FLASK_SECRET_KEY` — a random string for session security
- `TTE_API_KEY` — your tabletop.events API key

### Git Hooks

Enable the conventional commit hook:

```bash
git config core.hooksPath .githooks
```

### Run

```bash
python run.py
```

The app will be available at `http://localhost:5000`.

## Documentation

- [Administrator Guide](docs/ADMIN.md) — installation, workflow, and troubleshooting
- [Developer Guide](docs/DEVELOPER.md) — architecture, module reference, and testing

## Project Structure

```
PawDrawing/
├── app.py                  # Flask app factory
├── config.py               # Configuration (reads from .env)
├── run.py                  # Dev server entry point
├── routes.py               # All Flask routes (Blueprint)
├── tte_client.py           # TTE API client with rate limiting & pagination
├── drawing.py              # Drawing algorithm (shuffle, conflicts, resolution)
├── data_processing.py      # Entry validation, de-duplication, grouping
├── Requirements.txt        # Python dependencies
├── .env.example            # Environment variable template
├── .githooks/
│   └── commit-msg          # Conventional Commits hook
├── templates/
│   ├── base.html               # Base layout with flash messages & loading overlay
│   ├── login.html              # Login form
│   ├── convention_select.html  # Convention search & library browse
│   ├── convention_confirm.html # Confirm selected convention
│   ├── library_confirm.html    # Confirm selected library (no convention)
│   ├── games.html              # Game list with premium toggles, sorting & search
│   ├── players.html            # Player management with remove/restore controls
│   └── drawing_results.html    # Results with conflicts, pickup, push, export
├── tests/
│   ├── test_routes.py          # Route/view tests
│   ├── test_tte_client.py      # API client tests
│   ├── test_drawing.py         # Drawing algorithm tests
│   └── test_data_processing.py # Data processing tests
└── docs/
    ├── ADMIN.md            # Administrator guide
    ├── DEVELOPER.md        # Developer & architecture guide
    └── Requirements.md     # Project requirements document
```
