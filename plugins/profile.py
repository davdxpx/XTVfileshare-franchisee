import time
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from config import Config
from db import db
from utils.ranks import format_progress_bar, BADGE_ICONS

# Helper function
def generate_profile_text_markup(user, req_info, fs_info, tg_user):
    user_id = user.get("user_id")
    first_name = user.get("first_name") or tg_user.first_name or "User"

    # Premium Logic
    is_premium = False
    premium_expiry = user.get("premium_expiry", 0)
    if user.get("is_premium") and premium_expiry > time.time():
        is_premium = True

    if is_premium:
        expiry_date = datetime.fromtimestamp(premium_expiry).strftime("%d.%m.%Y")
        status_line = f"🌟 **Premium** (Expires: {expiry_date})"
    else:
        status_line = "👤 Free User"

    # Fileshare Rank
    fs_rank = fs_info["current_rank"]
    fs_xp = int(user.get("xp_fileshare", 0))
    fs_next_threshold = fs_info["next_threshold"]
    fs_percent = fs_info["progress_percent"]

    fs_bar = format_progress_bar(fs_percent, length=10)

    if fs_next_threshold:
        xp_text = f"{fs_xp} / {fs_next_threshold} XP"
    else:
        xp_text = f"{fs_xp} XP (Max Level)"

    # Request Rank
    req_rank = req_info["current_rank"]
    total_req = user.get("total_requests", 0)

    # Badges
    badges_list = user.get("badges", [])
    if badges_list:
        b_parts = []
        for b in badges_list:
            icon = BADGE_ICONS.get(b, "🏅")
            b_parts.append(f"{icon} {b}")
        badges_display = "  ".join(b_parts)
    else:
        badges_display = "None yet"

    # Stats
    referrals = user.get("referral_count", 0)
    joined_ts = user.get("joined_at", 0)
    joined_date = datetime.fromtimestamp(joined_ts).strftime("%d.%m.%Y") if joined_ts else "Unknown"

    last_active_ts = user.get("updated_at", time.time())
    last_active_date = datetime.fromtimestamp(last_active_ts).strftime("%d.%m.%Y %H:%M")

    text = (
        f"👤 **User Profile**\n\n"
        f"**Name:** {first_name}\n"
        f"**ID:** `{user_id}`\n"
        f"**Status:** {status_line}\n\n"

        f"📊 **Fileshare Rank**\n"
        f"🏆 **{fs_rank}**\n"
        f"`[{fs_bar}]` {fs_percent}%\n"
        f"XP: {xp_text}\n\n"

        f"🔰 **Request Rank**\n"
        f"{req_rank}\n\n"

        f"🏅 **Badges**\n"
        f"{badges_display}\n\n"

        f"📈 **Statistics**\n"
        f"• Total Requests: `{total_req}`\n"
        f"• Referrals: `{referrals}`\n"
        f"• Joined: {joined_date}\n"
        f"• Last Active: {last_active_date}"
    )

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Refresh", callback_data="profile_refresh")],
        [InlineKeyboardButton("❌ Close", callback_data="profile_close")]
    ])

    return text, markup

@Client.on_message(filters.command("profile"))
async def profile_command(client: Client, message: Message):
    user_id = message.from_user.id

    # ensure_full_user_profile calculates ranks and updates DB
    user, req_info, fs_info = await db.ensure_full_user_profile(user_id)

    text, markup = generate_profile_text_markup(user, req_info, fs_info, message.from_user)

    await message.reply(text, reply_markup=markup)

@Client.on_callback_query(filters.regex(r"^profile_refresh$"))
async def profile_refresh(client, callback):
    user_id = callback.from_user.id
    user, req_info, fs_info = await db.ensure_full_user_profile(user_id)

    text, markup = generate_profile_text_markup(user, req_info, fs_info, callback.from_user)

    try:
        await callback.edit_message_text(text, reply_markup=markup)
    except Exception:
        pass

@Client.on_callback_query(filters.regex(r"^profile_close$"))
async def profile_close(client, callback):
    await callback.message.delete()
