import logging
import os
import time

from flask import Flask, flash, redirect, request, session, url_for
from flask_session import Session
from flask_wtf import CSRFProtect
from flask_wtf.csrf import CSRFError

from config import Config

logger = logging.getLogger(__name__)
csrf = CSRFProtect()


def _cleanup_old_sessions(app):
    """Delete session files older than PERMANENT_SESSION_LIFETIME."""
    session_dir = app.config.get("SESSION_FILE_DIR",
                                 os.environ.get("SESSION_FILE_DIR", "flask_session"))
    if not os.path.isdir(session_dir):
        return
    max_age = app.config["PERMANENT_SESSION_LIFETIME"].total_seconds()
    cutoff = time.time() - max_age
    removed = 0
    for name in os.listdir(session_dir):
        path = os.path.join(session_dir, name)
        try:
            if os.path.getmtime(path) < cutoff:
                os.remove(path)
                removed += 1
        except OSError:
            pass
    if removed:
        logger.info("Cleaned up %d expired session files from %s", removed, session_dir)


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    Session(app)
    csrf.init_app(app)

    @app.errorhandler(CSRFError)
    def handle_csrf_error(err):
        logger.warning("CSRF validation failed on %s: %s", request.path, err.description)
        session.clear()
        flash("Your browser session expired. Please log in again.", "error")
        return redirect(url_for("main.login"))

    # Initialize shared state directory
    import shared_state
    shared_state._shared_dir = app.config.get("SHARED_STATE_DIR", "shared_state")
    shared_state.init_dir()

    from routes import main_bp

    app.register_blueprint(main_bp)

    _cleanup_old_sessions(app)

    return app
