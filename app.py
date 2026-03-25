import logging
import os
import time

from flask import Flask
from flask_session import Session
from flask_wtf import CSRFProtect

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

    from routes import main_bp
    from routes.library import library_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(library_bp)

    _cleanup_old_sessions(app)

    return app
