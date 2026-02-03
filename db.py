import time
from motor.motor_asyncio import AsyncIOMotorClient
from config import Config
from log import get_logger

logger = get_logger(__name__)

class Database:
    def __init__(self):
        self.client = None
        self.db = None
        self.channels_col = None
        self.bundles_col = None
        self.configs_col = None
        self.tasks_col = None
        self.users_col = None

    def connect(self):
        try:
            self.client = AsyncIOMotorClient(Config.MONGO_URI)
            self.db = self.client.get_database()
            self.channels_col = self.db.channels
            self.bundles_col = self.db.bundles
            self.configs_col = self.db.configs
            self.tasks_col = self.db.tasks
            self.users_col = self.db.users
            logger.info("Connected to MongoDB")
        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            raise e

    # --- Configs ---
    async def get_config(self, key, default=None):
        doc = await self.configs_col.find_one({"key": key})
        return doc["value"] if doc else default

    async def update_config(self, key, value):
        await self.configs_col.update_one(
            {"key": key}, {"$set": {"value": value}}, upsert=True
        )

    # --- Channels ---
    async def add_channel(self, chat_id, title, username):
        await self.channels_col.update_one(
            {"chat_id": chat_id},
            {"$set": {"title": title, "username": username, "approved": True}},
            upsert=True
        )

    async def remove_channel(self, chat_id):
        await self.channels_col.delete_one({"chat_id": chat_id})

    async def get_approved_channels(self):
        cursor = self.channels_col.find({"approved": True})
        return await cursor.to_list(length=100)

    async def is_channel_approved(self, chat_id):
        doc = await self.channels_col.find_one({"chat_id": chat_id, "approved": True})
        return bool(doc)

    # --- Bundles ---
    async def create_bundle(self, code, file_ids, source_channel, title, original_range):
        await self.bundles_col.insert_one({
            "code": code,
            "file_ids": file_ids,
            "source_channel": source_channel,
            "title": title,
            "range": original_range,
            "created_at": time.time(),
            "views": 0
        })

    async def get_bundle(self, code):
        return await self.bundles_col.find_one({"code": code})

    async def get_all_bundles(self):
        return await self.bundles_col.find({}).to_list(length=100)

    async def increment_bundle_views(self, code):
        await self.bundles_col.update_one({"code": code}, {"$inc": {"views": 1}})

    # --- Tasks ---
    async def add_task(self, question, answer, options=None, task_type="text"):
        # options is list of strings for multiple choice
        await self.tasks_col.insert_one({
            "question": question,
            "answer": answer,
            "options": options or [],
            "type": task_type
        })

    async def get_random_tasks(self, limit=3):
        pipeline = [{"$sample": {"size": limit}}]
        cursor = self.tasks_col.aggregate(pipeline)
        return await cursor.to_list(length=limit)

    async def get_all_tasks(self):
        return await self.tasks_col.find({}).to_list(length=1000)

    async def delete_task(self, question):
        await self.tasks_col.delete_one({"question": question})

    # --- Rate Limit ---
    async def check_rate_limit(self, user_id):
        user = await self.users_col.find_one({"user_id": user_id})
        if not user:
            return True, 0 # Allowed, 0 requests

        history = user.get("requests", [])
        now = time.time()
        # Filter requests within the window
        valid_requests = [ts for ts in history if now - ts < Config.RATE_LIMIT_WINDOW]

        # Update if changed (cleanup old)
        if len(valid_requests) != len(history):
            await self.users_col.update_one(
                {"user_id": user_id},
                {"$set": {"requests": valid_requests}}
            )

        if len(valid_requests) >= Config.RATE_LIMIT_BUNDLES:
            return False, len(valid_requests) # Blocked

        return True, len(valid_requests)

    async def add_request(self, user_id):
        now = time.time()
        await self.users_col.update_one(
            {"user_id": user_id},
            {"$push": {"requests": now}},
            upsert=True
        )

db = Database()
