import asyncio
import time
import sys
from pyrogram import Client, idle
from config import Config
from db import db
from log import get_logger
from utils.sync_manager import sync_from_main

logger = get_logger(__name__)

async def check_franchise_auth_and_heartbeat(app):
    """
    Franchisee Authentication & Heartbeat Loop:
    1. Authenticates against MainDB.franchisees using ID and Password.
    2. Sends heartbeat to MainDB.bot_registry.
    
    If auth fails (invalid credentials or BANNED), triggers self destruct.
    """
    fail_count = 0
    max_fails_connection = 144 # 24h of offline tolerance
    
    while True:
        try:
            now = time.time()
            # 1. Check Auth
            franchisee = await db.franchisees_col.find_one({
                "franchisee_id": Config.FRANCHISEE_ID,
                "password": Config.FRANCHISEE_PASSWORD
            })
            
            # Reset connection fail count on successful query
            fail_count = 0
            
            if not franchisee:
                logger.critical(f"SECURITY ALERT: Invalid Franchisee Credentials for {Config.FRANCHISEE_ID}!")
                await handle_self_destruct("Invalid Franchise Credentials")
                break
                
            if franchisee.get("status") == "BANNED":
                logger.critical(f"SECURITY ALERT: Franchisee {Config.FRANCHISEE_ID} has been BANNED by the CEO!")
                await handle_self_destruct("Franchisee Banned")
                break
                
            # 2. Send Heartbeat to Registry
            if Config.BOT_USERNAME:
                line_id = f"FRANCHISE-{Config.FRANCHISEE_ID}"
                logger.info(f"❤️ Sending Heartbeat... (Line: {line_id})")
                
                await db.bot_registry_col.update_one(
                    {"username": Config.BOT_USERNAME}, 
                    {
                        "$set": {
                            "username": Config.BOT_USERNAME,
                            "line_id": line_id,
                            "type": "franchisee",
                            "status": "ACTIVE",
                            "last_seen": now,
                            "updated_at": now
                        }
                    },
                    upsert=True
                )
                
        except Exception as e:
            fail_count += 1
            logger.warning(f"Heartbeat/Auth Connection Failed ({fail_count}): {e}")
            
            if fail_count >= max_fails_connection:
                await handle_self_destruct("MainDB Unreachable > 24h", app=app)
                break
                
        # Heartbeat interval
        await asyncio.sleep(60)

async def handle_self_destruct(reason, app=None):
    logger.critical(f"⚠️ SELF DESTRUCT INITIATED: {reason}")
    logger.critical("Contact @davdxpx if this is an error.")

    if Config.CEO_ID and app:
        try:
            await app.send_message(Config.CEO_ID, f"⚠️ **SELF DESTRUCT TRIGGERED!**\n\nReason: {reason}\nContact: @davdxpx")
        except: pass

    # Clear Sensitive Cache from PrivateDB
    try:
        if db.local_cache_col:
            await db.local_cache_col.delete_many({})
            logger.info("Sensitive cache cleared.")
    except: pass

    sys.exit(f"SELF DESTRUCT: {reason}")

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

    # Run Cleanup (Fix pollution from previous syncs)
    await db.perform_cache_cleanup()

    await seed_tasks()

    # Validate Franchise Info
    if not Config.FRANCHISEE_ID or not Config.FRANCHISEE_PASSWORD:
        logger.critical("⚠️  MISSING FRANCHISEE_ID OR FRANCHISEE_PASSWORD! PLEASE CHECK .ENV")
        sys.exit("CRITICAL: Franchise Info Missing. Bot cannot start.")
    else:
        logger.info(f"✅ Franchisee ID: {Config.FRANCHISEE_ID}")
        logger.info("✅ Franchisee Password: [CONFIGURED]")

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
    asyncio.create_task(check_franchise_auth_and_heartbeat(app))
    asyncio.create_task(auto_delete_loop(app))
    asyncio.create_task(sync_loop())

    # Warmup Peer Cache
    logger.info("Warming up peer cache...")

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
