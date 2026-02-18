import time
import asyncio
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
        self.channels_col_main = None
        self.bundles_col_main = None
        self.groups_col_main = None
        self.configs_col_main = None

        # PrivateDB Collections (Local Write)
        self.channels_col_private = None
        self.bundles_col_private = None
        self.groups_col_private = None
        self.configs_col_private = None
        self.local_cache_col = None
        self.push_requests_col = None
        self.cache_channels_col = None
        self.cache_groups_col = None

        # Shared/Other
        self.tasks_col = None
        self.coupons_col = None
        self.logs_col = None
        self.force_shares_col = None
        self.delete_queue_col = None

        # UserDB Collections (Shared Read-Write)
        self.users_col = None

        # RequestDB Collection
        self.requests_col = None

        # MainDB Push Write (Direct via MainDB Role)
        self.push_requests_col_main = None

    def connect(self):
        try:
            # 1. MainDB Connection (Global Content & Limited Write)
            self.client_main = AsyncIOMotorClient(Config.MAIN_URI)
            try:
                self.db_main = self.client_main.get_database()
            except Exception:
                self.db_main = self.client_main["mainDB-filebot"]

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

            # 3. PrivateDB Connection (Local Cache/Bundles)
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
            self.db_request = self.client_main["mainDB-requests"]
            self.requests_col = self.db_request["requests"]

            # Initialize Collections

            # Read-Only Main
            self.channels_col_main = self.db_main.channels
            self.bundles_col_main = self.db_main.bundles
            self.groups_col_main = self.db_main.groups
            self.configs_col_main = self.db_main.configs

            # Write Main (Push Requests via Limited Role)
            self.push_requests_col_main = self.db_main.push_requests

            # Write Private
            self.channels_col_private = self.db_private.channels
            self.bundles_col_private = self.db_private.bundles
            self.groups_col_private = self.db_private.groups
            self.configs_col_private = self.db_private.configs
            self.local_cache_col = self.db_private.local_cache
            self.push_requests_col = self.db_private.push_requests
            self.cache_channels_col = self.db_private.cache_channels
            self.cache_groups_col = self.db_private.cache_groups

            # Other Global (Assume Read-Only Main for now, or Local?)
            self.tasks_col = self.db_main.tasks
            self.coupons_col = self.db_main.coupons
            self.force_shares_col = self.db_main.force_shares

            self.logs_col = self.db_private.logs
            self.delete_queue_col = self.db_private.delete_queue

            self.users_col = self.db_user.users

            logger.info("Connected to MongoDB (MainDB, UserDB, PrivateDB)")

            # --- Auto-Cleanup of Polluted Local Collections ---
            # Remove synced items from local collections to fix UI mixing issue
            # Run in background to not block startup
            try:
                # We can't use create_task here easily without loop, but we can just fire and forget if it's async?
                # Actually, this is init logic. Let's do it if we are in an async context?
                # db.connect is sync? No, calls AsyncIOMotorClient but doesn't await.
                # Wait, methods are async. connect() itself is synchronous in __init__?
                # No, connect() is a method. It is synchronous in main.py?
                # main.py calls db.connect() synchronously.
                # AsyncIOMotorClient creation is sync.
                # So we can't await here.
                # We will add a cleanup method and call it from main.py
                pass
            except Exception:
                pass

        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            raise e

    async def perform_cache_cleanup(self):
        """Removes 'synced' items from Local PrivateDB collections to fix UI pollution."""
        try:
            # Clean Channels
            res_ch = await self.channels_col_private.delete_many({"is_synced": True})
            if res_ch.deleted_count > 0:
                logger.info(f"Cleanup: Removed {res_ch.deleted_count} cached items from Local Channels.")

            # Clean Groups
            res_gr = await self.groups_col_private.delete_many({"is_synced": True})
            if res_gr.deleted_count > 0:
                logger.info(f"Cleanup: Removed {res_gr.deleted_count} cached items from Local Groups.")
        except Exception as e:
            logger.warning(f"Cache cleanup failed: {e}")

    # --- Helper for MainDB Retry ---
    async def _safe_main_query(self, coro_func, fallback_val=None, fallback_coro=None):
        """
        Executes a MainDB query with retries.
        If fails > 3 times or timeout > 30s, returns fallback.
        """
        attempts = 0
        max_retries = 3
        while attempts < max_retries:
            try:
                return await asyncio.wait_for(coro_func(), timeout=30.0)
            except Exception as e:
                attempts += 1
                logger.warning(f"MainDB query retry {attempts}: status {e}")
                await asyncio.sleep(5)

        logger.error("MainDB query failed after retries. Using fallback.")
        if fallback_coro:
            return await fallback_coro()
        return fallback_val

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
        # Check Private (Local Override) first
        doc = await self.configs_col_private.find_one({"key": key})
        if doc: return doc["value"]

        # Fallback to Main (Global) with retry
        async def main_query():
            doc = await self.configs_col_main.find_one({"key": key})
            return doc["value"] if doc else default

        return await self._safe_main_query(main_query, fallback_val=default)

    async def update_config(self, key, value):
        # Always write to Private (Local Override)
        await self.configs_col_private.update_one(
            {"key": key}, {"$set": {"value": value}}, upsert=True
        )

    # --- Channels ---
    async def add_channel(self, chat_id, title, username, channel_type="storage", invite_link=None):
        # Franchisee adds local channels to PrivateDB
        await self.channels_col_private.update_one(
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
        # Only remove from PrivateDB
        await self.channels_col_private.delete_one({"chat_id": chat_id})

    async def get_approved_channels(self):
        # Merge Main, Cache, and Private channels

        # 1. Private (Local)
        private_cursor = self.channels_col_private.find({"approved": True, "$or": [{"type": "storage"}, {"type": {"$exists": False}}]})
        private_channels = await private_cursor.to_list(length=100)

        # 2. Main (Global) with Cache Fallback
        async def main_query():
            cursor = self.channels_col_main.find({"approved": True, "$or": [{"type": "storage"}, {"type": {"$exists": False}}]})
            return await cursor.to_list(length=100)

        async def cache_fallback():
            logger.warning("MainDB unreachable. Using Cached Channels.")
            cursor = self.cache_channels_col.find({"approved": True, "$or": [{"type": "storage"}, {"type": {"$exists": False}}]})
            return await cursor.to_list(length=100)

        main_channels = await self._safe_main_query(main_query, fallback_coro=cache_fallback)

        # Combine: Main overrides nothing (read-only), Private overrides Main if ID matches?
        # Usually IDs distinct. If conflict, Private wins (local override).
        combined = {c["chat_id"]: c for c in main_channels}
        for c in private_channels:
            combined[c["chat_id"]] = c

        return list(combined.values())

    async def get_force_sub_channels(self):
        async def main_query():
            return await self.channels_col_main.find({"approved": True, "type": "force_sub"}).to_list(length=100)

        async def cache_fallback():
            return await self.cache_channels_col.find({"approved": True, "type": "force_sub"}).to_list(length=100)

        main_list = await self._safe_main_query(main_query, fallback_coro=cache_fallback)
        private_list = await self.channels_col_private.find({"approved": True, "type": "force_sub"}).to_list(length=100)
        return main_list + private_list

    async def get_franchise_channels(self):
        async def main_query():
            return await self.channels_col_main.find({"approved": True, "is_franchise": True}).to_list(length=100)
        return await self._safe_main_query(main_query, fallback_val=[])

    async def set_channel_franchise_status(self, chat_id, is_franchise):
        # Write to PrivateDB (Local Franchise setting?)
        await self.channels_col_private.update_one(
            {"chat_id": chat_id},
            {"$set": {"is_franchise": is_franchise, "type": "force_sub"}}
        )

    async def is_channel_approved(self, chat_id):
        # Check Private first
        if await self.channels_col_private.find_one({"chat_id": chat_id, "approved": True}):
            return True

        async def main_query():
            return await self.channels_col_main.find_one({"chat_id": chat_id, "approved": True})

        if await self._safe_main_query(main_query, fallback_val=False):
            return True
        return False

    # --- Series Channels ---
    async def add_series_channel(self, chat_id, title, username, tmdb_id, poster_msg_id, buttons_msg_id, instruction_msg_id):
        await self.channels_col_private.update_one(
            {"chat_id": chat_id},
            {"$set": {
                "title": title,
                "username": username,
                "approved": True,
                "type": "series",
                "tmdb_id": str(tmdb_id),
                "poster_msg_id": poster_msg_id,
                "buttons_msg_id": buttons_msg_id,
                "instruction_msg_id": instruction_msg_id,
                "created_at": time.time()
            }},
            upsert=True
        )

    async def get_series_channels(self):
        return await self.channels_col_private.find({"type": "series"}).to_list(length=100)

    async def get_series_channel_by_tmdb(self, tmdb_id):
        cursor = self.channels_col_private.find({"type": "series", "tmdb_id": str(tmdb_id)})
        return await cursor.to_list(length=10)

    async def update_series_channel_messages(self, chat_id, buttons_msg_id, instruction_msg_id=None):
        update = {"buttons_msg_id": buttons_msg_id}
        if instruction_msg_id:
            update["instruction_msg_id"] = instruction_msg_id
        await self.channels_col_private.update_one(
            {"chat_id": chat_id},
            {"$set": update}
        )

    # --- Bundles ---
    async def create_bundle(self, code, file_ids, source_channel, title, original_range, **kwargs):
        # Write to PrivateDB
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
        await self.bundles_col_private.insert_one(doc)

    async def get_bundle(self, code):
        # Try Private First
        doc = await self.bundles_col_private.find_one({"code": code})
        if doc:
            logger.info(f"Bundle query: code={code}, Status: Found in PrivateDB")
            return doc

        # Try Main with Retry
        async def main_query():
            return await self.bundles_col_main.find_one({"code": code})

        doc = await self._safe_main_query(main_query, fallback_val=None)
        if doc:
            logger.info(f"Bundle query: code={code}, Status: Found in MainDB")
            return doc

        logger.info(f"Bundle query: code={code}, Status: Not Found")
        return None

    async def get_all_bundles(self):
        # Returns local bundles mainly for management
        return await self.bundles_col_private.find({}).to_list(length=100)

    async def get_global_bundles_count(self):
        async def main_query():
            return await self.bundles_col_main.count_documents({})
        return await self._safe_main_query(main_query, fallback_val=0)

    async def increment_bundle_views(self, code):
        res = await self.bundles_col_private.update_one({"code": code}, {"$inc": {"views": 1}})
        if res.matched_count == 0:
            # It's a global bundle or non-existent.
            # Cannot write to MainDB (Read-Only).
            pass

    async def update_bundle_title(self, code, new_title):
        res = await self.bundles_col_private.update_one({"code": code}, {"$set": {"title": new_title}})
        if res.matched_count == 0:
             logger.warning(f"Attempted to update Global Bundle {code}. Read-only – use PrivateDB for local.")
             return False
        return True

    async def delete_bundle(self, code):
        res = await self.bundles_col_private.delete_one({"code": code})
        if res.deleted_count == 0:
             # Check if exists in main?
             logger.warning(f"Attempted to delete Global Bundle {code}. Read-only – use PrivateDB for local.")
             return False
        return True

    # --- Requests (Request Bot) ---
    async def mark_request_done(self, tmdb_id, media_type):
        if not tmdb_id: return
        try:
            tid = int(tmdb_id)
        except:
            tid = tmdb_id

        try:
            # Requests collection might be shared/writable or MainDB read-only?
            # UserDB is Shared Read-Write. MainDB is Read-Only.
            # Assuming requests are in MainDB cluster but might be separate DB "xtv_requests".
            # If fail, we catch it.
            await self.requests_col.update_many(
                {"tmdb_id": tid, "type": media_type},
                {"$set": {"status": "done"}}
            )
        except Exception as e:
            logger.warning(f"Failed to mark request done: {e}")

    # --- Tasks ---
    async def add_task(self, question, answer, options=None, task_type="text"):
        # Assume Global/MainDB task list.
        # Safeguard:
        logger.warning("Attempted to add task to MainDB. Read-only.")
        return False
        # If we wanted local tasks, we'd use tasks_col_private (not implemented yet).

    async def get_random_tasks(self, limit=3):
        async def main_query():
            pipeline = [{"$sample": {"size": limit}}]
            cursor = self.tasks_col.aggregate(pipeline)
            return await cursor.to_list(length=limit)
        return await self._safe_main_query(main_query, fallback_val=[])

    async def get_all_tasks(self):
        async def main_query():
            return await self.tasks_col.find({}).to_list(length=1000)
        return await self._safe_main_query(main_query, fallback_val=[])

    async def delete_task(self, question):
        logger.warning("Attempted to delete task from MainDB. Read-only.")
        return False

    # --- Force Share Channels ---
    async def add_share_channel(self, link, text_template):
        # Global? Safeguard.
        logger.warning("Attempted to add share channel to MainDB. Read-only.")
        return False

    async def get_share_channels(self):
        async def main_query():
            return await self.force_shares_col.find({}).to_list(length=100)
        return await self._safe_main_query(main_query, fallback_val=[])

    async def remove_share_channel(self, link):
         logger.warning("Attempted to remove share channel from MainDB. Read-only.")
         return False

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

    async def is_user_banned(self, user_id):
        """Check if a user is globally banned."""
        user = await self.users_col.find_one({"user_id": user_id, "banned": True})
        return True if user else False

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
        # Global coupons? Safeguard? Or local?
        # UserDB stores redeemed. Coupons MainDB?
        # Assume Global for now, read-only.
        logger.warning("Attempted to create coupon in MainDB. Read-only.")
        return False

    async def get_coupon(self, code):
        async def main_query():
            return await self.coupons_col.find_one({"code": code})
        return await self._safe_main_query(main_query, fallback_val=None)

    async def redeem_coupon(self, code, user_id):
        # UserDB Write (OK)
        user = await self.users_col.find_one({"user_id": user_id, "redeemed_coupons": code})
        if user:
            return False, "already_used"

        # Read Coupon (MainDB Safe)
        coupon = await self.get_coupon(code)
        if not coupon:
            return False, "invalid"

        if coupon["used_count"] >= coupon["usage_limit"]:
            return False, "limit_reached"

        # Update Coupon Used Count (MainDB Write) -> Fail
        # This is tricky. If coupons are Global, Franchisee cannot update usage count in MainDB.
        # Solution: "Shared read/write UserDB... coupons for global Premium".
        # Maybe coupons collection should be in UserDB? Or MainDB?
        # If MainDB is STRICT read-only, we cannot increment usage.
        # We try to update, but catch any error and proceed (since user validation passed).
        try:
             await self.coupons_col.update_one({"code": code}, {"$inc": {"used_count": 1}})
        except Exception as e:
             logger.warning(f"Could not increment coupon usage in MainDB (Read-Only): {e}. Proceeding with reward.")

        await self.users_col.update_one(
            {"user_id": user_id},
            {"$push": {"redeemed_coupons": code}},
            upsert=True
        )
        await self.add_premium_user(user_id, coupon["reward_hours"] / 24.0)
        return True, "success"

    async def delete_coupon(self, code):
        logger.warning("Attempted to delete coupon from MainDB. Read-only.")
        return False

    async def get_all_coupons(self):
        async def main_query():
            return await self.coupons_col.find({}).to_list(length=100)
        return await self._safe_main_query(main_query, fallback_val=[])

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
        await self.groups_col_private.insert_one(doc)
        return doc

    async def get_group(self, code):
        doc = await self.groups_col_private.find_one({"code": code})
        if doc: return doc

        async def main_query():
            return await self.groups_col_main.find_one({"code": code})
        async def cache_fallback():
            return await self.cache_groups_col.find_one({"code": code})

        return await self._safe_main_query(main_query, fallback_coro=cache_fallback)

    async def get_group_by_bundle(self, bundle_code):
        doc = await self.groups_col_private.find_one({"bundles": bundle_code})
        if doc: return doc

        async def main_query():
            return await self.groups_col_main.find_one({"bundles": bundle_code})
        async def cache_fallback():
            return await self.cache_groups_col.find_one({"bundles": bundle_code})

        return await self._safe_main_query(main_query, fallback_coro=cache_fallback)

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

        doc = await self.groups_col_private.find_one(query)
        if doc: return doc

        async def main_query():
            return await self.groups_col_main.find_one(query)
        async def cache_fallback():
            return await self.cache_groups_col.find_one(query)

        return await self._safe_main_query(main_query, fallback_coro=cache_fallback)

    async def add_bundle_to_group(self, group_code, bundle_code):
        # Only Private groups
        res = await self.groups_col_private.update_one(
            {"code": group_code},
            {"$addToSet": {"bundles": bundle_code}}
        )
        if res.matched_count == 0:
             logger.warning(f"Attempted to update Global Group {group_code}. Read-only.")
             return False
        return True

    async def remove_bundle_from_group(self, group_code, bundle_code):
        res = await self.groups_col_private.update_one(
            {"code": group_code},
            {"$pull": {"bundles": bundle_code}}
        )
        if res.matched_count == 0:
             logger.warning(f"Attempted to update Global Group {group_code}. Read-only.")
             return False
        return True

    async def update_group_title(self, group_code, new_title):
        res = await self.groups_col_private.update_one(
            {"code": group_code},
            {"$set": {"title": new_title}}
        )
        if res.matched_count == 0:
             logger.warning(f"Attempted to update Global Group {group_code}. Read-only.")
             return False
        return True

    async def delete_group(self, group_code):
        res = await self.groups_col_private.delete_one({"code": group_code})
        if res.deleted_count == 0:
             logger.warning(f"Attempted to delete Global Group {group_code}. Read-only.")
             return False
        return True

    async def get_all_groups(self):
        return await self.groups_col_private.find({}).to_list(length=1000)

db = Database()
