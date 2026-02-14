import time
from motor.motor_asyncio import AsyncIOMotorClient
from config import Config
from log import get_logger

logger = get_logger(__name__)

class Database:
    def __init__(self):
        self.client_main = None
        self.client_user = None
        self.client_private = None

        self.db_main = None
        self.db_user = None
        self.db_private = None
        self.db_request = None

        # MainDB Collections (Global Read-Only Content)
        self.channels_col = None
        self.bundles_col = None
        self.groups_col = None
        self.configs_col = None
        self.tasks_col = None
        self.coupons_col = None
        self.logs_col = None
        self.force_shares_col = None
        self.delete_queue_col = None

        # UserDB Collections (Shared Read-Write)
        self.users_col = None

        # PrivateDB Collections (Local Cache/Config)
        self.local_cache_col = None

        # RequestDB Collection
        self.requests_col = None

    def connect(self):
        try:
            # 1. MainDB Connection (Global Content)
            # Use Config.MAIN_URI
            self.client_main = AsyncIOMotorClient(Config.MAIN_URI)
            try:
                self.db_main = self.client_main.get_database()
            except Exception:
                self.db_main = self.client_main["fileshare_bot_main"]

            # 2. UserDB Connection (Global Users)
            if Config.USER_URI == Config.MAIN_URI:
                self.client_user = self.client_main
                self.db_user = self.db_main
            else:
                self.client_user = AsyncIOMotorClient(Config.USER_URI)
                try:
                    self.db_user = self.client_user.get_database()
                except Exception:
                    self.db_user = self.client_user["fileshare_bot_users"]

            # 3. PrivateDB Connection (Local Cache)
            if Config.PRIVATE_URI == Config.MAIN_URI:
                self.client_private = self.client_main
                self.db_private = self.db_main
            else:
                self.client_private = AsyncIOMotorClient(Config.PRIVATE_URI)
                try:
                    self.db_private = self.client_private.get_database()
                except Exception:
                    self.db_private = self.client_private["fileshare_bot_private"]

            # 4. RequestDB (Inside MainDB Cluster)
            self.db_request = self.client_main["xtv_requests"]
            self.requests_col = self.db_request["requests"]

            # Initialize Collections
            self.channels_col = self.db_main.channels
            self.bundles_col = self.db_main.bundles
            self.groups_col = self.db_main.groups
            self.configs_col = self.db_main.configs
            self.tasks_col = self.db_main.tasks
            self.coupons_col = self.db_main.coupons
            self.logs_col = self.db_main.logs
            self.force_shares_col = self.db_main.force_shares
            self.delete_queue_col = self.db_main.delete_queue

            self.users_col = self.db_user.users

            self.local_cache_col = self.db_private.local_cache

            logger.info("Connected to MongoDB (MainDB, UserDB, PrivateDB)")
        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            raise e

    # --- Audit Logs ---
    async def add_log(self, action, user_id, details):
        await self.logs_col.insert_one({
            "action": action,
            "user_id": user_id,
            "details": details,
            "ts": time.time()
        })

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
        cursor = self.channels_col.find({"approved": True, "$or": [{"type": "storage"}, {"type": {"$exists": False}}]})
        return await cursor.to_list(length=100)

    async def get_force_sub_channels(self):
        cursor = self.channels_col.find({"approved": True, "type": "force_sub"})
        return await cursor.to_list(length=100)

    async def get_franchise_channels(self):
        cursor = self.channels_col.find({"approved": True, "is_franchise": True})
        return await cursor.to_list(length=100)

    async def set_channel_franchise_status(self, chat_id, is_franchise):
        await self.channels_col.update_one(
            {"chat_id": chat_id},
            {"$set": {"is_franchise": is_franchise, "type": "force_sub"}}
        )

    async def is_channel_approved(self, chat_id):
        doc = await self.channels_col.find_one({"chat_id": chat_id, "approved": True})
        return bool(doc)

    # --- Bundles ---
    async def create_bundle(self, code, file_ids, source_channel, title, original_range, **kwargs):
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

    # --- Requests (Request Bot) ---
    async def mark_request_done(self, tmdb_id, media_type):
        if not tmdb_id: return
        try:
            tid = int(tmdb_id)
        except:
            tid = tmdb_id

        await self.requests_col.update_many(
            {"tmdb_id": tid, "type": media_type},
            {"$set": {"status": "done"}}
        )

    # --- Tasks ---
    async def add_task(self, question, answer, options=None, task_type="text"):
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
        await self.force_shares_col.insert_one({
            "link": link,
            "text": text_template,
            "created_at": time.time()
        })

    async def get_share_channels(self):
        return await self.force_shares_col.find({}).to_list(length=100)

    async def remove_share_channel(self, link):
        await self.force_shares_col.delete_one({"link": link})

    # --- Rate Limit ---
    async def check_rate_limit(self, user_id):
        user = await self.users_col.find_one({"user_id": user_id})
        if not user:
            return True, 0

        history = user.get("requests", [])
        now = time.time()
        valid_requests = [ts for ts in history if now - ts < Config.RATE_LIMIT_WINDOW]

        if len(valid_requests) != len(history):
            await self.users_col.update_one(
                {"user_id": user_id},
                {"$set": {"requests": valid_requests}}
            )

        if len(valid_requests) >= Config.RATE_LIMIT_BUNDLES:
            return False, len(valid_requests)

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
        user = await self.users_col.find_one({"user_id": user_id})
        if user and user.get("referrer_id"):
            return False

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

    async def get_user_origin(self, user_id):
        user = await self.users_col.find_one({"user_id": user_id})
        return user.get("origin_bot_id") if user else None

    # --- Auto-Delete ---
    async def add_to_delete_queue(self, chat_id, message_ids, delete_at):
        await self.delete_queue_col.insert_one({
            "chat_id": chat_id,
            "message_ids": message_ids,
            "delete_at": delete_at
        })

    async def get_due_deletions(self):
        now = time.time()
        cursor = self.delete_queue_col.find({"delete_at": {"$lte": now}})
        return await cursor.to_list(length=100)

    async def remove_from_delete_queue(self, id_list):
        await self.delete_queue_col.delete_many({"_id": {"$in": id_list}})

    # --- Stats ---
    async def get_active_users_24h(self):
        count = await self.users_col.count_documents({"requests": {"$exists": True, "$not": {"$size": 0}}})
        return count

    async def get_total_users(self):
        return await self.users_col.count_documents({})

    async def get_new_users_count(self, days=1):
        cutoff = time.time() - (days * 24 * 3600)
        return await self.users_col.count_documents({"joined_at": {"$gte": cutoff}})

    async def get_top_referrers(self, limit=10):
        cursor = self.users_col.find().sort("referral_count", -1).limit(limit)
        return await cursor.to_list(length=limit)

    # --- Coupons ---
    async def create_coupon(self, code, reward_hours, usage_limit=1):
        await self.coupons_col.insert_one({
            "code": code,
            "reward_hours": reward_hours,
            "usage_limit": usage_limit,
            "used_count": 0,
            "created_at": time.time()
        })

    async def get_coupon(self, code):
        return await self.coupons_col.find_one({"code": code})

    async def redeem_coupon(self, code, user_id):
        user = await self.users_col.find_one({"user_id": user_id, "redeemed_coupons": code})
        if user:
            return False, "already_used"

        coupon = await self.coupons_col.find_one({"code": code})
        if not coupon:
            return False, "invalid"

        if coupon["used_count"] >= coupon["usage_limit"]:
            return False, "limit_reached"

        await self.coupons_col.update_one({"code": code}, {"$inc": {"used_count": 1}})
        await self.users_col.update_one(
            {"user_id": user_id},
            {"$push": {"redeemed_coupons": code}},
            upsert=True
        )
        await self.add_premium_user(user_id, coupon["reward_hours"] / 24.0)
        return True, "success"

    async def delete_coupon(self, code):
        await self.coupons_col.delete_one({"code": code})

    async def get_all_coupons(self):
        return await self.coupons_col.find({}).to_list(length=100)

    # --- Daily Bonus ---
    async def get_daily_status(self, user_id):
        user = await self.users_col.find_one({"user_id": user_id})
        last_daily = user.get("last_daily", 0) if user else 0
        now = time.time()
        if now - last_daily > 24 * 3600:
            return True
        return False

    async def claim_daily_bonus(self, user_id, reward_hours=1):
        now = time.time()
        await self.users_col.update_one(
            {"user_id": user_id},
            {"$set": {"last_daily": now}},
            upsert=True
        )
        await self.extend_premium_user(user_id, reward_hours / 24.0)
        return True

    async def extend_premium_user(self, user_id, duration_days):
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

    # --- User History & Origin ---
    async def ensure_user(self, user_id, origin_bot_id=None):
        # Lazy user creation/ensure origin
        update = {"$set": {"updated_at": time.time()}}
        if origin_bot_id:
             update["$setOnInsert"] = {"origin_bot_id": origin_bot_id, "joined_at": time.time()}

        await self.users_col.update_one({"user_id": user_id}, update, upsert=True)

    async def add_user_history(self, user_id, code, title, limit=3):
        now = time.time()
        slice_val = -abs(limit)
        await self.users_col.update_one(
            {"user_id": user_id},
            {"$push": {"history": {
                "$each": [{"code": code, "title": title, "ts": now}],
                "$slice": slice_val
            }}},
            upsert=True
        )

    async def prune_user_history(self, user_id):
        # Lazy check to remove history older than X hours (Configurable)
        user = await self.users_col.find_one({"user_id": user_id})
        if not user or not user.get("history"): return

        retention_hours = await self.get_config("history_retention_hours", 3)
        cutoff = time.time() - (retention_hours * 60 * 60)

        new_history = [h for h in user["history"] if h["ts"] > cutoff]

        if len(new_history) != len(user["history"]):
             await self.users_col.update_one(
                {"user_id": user_id},
                {"$set": {"history": new_history}}
             )

    async def get_user_history(self, user_id):
        await self.prune_user_history(user_id)

        user = await self.users_col.find_one({"user_id": user_id})
        if not user: return []
        hist = user.get("history", [])
        return list(reversed(hist))

    # --- Groups ---
    async def create_group(self, code, title, tmdb_id, media_type, season, bundles=None, episode_val=None):
        doc = {
            "code": code,
            "title": title,
            "tmdb_id": str(tmdb_id) if tmdb_id else None,
            "media_type": media_type,
            "season": int(season) if season is not None else None,
            "episode_val": str(episode_val) if episode_val else None,
            "bundles": bundles or [],
            "created_at": time.time()
        }
        await self.groups_col.insert_one(doc)
        return doc

    async def get_group(self, code):
        return await self.groups_col.find_one({"code": code})

    async def get_group_by_bundle(self, bundle_code):
        return await self.groups_col.find_one({"bundles": bundle_code})

    async def get_group_by_tmdb(self, tmdb_id, media_type, season=None, episode_val=None):
        if not tmdb_id: return None
        query = {
            "tmdb_id": str(tmdb_id),
            "media_type": media_type
        }
        if media_type == "tv" and season is not None:
            query["season"] = int(season)

        if episode_val:
            query["episode_val"] = str(episode_val)
        else:
            query["episode_val"] = None

        return await self.groups_col.find_one(query)

    async def add_bundle_to_group(self, group_code, bundle_code):
        await self.groups_col.update_one(
            {"code": group_code},
            {"$addToSet": {"bundles": bundle_code}}
        )

    async def remove_bundle_from_group(self, group_code, bundle_code):
        await self.groups_col.update_one(
            {"code": group_code},
            {"$pull": {"bundles": bundle_code}}
        )

    async def update_group_title(self, group_code, new_title):
        await self.groups_col.update_one(
            {"code": group_code},
            {"$set": {"title": new_title}}
        )

    async def delete_group(self, group_code):
        await self.groups_col.delete_one({"code": group_code})

    async def get_all_groups(self):
        return await self.groups_col.find({}).to_list(length=1000)

db = Database()
