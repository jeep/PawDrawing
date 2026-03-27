"""Library-scoped shared state that persists across browser sessions.

Stores data that must be visible to all devices working with the same
library: ejections, notifications, settings, person cache, play groups.

Each library gets a separate JSON file in the shared state directory.
File locking ensures safe concurrent access from multiple workers.
"""

import fcntl
import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_shared_dir = os.environ.get("SHARED_STATE_DIR", "shared_state")


def _state_path(library_id: str) -> Path:
    """Return the file path for a library's shared state."""
    safe_id = "".join(c if c.isalnum() or c == "-" else "_" for c in library_id)
    return Path(_shared_dir) / f"{safe_id}.json"


def _lock_path(library_id: str) -> Path:
    """Return a lock file path for atomic read-modify-write."""
    safe_id = "".join(c if c.isalnum() or c == "-" else "_" for c in library_id)
    return Path(_shared_dir) / f"{safe_id}.lock"


def init_dir():
    """Create the shared state directory if it doesn't exist."""
    Path(_shared_dir).mkdir(parents=True, exist_ok=True)


def load(library_id: str) -> dict:
    """Load the full shared state for a library.

    Returns an empty dict if the file doesn't exist or is corrupt.
    """
    path = _state_path(library_id)
    if not path.exists():
        return {}
    try:
        with open(path, "r") as f:
            fcntl.flock(f, fcntl.LOCK_SH)
            try:
                return json.load(f)
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Could not load shared state for %s: %s", library_id, exc)
        return {}


def save(library_id: str, state: dict) -> None:
    """Save the full shared state for a library (replaces entire file)."""
    path = _state_path(library_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = _lock_path(library_id)
    with open(lock, "w") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        try:
            with open(path, "w") as f:
                json.dump(state, f, default=str)
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)


def update(library_id: str, key: str, value) -> None:
    """Atomically set a single key in the shared state file.

    Uses file locking to prevent concurrent-write corruption.
    """
    path = _state_path(library_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = _lock_path(library_id)
    with open(lock, "w") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        try:
            state = {}
            if path.exists():
                try:
                    with open(path, "r") as f:
                        state = json.load(f)
                except (json.JSONDecodeError, OSError):
                    state = {}
            state[key] = value
            with open(path, "w") as f:
                json.dump(state, f, default=str)
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)


def merge_dict(library_id: str, key: str, updates: dict) -> None:
    """Atomically merge a dict into a shared state key.

    Useful for person_cache and play_groups where multiple devices
    may add entries concurrently.  Existing keys in the stored dict
    are preserved; ``updates`` keys overwrite on collision.
    """
    path = _state_path(library_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = _lock_path(library_id)
    with open(lock, "w") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        try:
            state = {}
            if path.exists():
                try:
                    with open(path, "r") as f:
                        state = json.load(f)
                except (json.JSONDecodeError, OSError):
                    state = {}
            existing = state.get(key, {})
            existing.update(updates)
            state[key] = existing
            with open(path, "w") as f:
                json.dump(state, f, default=str)
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)


def delete(library_id: str) -> None:
    """Delete the shared state file for a library."""
    for path in (_state_path(library_id), _lock_path(library_id)):
        try:
            path.unlink()
        except FileNotFoundError:
            pass
