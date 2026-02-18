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
    # Append TLS settings to fix SSL handshake issues on some providers
    # Note: 'ssl_cert_reqs' is not valid in URI for newer pymongo, only 'tlsAllowInvalidCertificates'
    if MAIN_URI and "?" not in MAIN_URI:
        MAIN_URI += "?tlsAllowInvalidCertificates=true"
    elif MAIN_URI and "tlsAllowInvalidCertificates" not in MAIN_URI:
        MAIN_URI += "&tlsAllowInvalidCertificates=true"

    # UserDB (Shared Read-Write Users)
    USER_URI = os.getenv("USER_URI", MAIN_URI)

    # PrivateDB (Local Franchisee Data/Cache)
    PRIVATE_URI = os.getenv("PRIVATE_URI", MAIN_URI)

    # Identities
    CEO_ID = int(os.getenv("CEO_ID", "0"))
    ADMIN_ID = int(os.getenv("ADMIN_ID", "0")) # Legacy

    # Admins List
    # Robust parsing: split by comma, strip whitespace, filter digits, convert to int
    ADMIN_IDS = set()
    raw_admins = os.getenv("ADMIN_IDS", "")
    for x in raw_admins.split(","):
        x = x.strip()
        if x.isdigit():
            ADMIN_IDS.add(int(x))

    if ADMIN_ID:
        ADMIN_IDS.add(ADMIN_ID)
    if CEO_ID:
        ADMIN_IDS.add(CEO_ID)

    TMDB_API_KEY = os.getenv("TMDB_API_KEY", "")

    # Franchise Info (New v2.0.0)
    FRANCHISEE_ID = os.getenv("FRANCHISEE_ID", "")
    FRANCHISEE_PASSWORD = os.getenv("FRANCHISEE_PASSWORD", "")

    # Channels
    CEO_CHANNEL_ID = int(os.getenv("CEO_CHANNEL_ID", "0"))

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
    BOT_VERSION = "2.0.0"

    # Start Time
    START_TIME = None
