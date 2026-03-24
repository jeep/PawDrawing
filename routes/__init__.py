from flask import Blueprint

main_bp = Blueprint("main", __name__)

# Import route modules so they register their @main_bp routes.
from . import auth, convention, drawing, drawing_actions, games  # noqa: E402, F401
