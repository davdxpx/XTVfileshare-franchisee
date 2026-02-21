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

    # Professional Formatting
    if is_premium:
        expiry_date = datetime.fromtimestamp(premium_expiry).strftime("%d.%m.%Y")
        header = f"⭐️ **VIP DASHBOARD** ⭐️"
        status_display = f"💎 **Premium Member** (Expires: {expiry_date})"
        name_display = f"🌟 {first_name}"
    else:
        header = f"👤 **USER PROFILE**"
        status_display = "👤 **Free Account**"
        name_display = f"{first_name}"

    # Fileshare Rank (Prominent)
    fs_rank = fs_info["current_rank"]
    fs_xp = int(user.get("xp_fileshare", 0))
    fs_next_threshold = fs_info["next_threshold"]
    fs_percent = fs_info["progress_percent"]

    # Clean Progress Bar
    fs_bar = format_progress_bar(fs_percent, length=12) # Longer for impact

    if fs_next_threshold:
        xp_text = f"{fs_xp} / {fs_next_threshold} XP"
        next_rank_text = f"Next: {fs_info['next_rank']}"
    else:
        xp_text = f"{fs_xp} XP"
        next_rank_text = "Max Level Reached!"

    # Request Rank (Smaller)
    req_rank = req_info["current_rank"]
    total_req = user.get("total_requests", 0)
    req_next_threshold = req_info["next_threshold"]

    # Optional: Small progress bar for Request Rank too?
    # Prompt: "Request Rank smaller below". Progress bar "for both ranks".
    req_percent = req_info["progress_percent"]
    req_bar = format_progress_bar(req_percent, length=8) # Smaller

    if req_next_threshold:
        req_xp_text = f"{total_req} / {req_next_threshold}"
    else:
        req_xp_text = f"{total_req} (Max)"

    # Badges
    badges_list = user.get("badges", [])
    if badges_list:
        b_parts = []
        for b in badges_list:
            icon = BADGE_ICONS.get(b, "🏅")
            b_parts.append(f"{icon} {b}")
        badges_display = " • ".join(b_parts) # Bullet separator
    else:
        badges_display = "None"

    # Stats
    referrals = user.get("referral_count", 0)
    joined_ts = user.get("joined_at", 0)
    joined_date = datetime.fromtimestamp(joined_ts).strftime("%d.%m.%Y") if joined_ts else "Unknown"

    last_active_ts = user.get("updated_at", time.time())
    last_active_date = datetime.fromtimestamp(last_active_ts).strftime("%d.%m.%Y %H:%M")

    # Layout
    text = (
        f"{header}\n\n"
        f"**Name:** {name_display}\n"
        f"**ID:** `{user_id}`\n"
        f"{status_display}\n\n"

        f"📊 **FILESHARE RANK**\n"
        f"🏆 **{fs_rank}**\n"
        f"`{fs_bar}` **{fs_percent}%**\n"
        f"_{xp_text} • {next_rank_text}_\n\n"

        f"🔰 **Request Rank**\n"
        f"{req_rank}\n"
        f"`{req_bar}` {req_xp_text}\n\n"

        f"🏅 **Badges**\n"
        f"{badges_display}\n\n"

        f"📈 **Statistics**\n"
        f"• Total Requests: `{total_req}`\n"
        f"• Referrals: `{referrals}`\n"
        f"• Joined: {joined_date}\n"
        f"• Last Active: {last_active_date}"
    )

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Refresh Profile", callback_data="profile_refresh")],
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
