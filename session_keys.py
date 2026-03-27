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
    MANUAL_ENTRY_IDS = "manual_entry_ids"  # list[str] of P2W entry IDs manually added in app

    DRAWING_STATE = "drawing_state"
    DRAWING_CONFLICTS = "drawing_conflicts"
    DRAWING_TIMESTAMP = "drawing_timestamp"
    AUTO_RESOLVED = "auto_resolved"

    PREMIUM_GAMES = "premium_games"
    EJECTED_ENTRIES = "ejected_entries"

    PICKED_UP = "picked_up"
    NOT_HERE = "not_here"
    NOT_HERE_WARNING_DISMISSED = "not_here_warning_dismissed"

    # ── Library Management Mode ────────────────────────────────────────
    APP_MODE = "app_mode"  # "management", "players", "prep", or "drawing"
    AUTH_MODE = "auth_mode"  # "owner" or "volunteer"

    # Volunteer login
    VOLUNTEER_NAME = "volunteer_name"  # display name for current volunteer
    HAS_CHECKOUT_PRIVILEGE = "has_checkout_privilege"  # cached privilege check

    # Person identification
    PERSON_CACHE = "person_cache"  # {badge_number: {name, badge_id, user_id}}

    # Checkout tracking
    CHECKOUT_CACHE = "checkout_cache"  # list of active checkouts
    CHECKOUT_MAP = "checkout_map"  # shared: {game_id: {renter, checkout_id} | null}

    # P2W play group tracking
    PLAY_GROUPS = "play_groups"  # {person_key: [co-entrant keys]}

    # Notifications
    NOTIFICATIONS = "notifications"  # [{id, type, message, dismissed, timestamp, details}]

    # Component check tracking
    COMPONENT_CHECKS = "component_checks"  # {game_id: {checked, volunteer, timestamp}}

    # Drawing prep tracking
    PREP_COMPLETED = "prep_completed"  # bool — whether Drawing Prep has been visited
    TTE_REFRESHED = "tte_refreshed"  # bool — whether TTE data was refreshed in this session

    # Library management settings
    LIBRARY_SETTINGS = "library_settings"  # {include_non_p2w: bool, ...}
