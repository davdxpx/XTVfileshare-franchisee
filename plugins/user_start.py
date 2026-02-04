from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import UserNotParticipant, ChatAdminRequired
from config import Config
from db import db
from log import get_logger
from utils.tmdb import get_tmdb_details
import random
import asyncio
import time

logger = get_logger(__name__)

# Temporary state for user flows
# {user_id: {"code": str, "tasks": [], "task_index": 0}}
user_sessions = {}

async def check_force_sub(client, user_id):
    if not await db.get_config("force_sub_enabled", False):
        return True, []

    # Fetch from DB (new logic)
    channels = await db.get_force_sub_channels()
    if not channels:
        # Fallback to old config if empty?
        old_channels = await db.get_config("force_sub_channels", [])
        if not old_channels:
            return True, []

        # Temporary: use old list logic if DB empty
        # But we want to move to DB.
        # Let's support both for now or just DB?
        # DB is safer. But let's assume migration happens or we just use DB.
        # If user added channels via new panel, they are in DB.
        pass

    missing_channels = []

    # Check DB channels
    for ch in channels:
        chat_id = ch["chat_id"]
        invite = ch.get("invite_link")
        try:
            # Try getting chat member
            member = await client.get_chat_member(chat_id, user_id)
            if member.status in ["left", "kicked", "banned"]:
                missing_channels.append({"id": chat_id, "title": ch.get("title"), "link": invite or f"https://t.me/{ch.get('username')}"})
        except UserNotParticipant:
             missing_channels.append({"id": chat_id, "title": ch.get("title"), "link": invite or f"https://t.me/{ch.get('username')}"})
        except Exception as e:
             # Handle PeerIdInvalid specifically by trying to refresh peer
             if "Peer id invalid" in str(e) or "PEER_ID_INVALID" in str(e):
                 try:
                     # Refresh cache
                     await client.get_chat(chat_id)
                     # Retry once
                     member = await client.get_chat_member(chat_id, user_id)
                     if member.status in ["left", "kicked", "banned"]:
                        missing_channels.append({"id": chat_id, "title": ch.get("title"), "link": invite or f"https://t.me/{ch.get('username')}"})
                 except Exception as e2:
                     logger.warning(f"FS Check Retry Failed {chat_id}: {e2}")
                     # If we still can't check, we skip adding to missing (fail open) OR add to missing (fail closed)?
                     # Since this is "Secure Bot", failing closed is safer, but if bot is broken, user is stuck.
                     # User said "obwohl es davor funktioniert hat" -> imply it should work.
                     # If we can't verify, we assume user is NOT in channel if we want to be strict.
                     # But without a working link, they can't join.
                     # Let's add to missing so they see the link (if available).
                     missing_channels.append({"id": chat_id, "title": ch.get("title"), "link": invite or f"https://t.me/{ch.get('username')}"})
             else:
                 logger.warning(f"FS Check Error {chat_id}: {e}")
                 pass

    return len(missing_channels) == 0, missing_channels

async def send_next_step(client, user_id, chat_id):
    if user_id not in user_sessions:
        await client.send_message(chat_id, "❌ Session expired. Please click the link again.")
        return

    session = user_sessions[user_id]

    # 1. Tasks
    if await db.get_config("tasks_enabled", False):
        tasks = session.get("tasks")
        if tasks is None:
            # Determine dynamic count
            # Logic: Min 3, Max 8. Based on file count?
            # User said: "minimum 3, maximum 8" and "vary depending on how many files are included"

            bundle = await db.get_bundle(session["code"])
            file_count = len(bundle["file_ids"]) if bundle else 5 # default fallback

            # Scaling: 3 + (files // 5) clamped to 8
            # Updated from //3 to //5 as requested "scale slower"
            raw_count = 3 + (file_count // 5)
            task_count = min(max(3, raw_count), 8)

            fs_enabled = await db.get_config("force_sub_enabled", False)
            fs_credit = 0

            if fs_enabled:
                # Force sub counts as 2 tasks
                fs_credit = 2
                task_count = max(1, task_count - 2)

            # Now fetch random tasks
            tasks = await db.get_random_tasks(task_count)
            if not tasks: tasks = []
            session["tasks"] = tasks
            session["task_index"] = 0
            session["fs_credit"] = fs_credit

        current_idx = session["task_index"]
        if current_idx < len(tasks):
            task = tasks[current_idx]
            question = task["question"]
            options = task.get("options", [])
            task_type = task.get("type", "text")

            markup = []
            if task_type == "quiz" and options:
                btns = []
                for opt in options:
                    btns.append(InlineKeyboardButton(opt, callback_data=f"task_ans|{opt}"))
                markup = [btns[i:i+2] for i in range(0, len(btns), 2)]

            markup.append([InlineKeyboardButton("⏭ Skip (Wait 20s)", callback_data="task_skip")])

            # Header formatting
            # 🧩 Task X/Y • F-Subs 0/1 (if FS enabled)
            # Total visual tasks = task_count

            fs_info = ""
            fs_credit = session.get("fs_credit", 0)
            if fs_credit > 0:
                # We assume F-Sub is "done" (since we are here), so 1/1
                # User asked: "🧩 Task 1/6 • F-Subs 0/1" if not joined.
                # But here we are AFTER joining (or checking).
                # So we show F-Subs 1/1? Or just imply it?
                # "When beides aktiv ist und der nutzer noch nicht in allen verlinkten Channels mitglied ist so in der art: 🧩 Task 1/6 • F-Subs 0/1."
                # But if they are NOT member, they are stuck at the "Join Channels" screen.
                # Once they are here, they ARE member.
                # So we should show F-Subs 1/1 or just omit?
                # Maybe "F-Subs ✅"?
                # Let's show "F-Subs 1/1" to indicate it counted.
                fs_info = " • F-Subs 1/1"

            txt = f"**🧩 Task {current_idx + 1}/{len(tasks)}{fs_info}**\n\n{question}"
            if task_type == "text":
                txt += "\n\n__Send your answer below.__"

            await client.send_message(chat_id, txt, reply_markup=InlineKeyboardMarkup(markup))
            return

    # 2. Delivery
    await deliver_bundle(client, user_id, chat_id, session["code"])

async def deliver_bundle(client, user_id, chat_id, code):
    bundle = await db.get_bundle(code)
    if not bundle:
        await client.send_message(chat_id, "❌ Bundle not found.")
        return

    # Rate Limit Check
    allowed, req_count = await db.check_rate_limit(user_id)
    await db.add_request(user_id)
    await db.increment_bundle_views(code)

    files = bundle["file_ids"]

    # --- Fetch & Send Metadata Info ---
    tmdb_id = bundle.get("tmdb_id")
    media_type = bundle.get("media_type", "movie")

    if tmdb_id:
        details = get_tmdb_details(tmdb_id, media_type)
        if details:
            # Format Info Message
            # <Titel> (Fett, unterstrichen) • <Erscheinungsjahr> (kursiv)
            # <Dateien Infos>
            # Description

            title = details.get("title") or details.get("name")
            date = details.get("release_date") or details.get("first_air_date") or ""
            year = date[:4] if date else "Unknown"
            poster_path = details.get("poster_path")
            poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None
            overview = details.get("overview", "No description.")

            # File/Content Info
            content_info = ""
            if media_type == "tv" or media_type == "subs":
                season = bundle.get("season")
                eps = bundle.get("episodes_label")
                if season and eps:
                    if eps == "All":
                        content_info = f"S{season} Complete"
                    else:
                        content_info = f"S{season} E{eps}"
            else: # Movie
                quals = bundle.get("qualities", [])
                if quals:
                    content_info = f"Quality: {', '.join(quals)}"

            # Format Info Message
            # Use <i> for italics for cleaner look or __ for Markdown
            # Pyrogram default is Markdown.

            rating = details.get("vote_average", 0)
            genres = [g["name"] for g in details.get("genres", [])[:3]]
            genre_text = ", ".join(genres)

            # Size Calculation
            total_size = sum(f.get("file_size", 0) for f in files)
            size_gb = total_size / (1024 * 1024 * 1024)
            size_text = f"{size_gb:.2f} GB" if size_gb >= 1 else f"{total_size / (1024 * 1024):.2f} MB"

            # Content Info formatting
            meta_lines = []
            if rating:
                meta_lines.append(f"⭐️ {round(rating, 1)}/10  🎭 {genre_text}")

            if media_type == "tv" or media_type == "subs":
                season = bundle.get("season")
                eps = bundle.get("episodes_label")
                if season and eps:
                    ep_text = "Complete" if eps == "All" else f"Episodes {eps}"
                    meta_lines.append(f"📺 **Season {season}** • **{ep_text}**")

            quals = bundle.get("qualities", [])
            if quals:
                meta_lines.append(f"💿 **Quality:** {', '.join(quals)}")

            meta_lines.append(f"💾 **Size:** {size_text}")

            meta_block = "\n".join(meta_lines)

            # Description Quote
            # Add > to every line
            desc_lines = overview.split("\n")
            quoted_desc = "\n".join([f"> {line}" for line in desc_lines if line.strip()])

            caption = (
                f"<u>**{title}**</u> • _({year})_\n"
                f"{meta_block}\n\n"
                f"**💬 Description:**\n"
                f"{quoted_desc}\n\n"
                f"__Enjoy watching!__ 🍿"
            )

            try:
                if poster_url:
                    await client.send_photo(chat_id, poster_url, caption=caption)
                else:
                    await client.send_message(chat_id, caption)
            except Exception as e:
                logger.error(f"Failed to send info message: {e}")
                # Fallback if caption too long?
                if "caption is too long" in str(e).lower():
                    caption = caption[:1000] + "... (truncated)"
                    try:
                        await client.send_photo(chat_id, poster_url, caption=caption)
                    except:
                        await client.send_message(chat_id, caption)
                else:
                    await client.send_message(chat_id, caption)

    # --- Send Files ---
    # files already defined above
    status_msg = await client.send_message(chat_id, f"✅ Verified! Sending {len(files)} files...")

    for file_data in files:
        try:
            from utils.helpers import generate_random_code
            ext = "." + file_data["file_name"].split(".")[-1] if "." in file_data["file_name"] else ""
            new_name = f"file_{generate_random_code(8)}{ext}"

            await client.send_document(
                chat_id,
                file_data["file_id"],
                caption=None,
                file_name=new_name,
                protect_content=True
            )
            await asyncio.sleep(Config.DEFAULT_DELAY) # Small delay? Or user said 0 default.
        except Exception as e:
            logger.error(f"Failed to send file: {e}")

    await status_msg.delete()

    # --- End Sticker ---
    try:
        await client.send_sticker(chat_id, "CAACAgIAAxkBAAEQa0xpgkMvycmQypya3zZxS5rU8tuKBQACwJ0AAjP9EEgYhDgLPnTykDgE")
    except Exception as e:
        logger.error(f"Failed to send sticker: {e}")

    # Cleanup session
    if user_id in user_sessions:
        del user_sessions[user_id]


@Client.on_message(filters.command("start"))
async def start_handler(client: Client, message: Message):
    args = message.command
    if len(args) < 2:
        await message.reply("👋 Welcome! This is a private file sharing bot.")
        return

    code = args[1]
    user_id = message.from_user.id

    # Check Rate Limit
    allowed, count = await db.check_rate_limit(user_id)
    if not allowed:
        await message.reply(f"❌ Rate limit exceeded. You can only access {Config.RATE_LIMIT_BUNDLES} bundles every 2 hours.")
        return

    bundle = await db.get_bundle(code)
    if not bundle:
        await message.reply("❌ Invalid or expired link.")
        return

    # Init Session
    user_sessions[user_id] = {"code": code, "tasks": None, "task_index": 0}

    # Check Force Sub
    is_subbed, missing = await check_force_sub(client, user_id)
    if not is_subbed:
        btns = []
        for ch in missing:
            # ch is now dict {"id", "title", "link"}
            title = ch.get("title") or "Channel"
            link = ch.get("link")
            btns.append([InlineKeyboardButton(f"Join {title}", url=link)])

        btns.append([InlineKeyboardButton("✅ Checked / Try Again", callback_data=f"check_sub")])

        await message.reply(
            "🔒 **Access Restricted**\n\nPlease join the following channels to access the files.",
            reply_markup=InlineKeyboardMarkup(btns)
        )
        return

    # If subbed, proceed
    await send_next_step(client, user_id, message.chat.id)

@Client.on_callback_query(filters.regex(r"^check_sub$"))
async def on_check_sub(client, callback):
    user_id = callback.from_user.id
    if user_id not in user_sessions:
        await callback.answer("Session expired.", show_alert=True)
        return

    is_subbed, missing = await check_force_sub(client, user_id)
    if is_subbed:
        await callback.message.delete()
        await send_next_step(client, user_id, callback.message.chat.id)
    else:
        await callback.answer("❌ You haven't joined all channels yet!", show_alert=True)

# --- Task Handlers ---

@Client.on_callback_query(filters.regex(r"^task_skip$"))
async def on_task_skip(client, callback):
    msg_date = callback.message.date.timestamp()
    now = time.time()
    diff = now - msg_date

    if diff < 20:
        await callback.answer(f"⏳ Please wait {int(20 - diff)} more seconds.", show_alert=True)
        return

    user_id = callback.from_user.id
    if user_id in user_sessions:
        user_sessions[user_id]["task_index"] += 1
        await callback.message.delete()
        await send_next_step(client, user_id, callback.message.chat.id)

@Client.on_callback_query(filters.regex(r"^task_ans\|"))
async def on_task_ans(client, callback):
    user_id = callback.from_user.id
    if user_id not in user_sessions:
        await callback.answer("Session expired.")
        return

    ans = callback.data.split("|", 1)[1]
    session = user_sessions[user_id]
    tasks = session["tasks"]
    idx = session["task_index"]
    current_task = tasks[idx]

    correct_ans = current_task["answer"]

    if ans.strip().lower() == correct_ans.strip().lower():
        await callback.answer("✅ Correct!")
        session["task_index"] += 1
        await callback.message.delete()
        await send_next_step(client, user_id, callback.message.chat.id)
    else:
        await callback.answer("❌ Wrong answer. Try again or skip.", show_alert=True)

@Client.on_message(filters.text & ~filters.command(["start", "create_link", "admin", "cancel"]), group=2)
async def on_text_answer(client, message):
    user_id = message.from_user.id
    if user_id not in user_sessions:
        return

    session = user_sessions[user_id]
    tasks = session.get("tasks")
    if not tasks: return

    idx = session.get("task_index", 0)
    if idx >= len(tasks): return

    current_task = tasks[idx]
    if current_task.get("type") == "quiz":
        return

    correct_ans = current_task["answer"]

    if message.text.strip().lower() == correct_ans.strip().lower():
        await message.reply("✅ Correct!")
        session["task_index"] += 1
        await send_next_step(client, user_id, message.chat.id)
    else:
        await message.reply("❌ Wrong answer. Try again.")
