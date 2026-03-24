from flask import Flask
from flask_session import Session
from flask_wtf import CSRFProtect

from config import Config

csrf = CSRFProtect()


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    Session(app)
    csrf.init_app(app)

    from routes import main_bp

    app.register_blueprint(main_bp)

    return app
