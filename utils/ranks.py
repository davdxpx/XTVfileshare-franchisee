from datetime import datetime, timezone

# Request Ranks (Based on Total Requests)
REQUEST_RANKS = [
    (0, "Newbie"),
    (21, "Movie Enthusiast"),
    (81, "Series Addict"),
    (201, "Top Requester"),
    (401, "Elite Requester"),
    (701, "Legend Requester"),
    (1201, "Request God")
]

# Fileshare Ranks (Based on XP)
FILESHARE_RANKS = [
    (0, "Newbie"),
    (101, "Content Explorer"),
    (401, "Bundle Master"),
    (1001, "Top Sharer"),
    (2501, "Elite Sharer"),
    (5001, "Legend Sharer"),
    (10001, "XTV Legend")
]

def get_rank_info(value, rank_list):
    """
    Returns a dictionary with rank details:
    {
        "current_rank": str,
        "next_rank": str or None,
        "current_threshold": int,
        "next_threshold": int or None,
        "progress_percent": int,
        "progress_value": int,  # value - current_threshold
        "range_value": int      # next_threshold - current_threshold
    }
    """
    current_rank_name = rank_list[0][1]
    current_threshold = rank_list[0][0]
    next_rank_name = None
    next_threshold = None

    # Iterate to find the highest threshold <= value
    for i, (threshold, name) in enumerate(rank_list):
        if value >= threshold:
            current_rank_name = name
            current_threshold = threshold
            if i + 1 < len(rank_list):
                next_rank_name = rank_list[i+1][1]
                next_threshold = rank_list[i+1][0]
            else:
                next_rank_name = None
                next_threshold = None
        else:
            # We found a threshold > value, so the previous one was correct.
            break

    # Calculate Progress
    if next_threshold is None:
        progress_percent = 100
        progress_value = 0
        range_value = 0
    else:
        range_value = next_threshold - current_threshold
        progress_value = value - current_threshold
        progress_percent = int((progress_value / range_value) * 100)

    return {
        "current_rank": current_rank_name,
        "next_rank": next_rank_name,
        "current_threshold": current_threshold,
        "next_threshold": next_threshold,
        "progress_percent": progress_percent,
        "progress_value": progress_value,
        "range_value": range_value
    }

def get_badges(joined_at, user_count_index=None):
    """
    Returns a list of badge names based on join date and user count index.
    joined_at: timestamp (float/int)
    user_count_index: integer (1-based index of user in DB) or None
    """
    badges = []

    if not joined_at:
        return badges

    # Deadlines
    dt_mar = datetime(2026, 3, 1, tzinfo=timezone.utc).timestamp()
    dt_feb = datetime(2026, 2, 1, tzinfo=timezone.utc).timestamp()

    # Logic: OG (Joined before Feb) implies Pioneer (Joined before Mar),
    # but usually we show the best one.
    # Prompt says: "Pioneer (joined before March 2026)", "OG (joined before Feb 2026)"
    # I will assume they are mutually exclusive tiers for display purposes.
    if joined_at < dt_feb:
        badges.append("OG")
    elif joined_at < dt_mar:
        badges.append("Pioneer")

    # Early Adopter (First 100 users)
    # user_count_index should be passed if known.
    if user_count_index is not None and user_count_index <= 100:
        badges.append("Early Adopter")

    return badges

BADGE_ICONS = {
    "Pioneer": "🚀",
    "OG": "👑",
    "Early Adopter": "💎"
}

def format_progress_bar(percent, length=10):
    filled = int((percent / 100) * length)
    bar = "█" * filled + "░" * (length - filled)
    return bar
