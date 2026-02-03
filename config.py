import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    API_ID = int(os.getenv("API_ID", "0"))
    API_HASH = os.getenv("API_HASH", "")
    BOT_TOKEN = os.getenv("BOT_TOKEN", "")
    MONGO_URI = os.getenv("MONGO_URI", "")
    ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

    # Default Configs (fallback if DB empty)
    DEFAULT_DELAY = 0  # No delay as per clarification
    TASKS_PER_REQUEST = 3
    RATE_LIMIT_BUNDLES = 3
    RATE_LIMIT_WINDOW = 2 * 60 * 60  # 2 hours in seconds

    # Force Sub
    FORCE_SUB_MODE = "ANY" # ANY or ALL

    # Bot Username (will be set on startup)
    BOT_USERNAME = ""
