from flask import Blueprint

library_bp = Blueprint("library", __name__, url_prefix="/library-mgmt")

# Import route modules so they register their @library_bp routes.
from . import dashboard, checkout, lookup, component_checks, game_list  # noqa: E402, F401
