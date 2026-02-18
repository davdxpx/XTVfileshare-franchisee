
# Stores pending series channel setups
# Key: chat_id (int) or username (str)
# Value: {
#   "tmdb_id": int,
#   "media_type": str,
#   "user_id": int,
#   "timestamp": float
# }
pending_series_setups = {}

# Stores the state of the "Add Series Channel" wizard for each user
# Key: user_id (int)
# Value: {
#   "state": str, # e.g., "wait_series_search", "wait_series_select", "wait_channel_id"
#   "data": dict  # Temporary data like search results, selected tmdb_id
# }
series_wizard_states = {}
