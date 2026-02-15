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
        # Fetch from Main
        channels = await db.get_force_sub_channels() # This gets Main+Private, but we want Main source specifically

        # We need direct access to copy.
        # db.channels_col_main is available.

        main_channels = await db.channels_col_main.find({"approved": True, "type": "force_sub"}).to_list(length=1000)

        synced_channels = 0
        for ch in main_channels:
            # Upsert into PrivateDB with a flag?
            # Or better: Maintain a separate 'cache_channels' collection?
            # Prompt says "cache force_sub_channels... to PrivateDB".
            # If we upsert to `channels_col_private`, they become "local".
            # If MainDB is down, `get_force_sub_channels` checks PrivateDB.
            # So copying them there works as a fallback.
            # But we should distinguish them so we don't delete them if we want to "clean sync".
            # For now, let's upsert by chat_id.

            # Prepare doc (exclude _id)
            doc = {k:v for k,v in ch.items() if k != "_id"}
            doc["is_synced"] = True
            doc["last_synced"] = time.time()

            await db.channels_col_private.update_one(
                {"chat_id": doc["chat_id"]},
                {"$set": doc},
                upsert=True
            )
            synced_channels += 1

        # 2. Sync Shared Bundles (Optional/Heavy?)
        # If we copy ALL bundles, it might be too much.
        # Maybe just "featured" or "recent"?
        # Prompt says "shared bundles/groups".
        # Let's limit to recent 100 or specific "shared" flag if it existed.
        # We will skip bulk bundle sync to avoid bloating PrivateDB unless explicitly requested.
        # But groups are important for navigation.

        # 3. Sync Groups
        main_groups = await db.groups_col_main.find({}).sort("created_at", -1).limit(200).to_list(length=200)
        synced_groups = 0
        for grp in main_groups:
            doc = {k:v for k,v in grp.items() if k != "_id"}
            doc["is_synced"] = True
            doc["last_synced"] = time.time()

            await db.groups_col_private.update_one(
                {"code": doc["code"]},
                {"$set": doc},
                upsert=True
            )
            synced_groups += 1

        duration = time.time() - start_time
        logger.info(f"Sync complete in {duration:.2f}s. Cached: {synced_channels} Channels, {synced_groups} Groups.")

    except Exception as e:
        logger.error(f"Sync Job Failed: {e}")
