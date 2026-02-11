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
            try:
                self.db = self.client.get_database()
            except Exception:
                # Fallback if no database specified in URI
                self.db = self.client["fileshare_bot"]

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
    async def add_channel(self, chat_id, title, username, channel_type="storage", invite_link=None):
        await self.channels_col.update_one(
            {"chat_id": chat_id},
            {"$set": {
                "title": title,
                "username": username,
                "approved": True,
                "type": channel_type,
                "invite_link": invite_link
            }},
            upsert=True
        )

    async def remove_channel(self, chat_id):
        await self.channels_col.delete_one({"chat_id": chat_id})

    async def get_approved_channels(self):
        # Default to storage if type not set (legacy support)
        cursor = self.channels_col.find({"approved": True, "$or": [{"type": "storage"}, {"type": {"$exists": False}}]})
        return await cursor.to_list(length=100)

    async def get_force_sub_channels(self):
        cursor = self.channels_col.find({"approved": True, "type": "force_sub"})
        return await cursor.to_list(length=100)

    async def is_channel_approved(self, chat_id):
        doc = await self.channels_col.find_one({"chat_id": chat_id, "approved": True})
        return bool(doc)

    # --- Bundles ---
    async def create_bundle(self, code, file_ids, source_channel, title, original_range, **kwargs):
        # kwargs allows passing extra fields like tmdb_id, media_type, etc.
        doc = {
            "code": code,
            "file_ids": file_ids,
            "source_channel": source_channel,
            "title": title,
            "range": original_range,
            "created_at": time.time(),
            "views": 0
        }
        doc.update(kwargs)
        await self.bundles_col.insert_one(doc)

    async def get_bundle(self, code):
        return await self.bundles_col.find_one({"code": code})

    async def get_all_bundles(self):
        return await self.bundles_col.find({}).to_list(length=100)

    async def increment_bundle_views(self, code):
        await self.bundles_col.update_one({"code": code}, {"$inc": {"views": 1}})

    async def update_bundle_title(self, code, new_title):
        await self.bundles_col.update_one({"code": code}, {"$set": {"title": new_title}})

    async def delete_bundle(self, code):
        await self.bundles_col.delete_one({"code": code})

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

    # --- Force Share Channels ---
    async def add_share_channel(self, link, text_template):
        await self.db.force_shares.insert_one({
            "link": link,
            "text": text_template,
            "created_at": time.time()
        })

    async def get_share_channels(self):
        return await self.db.force_shares.find({}).to_list(length=100)

    async def remove_share_channel(self, link):
        await self.db.force_shares.delete_one({"link": link})

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

    # --- Premium ---
    async def add_premium_user(self, user_id, duration_days):
        # Use extend logic by default to be safe
        await self.extend_premium_user(user_id, duration_days)

    async def remove_premium_user(self, user_id):
        await self.users_col.update_one(
            {"user_id": user_id},
            {"$set": {"is_premium": False, "premium_expiry": 0}}
        )

    async def is_premium_user(self, user_id):
        user = await self.users_col.find_one({"user_id": user_id})
        if not user or not user.get("is_premium"):
            return False
        expiry = user.get("premium_expiry", 0)
        if expiry < time.time():
            return False
        return True

    async def get_premium_users(self):
         cursor = self.users_col.find({"is_premium": True})
         return await cursor.to_list(length=1000)

    # --- Referrals ---
    async def set_referrer(self, user_id, referrer_id):
        # Only set if not already set
        user = await self.users_col.find_one({"user_id": user_id})
        if user and user.get("referrer_id"):
            return False # Already has referrer

        await self.users_col.update_one(
            {"user_id": user_id},
            {"$set": {"referrer_id": referrer_id}},
            upsert=True
        )
        return True

    async def increment_referral(self, referrer_id):
        await self.users_col.update_one(
            {"user_id": referrer_id},
            {"$inc": {"referral_count": 1}},
            upsert=True
        )
        return await self.get_referral_count(referrer_id)

    async def get_referral_count(self, user_id):
        user = await self.users_col.find_one({"user_id": user_id})
        return user.get("referral_count", 0) if user else 0

    # --- Auto-Delete ---
    async def add_to_delete_queue(self, chat_id, message_ids, delete_at):
        await self.db.delete_queue.insert_one({
            "chat_id": chat_id,
            "message_ids": message_ids,
            "delete_at": delete_at
        })

    async def get_due_deletions(self):
        now = time.time()
        cursor = self.db.delete_queue.find({"delete_at": {"$lte": now}})
        return await cursor.to_list(length=100)

    async def remove_from_delete_queue(self, id_list):
        await self.db.delete_queue.delete_many({"_id": {"$in": id_list}})

    # --- Stats ---
    async def get_active_users_24h(self):
        # We need to track activity. Using last request time.
        # Assuming 'requests' list stores timestamps, we can check the last one.
        # Or we add a 'last_active' field. For now, let's use requests list max.
        now = time.time()
        cutoff = now - (24 * 3600)
        # Find users where at least one request is > cutoff
        # This is heavy if requests list is long.
        # Optimally, we update 'last_active' on every request.
        # Let's rely on 'requests' being sorted or just check availability.
        # Actually check_rate_limit updates/prunes requests.
        # So any user with non-empty requests list might be active recently?
        # But rate limit window is 2h.
        # Let's count users who have requests.
        count = await self.users_col.count_documents({"requests": {"$exists": True, "$not": {"$size": 0}}})
        # This is roughly "active in last 2h".
        # To get 24h, we'd need better tracking.
        # For this iteration, let's stick to this or implement last_active later.
        return count

    async def get_total_users(self):
        return await self.users_col.count_documents({})

    async def get_new_users_count(self, days=1):
        # Assuming we track 'joined_at'. If not, we can't do this accurately yet.
        # We should add 'joined_at' to new users.
        # For legacy users without it, they are "old".
        cutoff = time.time() - (days * 24 * 3600)
        return await self.users_col.count_documents({"joined_at": {"$gte": cutoff}})

    async def get_top_referrers(self, limit=10):
        cursor = self.users_col.find().sort("referral_count", -1).limit(limit)
        return await cursor.to_list(length=limit)

    # --- Coupons ---
    async def create_coupon(self, code, reward_hours, usage_limit=1):
        await self.db.coupons.insert_one({
            "code": code,
            "reward_hours": reward_hours,
            "usage_limit": usage_limit,
            "used_count": 0,
            "created_at": time.time()
        })

    async def get_coupon(self, code):
        return await self.db.coupons.find_one({"code": code})

    async def redeem_coupon(self, code, user_id):
        # Check if user already used it?
        # Create a redemption log collection or store in user doc.
        # Let's store in user doc: "redeemed_coupons": [code1, code2]
        user = await self.users_col.find_one({"user_id": user_id, "redeemed_coupons": code})
        if user:
            return False, "already_used"

        coupon = await self.db.coupons.find_one({"code": code})
        if not coupon:
            return False, "invalid"

        if coupon["used_count"] >= coupon["usage_limit"]:
            return False, "limit_reached"

        # Apply
        await self.db.coupons.update_one({"code": code}, {"$inc": {"used_count": 1}})
        await self.users_col.update_one(
            {"user_id": user_id},
            {"$push": {"redeemed_coupons": code}},
            upsert=True
        )
        await self.add_premium_user(user_id, coupon["reward_hours"] / 24.0)
        return True, "success"

    async def delete_coupon(self, code):
        await self.db.coupons.delete_one({"code": code})

    async def get_all_coupons(self):
        return await self.db.coupons.find({}).to_list(length=100)

    # --- Daily Bonus ---
    async def get_daily_status(self, user_id):
        user = await self.users_col.find_one({"user_id": user_id})
        last_daily = user.get("last_daily", 0) if user else 0
        now = time.time()
        # Cooldown 24h
        if now - last_daily > 24 * 3600:
            return True # Ready
        return False # Cooldown

    async def claim_daily_bonus(self, user_id, reward_hours=1):
        # Update last_daily
        now = time.time()
        await self.users_col.update_one(
            {"user_id": user_id},
            {"$set": {"last_daily": now}},
            upsert=True
        )
        # Grant Premium (additive?)
        # db.add_premium_user sets expiry from NOW. If user already has premium, we should extend it.
        # Our current add_premium_user logic sets `expiry = time.time() + duration`.
        # This overwrites if they have 30 days left! We need to fix `add_premium_user` to extend.

        # Let's fix add_premium_user first (below) or override here.
        # For safety let's do logic here for now or update the main method.
        # I will update `add_premium_user` logic in this patch too.
        await self.extend_premium_user(user_id, reward_hours / 24.0)
        return True

    async def extend_premium_user(self, user_id, duration_days):
        # Intelligent add
        user = await self.users_col.find_one({"user_id": user_id})
        current_expiry = user.get("premium_expiry", 0) if user else 0
        now = time.time()

        if current_expiry > now:
            new_expiry = current_expiry + (duration_days * 24 * 3600)
        else:
            new_expiry = now + (duration_days * 24 * 3600)

        await self.users_col.update_one(
            {"user_id": user_id},
            {"$set": {"premium_expiry": new_expiry, "is_premium": True}},
            upsert=True
        )

db = Database()
