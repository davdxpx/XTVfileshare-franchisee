import asyncio
import time
import sys
from pyrogram import Client, idle
from config import Config
from db import db
from log import get_logger
from utils.backup import run_backup

logger = get_logger(__name__)

async def check_ceo_security():
    # Verify CEO_ID against DB
    stored_owner = await db.get_config("owner_id")
    if stored_owner is None:
        # First time setup
        if Config.CEO_ID:
            await db.update_config("owner_id", Config.CEO_ID)
            logger.info(f"Owner ID initialized to {Config.CEO_ID}")
    else:
        if Config.CEO_ID and stored_owner != Config.CEO_ID:
            logger.critical(f"SECURITY ALERT: CEO_ID mismatch! Env: {Config.CEO_ID}, DB: {stored_owner}")
            sys.exit("SECURITY ALERT: CEO_ID mismatch. Self-destructing.")

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

async def seed_tasks():
    # Check if tasks exist
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

async def auto_delete_loop(app):
    logger.info("Starting Auto-Delete Loop...")
    while True:
        try:
            # Check DB for due deletions
            due_list = await db.get_due_deletions()
            if due_list:
                for item in due_list:
                    chat_id = item["chat_id"]
                    msg_ids = item["message_ids"]
                    # msg_ids can be list or single int (legacy/robustness)
                    if isinstance(msg_ids, int): msg_ids = [msg_ids]

                    try:
                        await app.delete_messages(chat_id, msg_ids)
                    except Exception as e:
                        logger.warning(f"Failed to auto-delete in {chat_id}: {e}")

                    # Remove from queue regardless of success (to avoid infinite loop if blocked)
                    await db.remove_from_delete_queue([item["_id"]])

            await asyncio.sleep(60) # Check every minute
        except Exception as e:
            logger.error(f"Auto-Delete Loop Error: {e}")
            await asyncio.sleep(60)

async def main():
    # Set Start Time
    Config.START_TIME = time.time()

    # Connect to Database
    db.connect()

    # Security Check
    await check_ceo_security()

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
    logger.info(f"Bot started as @{me.username}")
    logger.info("🚀 Bot is running! Developed by @davdxpx")

    # Start Background Tasks
    asyncio.create_task(auto_delete_loop(app))
    asyncio.create_task(backup_loop(app))

    # Warmup Peer Cache
    logger.info("Warming up peer cache...")
    channels = await db.get_approved_channels()
    fs_channels = await db.get_force_sub_channels()
    all_chats = channels + fs_channels

    # Unique dict by chat_id to keep metadata (like username)
    unique_chats = {c["chat_id"]: c for c in all_chats}

    for chat_id, data in unique_chats.items():
        try:
            # Try username first if available (resolves peer better)
            username = data.get("username")
            if username:
                await app.get_chat(username)
                # logger.info(f"Cached peer via username: {username}")
            else:
                await app.get_chat(chat_id)
                # logger.info(f"Cached peer via ID: {chat_id}")
        except Exception as e:
            logger.warning(f"Failed to cache peer {chat_id} (@{data.get('username')}): {e}")

    await idle()
    await app.stop()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
