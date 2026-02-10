import asyncio
from pyrogram import Client, idle
from config import Config
from db import db
from log import get_logger

logger = get_logger(__name__)

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

async def main():
    # Connect to Database
    db.connect()

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
