import asyncio
import time
import sys
from pyrogram import Client, idle
from config import Config
from db import db
from log import get_logger
from utils.backup import run_backup
from utils.sync_manager import sync_from_main

logger = get_logger(__name__)

async def check_security_and_connectivity():
    """
    Robust Security Check:
    1. CEO_ID mismatch vs MainDB Config
    2. MainDB Connectivity

    If failure > 5 times or downtime > 24h: Self Destruct.
    """
    fail_count = 0
    max_fails = 5

    while True:
        try:
            # 1. Check Connectivity & Owner ID
            stored_owner = await db.get_config("owner_id")

            # If successful read, reset fail count
            fail_count = 0

            if stored_owner is None:
                # First time initialization
                if Config.CEO_ID:
                    await db.update_config("owner_id", Config.CEO_ID)
                    logger.info(f"Owner ID initialized to {Config.CEO_ID}")
            else:
                if Config.CEO_ID and stored_owner != Config.CEO_ID:
                    logger.critical(f"SECURITY ALERT: CEO_ID mismatch! Env: {Config.CEO_ID}, DB: {stored_owner}")
                    await handle_self_destruct("CEO_ID Mismatch")

        except Exception as e:
            fail_count += 1
            logger.warning(f"MainDB Connection Failed ({fail_count}): {e}")

            # Request: if Main down > 24h
            # Check interval is 10 mins (600s).
            # 24h = 1440 mins = 144 checks.
            # Using 144 checks = 24h.

            if fail_count >= 144:
                await handle_self_destruct("MainDB Unreachable > 24h")

        # Check every 10 mins
        await asyncio.sleep(600)

async def handle_self_destruct(reason):
    logger.critical(f"⚠️ SELF DESTRUCT INITIATED: {reason}")
    logger.critical("Contact @davdxpx if this is an error.")

    # Clear Sensitive Cache from PrivateDB
    try:
        if db.local_cache_col:
            await db.local_cache_col.delete_many({})
            logger.info("Sensitive cache cleared.")
    except: pass

    sys.exit(f"SELF DESTRUCT: {reason}")

async def backup_loop(app):
    logger.info("Starting Backup Loop...")
    while True:
        try:
            # Check last backup time
            last_backup = await db.get_config("last_backup_ts", 0)
            now = time.time()

            # 24 hours = 86400 seconds
            if now - last_backup >= 86400:
                success = await run_backup(app)
                if success:
                    await db.update_config("last_backup_ts", now)

            # Check every hour
            await asyncio.sleep(3600)
        except Exception as e:
            logger.error(f"Backup Loop Error: {e}")
            await asyncio.sleep(3600)

async def sync_loop():
    logger.info("Starting Sync Loop (30 min interval)...")
    while True:
        await sync_from_main()
        await asyncio.sleep(1800) # 30 mins

async def seed_tasks():
    # Check if tasks exist
    try:
        tasks = await db.get_all_tasks()
        if not tasks:
            logger.info("Seeding default tasks...")
            defaults = [
                {"q": "What is 5 + 3?", "a": "8", "t": "text"},
                {"q": "What is 10 * 2?", "a": "20", "t": "text"},
                {"q": "What is 15 - 7?", "a": "8", "t": "text"},
                {"q": "Is the earth flat?", "a": "No", "opts": ["Yes", "No"], "t": "quiz"},
                {"q": "Capital of France?", "a": "Paris", "opts": ["London", "Berlin", "Paris", "Madrid"], "t": "quiz"},
                {"q": "2 + 2 * 2 = ?", "a": "6", "opts": ["6", "8", "4"], "t": "quiz"}
            ]
            for t in defaults:
                await db.add_task(t["q"], t["a"], t.get("opts"), t["t"])
            logger.info("Seeding complete.")
    except Exception as e:
        logger.warning(f"Seeding skipped (DB not ready?): {e}")

async def auto_delete_loop(app):
    logger.info("Starting Auto-Delete Loop...")
    while True:
        try:
            # Check DB for due deletions
            due_list = await db.get_due_deletions()
            if due_list:
                for item in due_list:
                    chat_id = item["chat_id"]
                    message_ids = item["message_ids"]
                    if isinstance(message_ids, int): message_ids = [message_ids]

                    try:
                        await app.delete_messages(chat_id, message_ids)
                    except Exception as e:
                        logger.warning(f"Failed to auto-delete in {chat_id}: {e}")

                    # Remove from queue regardless of success
                    await db.remove_from_delete_queue([item["_id"]])

            await asyncio.sleep(60)
        except Exception as e:
            logger.error(f"Auto-Delete Loop Error: {e}")
            await asyncio.sleep(60)

async def main():
    # Set Start Time
    Config.START_TIME = time.time()

    # Connect to Database
    db.connect()

    # Start Security Monitor (Non-blocking task)
    asyncio.create_task(check_security_and_connectivity())

    # Seed Data
    await seed_tasks()

    # Initialize Bot
    plugins = dict(root="plugins")
    app = Client(
        "file_share_bot",
        api_id=Config.API_ID,
        api_hash=Config.API_HASH,
        bot_token=Config.BOT_TOKEN,
        plugins=plugins
    )

    await app.start()

    me = await app.get_me()
    Config.BOT_USERNAME = me.username

    # Startup Logs
    logger.info("========================================")
    logger.info(f"🚀 XTV Fileshare Bot v{Config.BOT_VERSION}")
    logger.info(f"👤 Bot: @{me.username} ({me.id})")
    logger.info(f"🔑 Owner ID: {Config.CEO_ID}")
    logger.info("========================================")

    # Mode Check
    if Config.MAIN_URI == Config.PRIVATE_URI:
        mode = "STANDALONE / CEO"
    else:
        mode = "FRANCHISEE (Connected to MainDB)"
    logger.info(f"⚙️  Running Mode: {mode}")
    logger.info("========================================")

    # Start Background Tasks
    asyncio.create_task(auto_delete_loop(app))
    # asyncio.create_task(backup_loop(app)) # Backup disabled for Franchisee
    asyncio.create_task(sync_loop())

    # Warmup Peer Cache
    logger.info("Warming up peer cache...")

    # Cache Backup Channel
    if Config.BACKUP_CHANNEL_ID:
        try:
            await app.get_chat(Config.BACKUP_CHANNEL_ID)
            logger.info(f"Cached Backup Channel: {Config.BACKUP_CHANNEL_ID}")
        except Exception as e:
            logger.error(f"Failed to cache Backup Channel {Config.BACKUP_CHANNEL_ID}: {e}")

    try:
        channels = await db.get_approved_channels()
        fs_channels = await db.get_force_sub_channels()
        all_chats = channels + fs_channels

        unique_chats = {c["chat_id"]: c for c in all_chats}

        for chat_id, data in unique_chats.items():
            try:
                username = data.get("username")
                if username:
                    await app.get_chat(username)
                else:
                    await app.get_chat(chat_id)
            except Exception as e:
                logger.warning(f"Failed to cache peer {chat_id}: {e}")
    except Exception as e:
        logger.warning(f"Peer cache warmup partial fail: {e}")

    await idle()
    await app.stop()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
