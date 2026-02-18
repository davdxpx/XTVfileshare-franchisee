from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.enums import ParseMode
import asyncio
import html
import re
from config import Config
from db import db
from log import get_logger
from utils.tmdb import search_tmdb, get_tmdb_details
from utils.states import pending_series_setups, series_wizard_states

logger = get_logger(__name__)

# --- Menu ---

@Client.on_callback_query(filters.regex(r"^admin_series_menu$"))
async def admin_series_menu(client, callback):
    text = "**📺 Series Channels Management**\n\nManage local series channels here."
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 List Series Channels", callback_data="list_series_channels")],
        [InlineKeyboardButton("➕ Add Series Channel (Manual)", callback_data="add_series_start")],
        [InlineKeyboardButton("🔙 Back", callback_data="admin_channels_menu")]
    ])
    await callback.edit_message_text(text, reply_markup=markup)

# --- List Channels ---

@Client.on_callback_query(filters.regex(r"^list_series_channels$"))
async def list_series_channels(client, callback):
    channels = await db.get_series_channels()
    if not channels:
        await callback.answer("No series channels found.", show_alert=True)
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Add Series Channel", callback_data="add_series_start")],
            [InlineKeyboardButton("🔙 Back", callback_data="admin_series_menu")]
        ])
        # Try edit or send
        try: await callback.edit_message_text("No series channels found.", reply_markup=markup)
        except: await callback.message.reply("No series channels found.", reply_markup=markup)
        return

    markup = []
    for ch in channels[:20]:
        title = ch.get("title", "Untitled")
        chat_id = ch.get("chat_id")
        markup.append([InlineKeyboardButton(f"{title}", callback_data=f"view_series_ch|{chat_id}")])

    markup.append([InlineKeyboardButton("🔙 Back", callback_data="admin_series_menu")])
    await callback.edit_message_text("**📺 Local Series Channels:**", reply_markup=InlineKeyboardMarkup(markup))

@Client.on_callback_query(filters.regex(r"^view_series_ch\|"))
async def view_series_channel(client, callback):
    chat_id = int(callback.data.split("|")[1])
    channel = await db.channels_col_private.find_one({"chat_id": chat_id, "type": "series"})

    if not channel:
        await callback.answer("Channel not found.", show_alert=True)
        await list_series_channels(client, callback)
        return

    title = channel.get("title")
    tmdb_id = channel.get("tmdb_id", "N/A")
    username = channel.get("username")
    link = f"@{username}" if username else f"ID: {chat_id}"

    text = (
        f"**📺 Series Channel**\n\n"
        f"Title: `{title}`\n"
        f"Link: {link}\n"
        f"TMDb ID: `{tmdb_id}`"
    )

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Refresh Channel", callback_data=f"refresh_series_ch|{chat_id}")],
        [InlineKeyboardButton("🗑 Delete Channel", callback_data=f"del_series_ch|{chat_id}")],
        [InlineKeyboardButton("🔙 Back", callback_data="list_series_channels")]
    ])
    await callback.edit_message_text(text, reply_markup=markup)

@Client.on_callback_query(filters.regex(r"^del_series_ch\|"))
async def delete_series_channel_handler(client, callback):
    chat_id = int(callback.data.split("|")[1])
    await db.remove_channel(chat_id)
    await callback.answer("Channel deleted from DB (Files remain).", show_alert=True)
    await list_series_channels(client, callback)

@Client.on_callback_query(filters.regex(r"^refresh_series_ch\|"))
async def refresh_series_channel_handler(client, callback):
    chat_id = int(callback.data.split("|")[1])
    await callback.answer("Refreshing...", show_alert=False)
    await refresh_series_channel(client, chat_id, update_text="🔄 Channel Refreshed!")
    try: await callback.message.delete()
    except: pass
    await view_series_channel(client, callback) # Re-show menu

# --- Add Wizard ---

@Client.on_callback_query(filters.regex(r"^add_series_start$"))
async def add_series_start(client, callback):
    series_wizard_states[callback.from_user.id] = {"state": "wait_series_search", "data": {}}
    await callback.message.delete()
    await client.send_message(
        callback.from_user.id,
        "**➕ Add Series Channel**\n\n"
        "First, **search for the TV Series** (TMDb).\n"
        "Send the series name:"
    )

@Client.on_message(filters.user(list(Config.ADMIN_IDS)) & filters.text & ~filters.command(["admin", "cancel"]), group=1)
async def series_wizard_input(client, message):
    user_id = message.from_user.id
    if user_id not in series_wizard_states:
        return

    state_obj = series_wizard_states[user_id]
    state = state_obj["state"]

    if state == "wait_series_search":
        query = message.text.strip()
        results = await search_tmdb(query, "tv")
        if not results:
            await message.reply("❌ No results found. Try again:")
            return

        markup = []
        for r in results[:5]:
            title = r.get("name") or r.get("original_name")
            year = (r.get("first_air_date") or "")[:4]
            tid = r["id"]
            markup.append([InlineKeyboardButton(f"{title} ({year})", callback_data=f"sel_ser|{tid}")])

        markup.append([InlineKeyboardButton("❌ Cancel", callback_data="admin_series_menu")])

        series_wizard_states[user_id] = {"state": "wait_series_select", "data": {}}
        await message.reply("🔍 **Select Series:**", reply_markup=InlineKeyboardMarkup(markup))
        return

    if state == "wait_series_channel_id":
        txt = message.text.strip()
        chat_id = None
        username = None

        if txt.lstrip("-").isdigit():
            chat_id = int(txt)
        elif txt.startswith("@"):
            username = txt
            try:
                chat = await client.get_chat(username)
                chat_id = chat.id
            except: pass
        else:
            await message.reply("❌ Invalid format. Send ID (e.g. -100...) or Username (@...).")
            return

        tmdb_id = state_obj["data"]["tmdb_id"]
        key = chat_id if chat_id else username.lower()

        pending_series_setups[key] = {
            "tmdb_id": tmdb_id,
            "media_type": "tv",
            "user_id": user_id,
            "username": username
        }

        del series_wizard_states[user_id]

        await message.reply(
            "✅ **Step 2: Add Bot as Admin**\n\n"
            f"Target: `{key}`\n"
            "Series TMDb: `{tmdb_id}`\n\n"
            "👉 **Go to that channel NOW and add this bot as Administrator.**\n"
            "The bot will automatically detect it and set up the channel.\n"
            "__(Waiting up to 10 minutes...)__"
        )
        return

@Client.on_callback_query(filters.regex(r"^sel_ser\|"))
async def select_series_callback(client, callback):
    tmdb_id = int(callback.data.split("|")[1])
    user_id = callback.from_user.id

    if user_id in series_wizard_states:
        series_wizard_states[user_id] = {"state": "wait_series_channel_id", "data": {"tmdb_id": tmdb_id}}

        await callback.message.delete()
        await client.send_message(
            user_id,
            f"✅ Selected TMDb ID: `{tmdb_id}`\n\n"
            "**Now send the Channel ID** (or Username) where you want to create the series channel.\n"
            "__(Make sure it's a fresh channel!)__"
        )

# --- Helper: Build Markup ---

async def build_series_markup(tmdb_id):
    groups = await db.groups_col_private.find({"tmdb_id": str(tmdb_id)}).to_list(length=100)

    def sort_key(g):
        s = g.get("season")
        if s is None: s = 9999
        return s
    sorted_groups = sorted(groups, key=sort_key)

    buttons = []
    q_regex = re.compile(r"(480p|720p|1080p|2160p|4k)", re.IGNORECASE)

    for grp in sorted_groups:
        season = grp.get("season")
        ep_label = grp.get("episode_val")
        b_codes = grp.get("bundles", [])
        qualities_set = set()

        if b_codes:
            bundles_cursor = db.bundles_col_private.find({"code": {"$in": b_codes}})
            async for b in bundles_cursor:
                title = b.get("title", "")
                found = q_regex.findall(title)
                for q in found:
                    qualities_set.add(q.lower())

        q_str = " & ".join(sorted(list(qualities_set)))
        if not q_str: q_str = "HD"

        if season:
            if ep_label:
                btn_text = f"Season {season} {ep_label} [{q_str}]"
            else:
                btn_text = f"Season {season} [{q_str}]"
        else:
            btn_text = f"{grp.get('title')} [{q_str}]"

        url = f"https://t.me/{Config.BOT_USERNAME}?start=group_{grp['code']}"
        buttons.append([InlineKeyboardButton(btn_text, url=url)])

    if not buttons:
        buttons.append([InlineKeyboardButton("Coming Soon...", callback_data="noop")])

    return InlineKeyboardMarkup(buttons)

# --- Setup Logic (Triggered by Event) ---

async def setup_series_channel(client, chat_id):
    if chat_id not in pending_series_setups: return

    data = pending_series_setups[chat_id]
    tmdb_id = data["tmdb_id"]
    user_id = data["user_id"]
    stored_username = data.get("username")

    try:
        chat = await client.get_chat(chat_id)
        title = chat.title
        username = chat.username or stored_username

        try: await client.send_message(user_id, f"✅ **Bot Promoted in {title}!**\nSetting up series channel...")
        except: pass

        ids = await generate_series_messages(client, chat_id, tmdb_id)

        if not ids:
             try: await client.send_message(user_id, "❌ Setup failed. Could not generate messages (No groups found?).")
             except: pass
             return

        await db.add_series_channel(
            chat_id=chat_id,
            title=title,
            username=username,
            tmdb_id=tmdb_id,
            poster_msg_id=ids["poster"],
            buttons_msg_id=ids["buttons"],
            instruction_msg_id=ids["instruction"]
        )

        try: await client.send_message(user_id, "🎉 **Series Channel Setup Complete!**")
        except: pass

    except Exception as e:
        logger.error(f"Setup Series Error: {e}")
        try: await client.send_message(user_id, f"❌ Error: {e}")
        except: pass
    finally:
        if chat_id in pending_series_setups:
            del pending_series_setups[chat_id]

async def generate_series_messages(client, chat_id, tmdb_id):
    details = await get_tmdb_details(tmdb_id, "tv")
    if not details: return None

    # Build Markup
    markup = await build_series_markup(tmdb_id)

    # Content
    poster_path = details.get("poster_path")
    poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None

    title = details.get("name", "Unknown Series")
    year = (details.get("first_air_date") or "")[:4]
    rating = details.get("vote_average", 0)
    overview = details.get("overview", "")
    genres = [g["name"] for g in details.get("genres", [])[:3]]
    genre_text = ", ".join(genres)

    caption = (
        f"📺 <b>{html.escape(title)}</b> ({year})\n\n"
        f"⭐️ <b>Rating:</b> {round(rating, 1)}/10\n"
        f"🎭 <b>Genres:</b> {genre_text}\n\n"
        f"📖 <b>Plot:</b>\n<i>{html.escape(overview)[:800]}...</i>\n\n"
        f"👇 <b>Enjoy watching!</b> 🍿"
    )

    if poster_url:
        msg1 = await client.send_photo(chat_id, poster_url, caption=caption, parse_mode=ParseMode.HTML)
    else:
        msg1 = await client.send_message(chat_id, caption, parse_mode=ParseMode.HTML)

    msg2 = await client.send_message(
        chat_id,
        "⬇️ **Select Season & Quality:**",
        reply_markup=markup
    )

    msg3 = await client.send_message(
        chat_id,
        "👆 **Click any season button above and start the bot to get files!**"
    )

    return {"poster": msg1.id, "buttons": msg2.id, "instruction": msg3.id}

# --- Refresh Logic ---

async def refresh_series_channel(client, chat_id, update_text=None):
    ch = await db.channels_col_private.find_one({"chat_id": chat_id, "type": "series"})
    if not ch: return

    tmdb_id = ch.get("tmdb_id")
    old_btn_msg_id = ch.get("buttons_msg_id")
    old_instr_msg_id = ch.get("instruction_msg_id")

    markup = await build_series_markup(tmdb_id)

    # Delete Old
    try: await client.delete_messages(chat_id, [old_btn_msg_id, old_instr_msg_id])
    except: pass

    # Send New
    msg2 = await client.send_message(
        chat_id,
        "⬇️ **Select Season & Quality:**",
        reply_markup=markup
    )

    msg3 = await client.send_message(
        chat_id,
        "👆 **Click any season button above and start the bot to get files!**"
    )

    await db.update_series_channel_messages(chat_id, msg2.id, msg3.id)

    if update_text:
        await notify_series_update(client, chat_id, update_text)

async def notify_series_update(client, chat_id, text="New content added! ✔️"):
    try:
        msg = await client.send_message(chat_id, text)
        # We spawn a background task to delete it
        asyncio.create_task(delayed_delete(msg))
    except: pass

async def delayed_delete(message, delay=600):
    await asyncio.sleep(delay)
    try: await message.delete()
    except: pass
