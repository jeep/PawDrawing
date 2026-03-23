import os

from cachelib import FileSystemCache
from dotenv import load_dotenv

load_dotenv()

_session_dir = os.environ.get("SESSION_FILE_DIR", "flask_session")


class Config:
    SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "dev-key-change-me")
    TTE_API_KEY = os.environ.get("TTE_API_KEY", "")
    TTE_BASE_URL = "https://tabletop.events/api"
    SESSION_TYPE = "cachelib"
    SESSION_CACHELIB = FileSystemCache(cache_dir=_session_dir, threshold=0)
