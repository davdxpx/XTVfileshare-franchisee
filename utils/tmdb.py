import aiohttp
from config import Config
from log import get_logger

logger = get_logger(__name__)

TMDB_BASE_URL = "https://api.themoviedb.org/3"

async def search_tmdb(query, media_type="movie"):
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
        "language": "en-US",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=10) as response:
                response.raise_for_status()
                data = await response.json()
                return data.get("results", [])
    except Exception as e:
        logger.error(f"TMDb Search Error: {e}")
        return []

async def get_tmdb_details(tmdb_id, media_type="movie"):
    if not Config.TMDB_API_KEY:
        return None

    url = f"{TMDB_BASE_URL}/{media_type}/{tmdb_id}"
    params = {
        "api_key": Config.TMDB_API_KEY,
        "language": "en-US"
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=10) as response:
                response.raise_for_status()
                return await response.json()
    except Exception as e:
        logger.error(f"TMDb Details Error: {e}")
        return None
