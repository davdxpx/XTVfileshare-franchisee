import requests
from config import Config
from log import get_logger

logger = get_logger(__name__)

TMDB_BASE_URL = "https://api.themoviedb.org/3"

def search_tmdb(query, media_type="movie"):
    """
    Search TMDb for movies or tv shows.
    media_type: 'movie' or 'tv'
    """
    if not Config.TMDB_API_KEY:
        logger.warning("TMDb API Key missing.")
        return []

    url = f"{TMDB_BASE_URL}/search/{media_type}"
    params = {
        "api_key": Config.TMDB_API_KEY,
        "query": query,
        "language": "en-US", # Or make configurable? User prompts were in German/English mix.
                             # Let's default to English for global, or German if requested.
                             # User input "The Rookie (2018)" suggests original titles often used.
                             # Keeping en-US is standard, but maybe 'de-DE' if description should be german.
                             # User said: "Description... <hier kommt die Beschreibung rein>"
                             # Let's stick to en-US for now or de-DE if user wants German.
                             # I'll use 'en-US' as default.
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        return data.get("results", [])
    except Exception as e:
        logger.error(f"TMDb Search Error: {e}")
        return []

def get_tmdb_details(tmdb_id, media_type="movie"):
    if not Config.TMDB_API_KEY:
        return None

    url = f"{TMDB_BASE_URL}/{media_type}/{tmdb_id}"
    params = {
        "api_key": Config.TMDB_API_KEY,
        "language": "en-US" # Fetching description
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"TMDb Details Error: {e}")
        return None
