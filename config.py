import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    API_ID = int(os.getenv("API_ID", "0"))
    API_HASH = os.getenv("API_HASH", "")
    BOT_TOKEN = os.getenv("BOT_TOKEN", "")

    # 3-DB Architecture Preparation
    # MainDB (Read-Only Global Content)
    MAIN_URI = os.getenv("MAIN_URI", os.getenv("MONGO_URI", ""))

    # UserDB (Shared Read-Write Users)
    USER_URI = os.getenv("USER_URI", MAIN_URI)

    # PrivateDB (Local Franchisee Data/Cache)
    PRIVATE_URI = os.getenv("PRIVATE_URI", MAIN_URI)

    # Identities
    CEO_ID = int(os.getenv("CEO_ID", "0"))
    ADMIN_ID = int(os.getenv("ADMIN_ID", "0")) # Legacy

    # Admins List
    ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()}
    if ADMIN_ID:
        ADMIN_IDS.add(ADMIN_ID)
    if CEO_ID:
        ADMIN_IDS.add(CEO_ID)

    TMDB_API_KEY = os.getenv("TMDB_API_KEY", "")

    # Channels
    BACKUP_CHANNEL_ID = int(os.getenv("BACKUP_CHANNEL_ID", "0"))

    # Default Configs (fallback if DB empty)
    DEFAULT_DELAY = 0  # No delay as per clarification
    TASKS_PER_REQUEST = 3
    RATE_LIMIT_BUNDLES = 3
    RATE_LIMIT_WINDOW = 2 * 60 * 60  # 2 hours in seconds

    # Force Sub
    FORCE_SUB_MODE = "ANY" # ANY or ALL

    # Bot Username (will be set on startup)
    BOT_USERNAME = ""

    # Bot Version
    BOT_VERSION = "1.8.0"

    # Start Time
    START_TIME = None
