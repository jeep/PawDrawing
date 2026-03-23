from flask import Flask
from flask_session import Session

from config import Config


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    Session(app)

    from routes import main_bp

    app.register_blueprint(main_bp)

    return app
