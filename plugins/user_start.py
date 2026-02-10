import html
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.enums import ParseMode
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

    # Metadata Logic
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

            # Fetch data and escape for HTML safety
            raw_title = details.get("title") or details.get("name")
            title = html.escape(raw_title) if raw_title else "Unknown"

            date = details.get("release_date") or details.get("first_air_date") or ""
            year = date[:4] if date else "Unknown"

            poster_path = details.get("poster_path")
            poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None

            raw_overview = details.get("overview", "No description.")
            overview = html.escape(raw_overview)

            meta_lines = []
            if rating: meta_lines.append(f"⭐️ {round(rating, 1)}/10  🎭 {genre_text}")

            if media_type == "tv" or media_type == "subs":
                season = bundle.get("season")
                eps = bundle.get("episodes_label")
                if season and eps:
                    ep_text = "Complete" if eps == "All" else f"Episodes {eps}"
                    # HTML Tags instead of Markdown (** -> <b>)
                    meta_lines.append(f"📺 <b>Season {season}</b> • <b>{ep_text}</b>")

            quals = bundle.get("qualities", [])
            if quals:
                meta_lines.append(f"💿 <b>Quality:</b> {', '.join(quals)}")
            meta_lines.append(f"💾 <b>Size:</b> {size_text}")

            # Use HTML Blockquote
            quoted_desc = f"<blockquote>{overview}</blockquote>"

            caption = (
                f"<u><b>{title}</b></u> • <i>({year})</i>\n"
                f"{str.join('\n', meta_lines)}\n\n"
                f"<b>💬 Description:</b>\n"
                f"{quoted_desc}\n\n"
                f"<i>Enjoy watching!</i> 🍿"
            )

            try:
                if poster_url:
                    await client.send_photo(chat_id, poster_url, caption=caption, parse_mode=ParseMode.HTML)
                else:
                    await client.send_message(chat_id, caption, parse_mode=ParseMode.HTML)
            except Exception as e:
                logger.error(f"Error sending metadata: {e}")
                # Fallback if something goes wrong
                await client.send_message(chat_id, caption, parse_mode=ParseMode.HTML)

    status_msg = await client.send_message(chat_id, f"✅ Verified! Sending {len(files)} files...")
    sent_msgs = []
    for file_data in files:
        try:
            from utils.helpers import generate_random_code
            ext = "." + file_data["file_name"].split(".")[-1] if "." in file_data["file_name"] else ""
            new_name = f"file_{generate_random_code(8)}{ext}"
            msg = await client.send_document(chat_id, file_data["file_id"], caption=None, file_name=new_name, protect_content=True)
            sent_msgs.append(msg.id)
            await asyncio.sleep(Config.DEFAULT_DELAY)
        except Exception as e:
            logger.error(f"Send error: {e}")
    await status_msg.delete()

    # Auto Delete
    auto_del_mins = await db.get_config("auto_delete_time", 0)
    if auto_del_mins > 0 and sent_msgs:
        delete_at = time.time() + (auto_del_mins * 60)
        await db.add_to_delete_queue(chat_id, sent_msgs, delete_at)
        await client.send_message(chat_id, f"⚠️ **Attention!** These files will self-destruct in **{auto_del_mins} minutes**!")

    try:
        await client.send_sticker(chat_id, "CAACAgIAAxkBAAEQa0xpgkMvycmQypya3zZxS5rU8tuKBQACwJ0AAjP9EEgYhDgLPnTykDgE")
    except: pass

    if user_id in user_sessions: del user_sessions[user_id]

# --- Main Logic ---

@Client.on_message(filters.command("start"))
async def start_handler(client: Client, message: Message):
    args = message.command
    user_id = message.from_user.id

    if len(args) < 2:
        await message.reply("👋 Welcome!")
        return

    code = args[1]

    # --- Referral Logic ---
    if code.startswith("ref_"):
        try:
            referrer_id = int(code.split("_")[1])
            if referrer_id != user_id:
                # Set referrer
                if await db.set_referrer(user_id, referrer_id):
                    # Increment count
                    new_count = await db.increment_referral(referrer_id)
                    # Check Target
                    target = await db.get_config("referral_target", 10)
                    if new_count >= target:
                        # Grant Reward
                        reward_hours = await db.get_config("referral_reward_hours", 24)
                        await db.add_premium_user(referrer_id, reward_hours / 24.0)
                        try:
                            await client.send_message(referrer_id, f"🎉 You invited {target} users! You received {reward_hours}h Premium Access!")
                        except: pass
            await message.reply("👋 Welcome! You have been referred to the bot.")
        except Exception as e:
            logger.error(f"Ref error: {e}")
            await message.reply("👋 Welcome!")
        return
    # ----------------------

    # Check Rate Limit
    # Premium users bypass rate limit? Usually yes.
    is_premium = await db.is_premium_user(user_id)

    if not is_premium:
        allowed, count = await db.check_rate_limit(user_id)
        if not allowed:
            await message.reply(f"❌ Rate limit exceeded. {Config.RATE_LIMIT_BUNDLES} bundles / 2h.")
            return

    bundle = await db.get_bundle(code)
    if not bundle:
        await message.reply("❌ Invalid link.")
        return

    # Premium Skip Logic
    if is_premium:
        await message.reply("🌟 **Premium User Detected!** Bypassing Quest...")
        await deliver_bundle(client, user_id, message.chat.id, code)
        return

    # Generate Quest
    msg = await message.reply("⏳ Calculating requirements...")
    quest = await QuestEngine.generate_quest(user_id, bundle, client)
    await msg.delete()

    user_sessions[user_id] = {"code": code, "quest": quest}
    await process_quest_step(client, user_id, message.chat.id)

@Client.on_message(filters.command(["referral", "invite"]))
async def referral_command(client, message):
    user_id = message.from_user.id
    bot_username = Config.BOT_USERNAME

    count = await db.get_referral_count(user_id)
    target = await db.get_config("referral_target", 10)
    reward_hours = await db.get_config("referral_reward_hours", 24)

    link = f"https://t.me/{bot_username}?start=ref_{user_id}"

    text = (
        f"**🚀 Invite Friends & Earn Premium!**\n\n"
        f"Invite **{target}** users to get **{reward_hours}h Premium Access** (skip all quests).\n\n"
        f"📊 **Your Progress:** `{count}/{target}`\n\n"
        f"🔗 **Your Link:**\n`{link}`\n\n"
        f"__Share this link with your friends!__"
    )

    from urllib.parse import quote
    share_text = quote("Check out this awesome bot!")
    share_url = f"https://t.me/share/url?url={link}&text={share_text}"
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("↗️ Share Link", url=share_url)]])

    await message.reply(text, reply_markup=markup)

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
            "🔄 **Share Required**\n\n"
            "1. Click the **Share** button below and send to 5 contacts.\n"
            "2. Click **Verify** when done."
        )

        markup_share = InlineKeyboardMarkup([
            [InlineKeyboardButton("↗️ Share to Friends", url=share_url)]
        ])

        markup_verify = InlineKeyboardMarkup([
            [InlineKeyboardButton("↗️ Share to Friends", url=share_url)],
            [InlineKeyboardButton("✅ Verify", callback_data="share_verify_fake")]
        ])

        msg = await client.send_message(chat_id, text, reply_markup=markup_share)

        # Delayed appearance of Verify button
        # Run in background task to avoid blocking?
        # process_quest_step is async, but we want to return.
        asyncio.create_task(delayed_verify_button(msg, markup_verify))

async def delayed_verify_button(message, markup):
    await asyncio.sleep(5)
    try:
        await message.edit_reply_markup(reply_markup=markup)
    except Exception as e:
        logger.warning(f"Failed to update share markup: {e}")

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
