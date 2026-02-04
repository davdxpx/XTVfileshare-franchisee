from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from config import Config
from db import db
from log import get_logger
from utils.tmdb import get_tmdb_details
from plugins.quest import QuestEngine
import asyncio
import time

logger = get_logger(__name__)

# {user_id: {"code": str, "quest": dict}}
user_sessions = {}

# --- Delivery (Moved up for clarity) ---
async def deliver_bundle(client, user_id, chat_id, code):
    bundle = await db.get_bundle(code)
    if not bundle:
        await client.send_message(chat_id, "❌ Bundle not found.")
        return

    # Rate Limit
    allowed, req_count = await db.check_rate_limit(user_id)
    await db.add_request(user_id)
    await db.increment_bundle_views(code)

    files = bundle["file_ids"]

    # Metadata Logic (Same as before)
    tmdb_id = bundle.get("tmdb_id")
    media_type = bundle.get("media_type", "movie")

    if tmdb_id:
        details = get_tmdb_details(tmdb_id, media_type)
        if details:
            rating = details.get("vote_average", 0)
            genres = [g["name"] for g in details.get("genres", [])[:3]]
            genre_text = ", ".join(genres)
            total_size = sum(f.get("file_size", 0) for f in files)
            size_gb = total_size / (1024 * 1024 * 1024)
            size_text = f"{size_gb:.2f} GB" if size_gb >= 1 else f"{total_size / (1024 * 1024):.2f} MB"

            title = details.get("title") or details.get("name")
            date = details.get("release_date") or details.get("first_air_date") or ""
            year = date[:4] if date else "Unknown"
            poster_path = details.get("poster_path")
            poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None
            overview = details.get("overview", "No description.")

            meta_lines = []
            if rating: meta_lines.append(f"⭐️ {round(rating, 1)}/10  🎭 {genre_text}")

            if media_type == "tv" or media_type == "subs":
                season = bundle.get("season")
                eps = bundle.get("episodes_label")
                if season and eps:
                    ep_text = "Complete" if eps == "All" else f"Episodes {eps}"
                    meta_lines.append(f"📺 **Season {season}** • **{ep_text}**")

            quals = bundle.get("qualities", [])
            if quals: meta_lines.append(f"💿 **Quality:** {', '.join(quals)}")
            meta_lines.append(f"💾 **Size:** {size_text}")

            desc_lines = overview.split("\n")
            quoted_desc = "\n".join([f"> {line}" for line in desc_lines if line.strip()])

            caption = (
                f"<u>**{title}**</u> • _({year})_\n"
                f"{str.join('\n', meta_lines)}\n\n"
                f"**💬 Description:**\n"
                f"{quoted_desc}\n\n"
                f"__Enjoy watching!__ 🍿"
            )

            try:
                if poster_url:
                    await client.send_photo(chat_id, poster_url, caption=caption)
                else:
                    await client.send_message(chat_id, caption)
            except Exception:
                await client.send_message(chat_id, caption)

    status_msg = await client.send_message(chat_id, f"✅ Verified! Sending {len(files)} files...")
    for file_data in files:
        try:
            from utils.helpers import generate_random_code
            ext = "." + file_data["file_name"].split(".")[-1] if "." in file_data["file_name"] else ""
            new_name = f"file_{generate_random_code(8)}{ext}"
            await client.send_document(chat_id, file_data["file_id"], caption=None, file_name=new_name, protect_content=True)
            await asyncio.sleep(Config.DEFAULT_DELAY)
        except Exception as e:
            logger.error(f"Send error: {e}")
    await status_msg.delete()
    try:
        await client.send_sticker(chat_id, "CAACAgIAAxkBAAEQa0xpgkMvycmQypya3zZxS5rU8tuKBQACwJ0AAjP9EEgYhDgLPnTykDgE")
    except: pass

    if user_id in user_sessions: del user_sessions[user_id]

# --- Main Logic ---

@Client.on_message(filters.command("start"))
async def start_handler(client: Client, message: Message):
    args = message.command
    if len(args) < 2:
        await message.reply("👋 Welcome!")
        return

    code = args[1]
    user_id = message.from_user.id

    # Check Rate Limit
    allowed, count = await db.check_rate_limit(user_id)
    if not allowed:
        await message.reply(f"❌ Rate limit exceeded. {Config.RATE_LIMIT_BUNDLES} bundles / 2h.")
        return

    bundle = await db.get_bundle(code)
    if not bundle:
        await message.reply("❌ Invalid link.")
        return

    # Generate Quest
    msg = await message.reply("⏳ Calculating requirements...")
    quest = await QuestEngine.generate_quest(user_id, bundle, client)
    await msg.delete()

    user_sessions[user_id] = {"code": code, "quest": quest}
    await process_quest_step(client, user_id, message.chat.id)

async def process_quest_step(client, user_id, chat_id):
    session = user_sessions.get(user_id)
    if not session: return

    quest = session["quest"]
    idx = quest["current_index"]
    steps = quest["steps"]
    counts = quest["counts"]

    if idx >= len(steps):
        # Done
        await deliver_bundle(client, user_id, chat_id, session["code"])
        return

    step = steps[idx]
    stype = step["type"]

    # Progress Header
    # "🧩 Task 1/2 • Subs 0/2 • Share 0/1"
    # We need to count how many of each type passed
    # This is complex to calc dynamic "passed", simpler to just show static totals?
    # User said: "Task 1/6 • F-Subs 0/1" (Meaning current step / total of that type).
    # We iterate steps to find counts.

    done_counts = {"task": 0, "sub": 0, "share": 0}
    for i in range(idx):
        t = steps[i]["type"]
        done_counts[t] += 1

    # Current step is logically "in progress", so maybe +1 to done?
    # Usually "1/2" means "Doing 1 of 2".

    current_counts = {k: v + 1 if k == stype else v for k,v in done_counts.items()}
    # Cap at max
    for k in current_counts:
        if current_counts[k] > counts[k]: current_counts[k] = counts[k]

    header_parts = []
    if counts["task"] > 0: header_parts.append(f"🧩 Task {current_counts['task']}/{counts['task']}")
    if counts["sub"] > 0: header_parts.append(f"🔒 Subs {current_counts['sub']}/{counts['sub']}")
    if counts["share"] > 0: header_parts.append(f"📢 Share {current_counts['share']}/{counts['share']}")

    header = " • ".join(header_parts)

    # Render Step
    if stype == "task":
        data = step["data"]
        q = data["question"]
        opts = data.get("options", [])
        markup = []
        if opts:
            btns = [InlineKeyboardButton(o, callback_data=f"q_ans|{o}") for o in opts]
            markup = [btns[i:i+2] for i in range(0, len(btns), 2)]

        markup.append([InlineKeyboardButton("⏭ Skip (Wait 20s)", callback_data="q_skip")])

        text = f"**{header}**\n\n{q}"
        if not opts: text += "\n\n__Send answer below.__"

        await client.send_message(chat_id, text, reply_markup=InlineKeyboardMarkup(markup))

    elif stype == "sub":
        ch = step["channel"]
        link = ch["link"] or f"https://t.me/{ch.get('username')}" # Fallback

        text = f"**{header}**\n\nPlease join this channel to continue."
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"Join {ch.get('title')}", url=link)],
            [InlineKeyboardButton("✅ I Joined", callback_data="sub_check")]
        ])
        await client.send_message(chat_id, text, reply_markup=markup)

    elif stype == "share":
        # Get data from step
        share_data = step.get("data", {})
        share_link = share_data.get("link") or f"https://t.me/{Config.BOT_USERNAME}"
        raw_text = share_data.get("text") or "Check this out! {channel_link}"

        final_text = raw_text.replace("{channel_link}", share_link)

        from urllib.parse import quote
        safe_text = quote(final_text)
        share_url = f"https://t.me/share/url?text={safe_text}"

        text = (
            f"**{header}**\n\n"
            "🔄 **Force Share Required**\n\n"
            "1. Click the **Share** button below and send to 5 contacts.\n"
            "2. Click **Verify** when done."
        )

        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("↗️ Share to Friends", url=share_url)],
            [InlineKeyboardButton("✅ Verify", callback_data="share_verify_fake")]
        ])

        await client.send_message(chat_id, text, reply_markup=markup)

# --- Handlers ---

@Client.on_callback_query(filters.regex(r"^q_ans\|"))
async def quest_ans(client, callback):
    user_id = callback.from_user.id
    if user_id not in user_sessions:
        await callback.answer("Expired.")
        return

    ans = callback.data.split("|", 1)[1]
    session = user_sessions[user_id]
    step = session["quest"]["steps"][session["quest"]["current_index"]]

    if step["type"] != "task": return

    correct = step["data"]["answer"]
    if ans.lower() == correct.lower():
        await callback.answer("✅ Correct!")
        await callback.message.delete()
        session["quest"]["current_index"] += 1
        await process_quest_step(client, user_id, callback.message.chat.id)
    else:
        await callback.answer("❌ Wrong!", show_alert=True)

@Client.on_callback_query(filters.regex(r"^q_skip$"))
async def quest_skip(client, callback):
    # Check time (mock for now, or rely on client side wait? No, server check)
    msg_date = callback.message.date.timestamp()
    if time.time() - msg_date < 20:
        await callback.answer("Wait 20s!", show_alert=True)
        return

    user_id = callback.from_user.id
    if user_id in user_sessions:
        user_sessions[user_id]["quest"]["current_index"] += 1
        await callback.message.delete()
        await process_quest_step(client, user_id, callback.message.chat.id)

@Client.on_message(filters.text & ~filters.command(["start", "create_link", "admin", "cancel"]), group=2)
async def quest_text_handler(client, message):
    user_id = message.from_user.id
    if user_id not in user_sessions: return

    session = user_sessions[user_id]
    idx = session["quest"]["current_index"]
    if idx >= len(session["quest"]["steps"]): return

    step = session["quest"]["steps"][idx]

    if step["type"] == "task":
        correct = step["data"]["answer"]
        if message.text.strip().lower() == correct.lower():
            await message.reply("✅ Correct!")
            session["quest"]["current_index"] += 1
            await process_quest_step(client, user_id, message.chat.id)
        else:
            await message.reply("❌ Wrong answer.")

@Client.on_callback_query(filters.regex(r"^sub_check$"))
async def sub_check_handler(client, callback):
    user_id = callback.from_user.id
    if user_id not in user_sessions: return

    session = user_sessions[user_id]
    idx = session["quest"]["current_index"]
    step = session["quest"]["steps"][idx]

    if step["type"] != "sub": return

    ch_id = step["channel"]["id"]
    try:
        # Robust check
        try: await client.get_chat(ch_id)
        except: pass

        member = await client.get_chat_member(ch_id, user_id)
        if member.status not in ["left", "kicked", "banned"]:
            # Success
            await callback.answer("✅ Verified!")
            await callback.message.delete()
            session["quest"]["current_index"] += 1
            await process_quest_step(client, user_id, callback.message.chat.id)
            return
    except Exception as e:
        logger.warning(f"Sub check fail: {e}")

    await callback.answer("❌ You are not in the channel yet! (Or bot cannot verify)", show_alert=True)

@Client.on_callback_query(filters.regex(r"^share_verify_fake$"))
async def share_verify_fake(client, callback):
    user_id = callback.from_user.id
    if user_id not in user_sessions: return

    # Show loading state
    try:
        await callback.edit_message_reply_markup(
            InlineKeyboardMarkup([[InlineKeyboardButton("⏳ Verifying...", callback_data="noop")]])
        )
    except: pass

    # Fake Check delay
    await asyncio.sleep(10)

    # Success
    session = user_sessions[user_id]
    session["quest"]["current_index"] += 1

    await callback.edit_message_text("✅ **Share Verified!**")
    await process_quest_step(client, user_id, callback.message.chat.id)
