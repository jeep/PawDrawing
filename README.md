# PawDrawing

A web application for managing Play-and-Win drawings at tabletop gaming conventions. Integrates with the [tabletop.events](https://tabletop.events) API.

## Setup

### Prerequisites

- Python 3.10+

### Installation

```bash
# Clone the repo
git clone git@github.com:jeep/PawDrawing.git
cd PawDrawing

# Create a virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
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

## Project Structure

```
PawDrawing/
├── app.py              # Flask app factory
├── config.py           # Configuration (reads from .env)
├── routes.py           # Route handlers
├── run.py              # Entry point
├── requirements.txt    # Python dependencies
├── templates/          # Jinja2 HTML templates
│   ├── base.html       # Base layout
│   └── index.html      # Home page
├── .env.example        # Environment variable template
├── .gitignore
├── Requirements.md     # Project requirements document
└── README.md
```
