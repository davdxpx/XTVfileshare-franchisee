import asyncio
import time
from db import db
from config import Config
from log import get_logger

logger = get_logger(__name__)

async def sync_from_main():
    """
    Syncs essential read-only data from MainDB to PrivateDB (Local Cache)
    to ensure availability even if MainDB goes down temporarily.

    Syncs:
    - Force Sub Channels
    - Shared Bundles (optional, depending on scale)
    - Groups
    """
    if Config.MAIN_URI == Config.PRIVATE_URI:
        return # Standalone mode, no sync needed

    logger.info("Starting Sync Job: MainDB -> PrivateDB")
    start_time = time.time()

    try:
        # 1. Sync Force Sub Channels
        # Fetch from Main directly
        main_channels = await db.channels_col_main.find({"approved": True, "type": "force_sub"}).to_list(length=1000)

        synced_channels = 0
        for ch in main_channels:
            # Sync to dedicated Cache Collection

            # Prepare doc (exclude _id)
            doc = {k:v for k,v in ch.items() if k != "_id"}
            doc["is_synced"] = True
            doc["last_synced"] = time.time()

            await db.cache_channels_col.update_one(
                {"chat_id": doc["chat_id"]},
                {"$set": doc},
                upsert=True
            )
            synced_channels += 1

        # 2. Sync Shared Bundles (Optional - skipped to avoid bloat)

        # 3. Sync Groups
        main_groups = await db.groups_col_main.find({}).sort("created_at", -1).limit(200).to_list(length=200)
        synced_groups = 0
        for grp in main_groups:
            doc = {k:v for k,v in grp.items() if k != "_id"}
            doc["is_synced"] = True
            doc["last_synced"] = time.time()

            await db.cache_groups_col.update_one(
                {"code": doc["code"]},
                {"$set": doc},
                upsert=True
            )
            synced_groups += 1

        duration = time.time() - start_time
        logger.info(f"Sync complete in {duration:.2f}s. Cached: {synced_channels} Channels, {synced_groups} Groups.")

    except Exception as e:
        logger.error(f"Sync Job Failed: {e}")
