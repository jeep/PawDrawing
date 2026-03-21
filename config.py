import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "dev-key-change-me")
    TTE_API_KEY = os.environ.get("TTE_API_KEY", "")
    TTE_BASE_URL = "https://tabletop.events/api"
