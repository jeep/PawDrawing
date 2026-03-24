"""Constants for Flask session keys used throughout the application."""


class SK:
    TTE_SESSION_ID = "tte_session_id"
    TTE_USERNAME = "tte_username"
    TTE_USER_ID = "tte_user_id"
    TTE_API_KEY = "tte_api_key"

    CONVENTION_ID = "convention_id"
    CONVENTION_NAME = "convention_name"
    LIBRARY_ID = "library_id"
    LIBRARY_NAME = "library_name"

    CACHED_GAMES = "cached_games"
    CACHED_ENTRIES = "cached_entries"

    DRAWING_STATE = "drawing_state"
    DRAWING_CONFLICTS = "drawing_conflicts"
    DRAWING_TIMESTAMP = "drawing_timestamp"
    AUTO_RESOLVED = "auto_resolved"

    PREMIUM_GAMES = "premium_games"
    EJECTED_ENTRIES = "ejected_entries"

    PICKED_UP = "picked_up"
    NOT_HERE = "not_here"
    NOT_HERE_WARNING_DISMISSED = "not_here_warning_dismissed"
    SOLO_DISMISSED_GAMES = "solo_dismissed_games"
