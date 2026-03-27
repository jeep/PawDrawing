from flask import Blueprint

library_bp = Blueprint("library", __name__, url_prefix="/library-mgmt")

# Import route modules so they register their @library_bp routes.
from . import checkout, component_checks, dashboard, game_list, lookup, volunteer  # noqa: E402, F401
