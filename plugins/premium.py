from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from db import db
from config import Config
from datetime import datetime
import time

@Client.on_message(filters.command(["premium", "vip"]))
async def premium_command(client, message):
    user_id = message.from_user.id
    is_prem = await db.is_premium_user(user_id)

    if not is_prem:
        # Non-Premium View
        text = (
            "🔒 **Premium Access Locked**\n\n"
            "Unlock the full potential of XTV Fileshare Bot!\n\n"
            "**💎 Premium Benefits:**\n"
            "• ⏭ **Skip All Quests** (Instant Access)\n"
            "• 📂 **My History** (Recent downloads)\n"
            "• ⚡ **Priority Speed** (Fastest Servers)\n"
            "• 🚫 **No Ads**\n\n"
            "__Get Premium by inviting friends or using coupons!__"
        )
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 Get Premium Free", callback_data="open_referral_menu")]
        ])
        await message.reply(text, reply_markup=markup)
        return

    # Premium View
    user = await db.users_col.find_one({"user_id": user_id})
    expiry = user.get("premium_expiry", 0)
    try:
        dt = datetime.fromtimestamp(expiry).strftime('%Y-%m-%d %H:%M')
    except:
        dt = "Unknown"

    text = (
        "🌟 **Premium Dashboard**\n\n"
        f"👤 **User:** `{user_id}`\n"
        f"📅 **Expires:** `{dt}`\n\n"
        "__Thank you for supporting us!__"
    )

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("📂 My History", callback_data="prem_history")],
        [InlineKeyboardButton("⚡ Priority Mode: ON", callback_data="noop")],
        [InlineKeyboardButton("❌ Close", callback_data="close_menu")]
    ])

    await message.reply(text, reply_markup=markup)

@Client.on_callback_query(filters.regex(r"^open_referral_menu$"))
async def open_referral_jump(client, callback):
    # Trigger existing logic from community plugin
    from plugins.community import show_referral_menu
    await show_referral_menu(client, callback.message.chat.id, callback.from_user.id, callback.message)

@Client.on_callback_query(filters.regex(r"^noop$"))
async def noop_cb(client, callback):
    await callback.answer("✅ Active")

@Client.on_callback_query(filters.regex(r"^close_menu$"))
async def close_menu_cb(client, callback):
    await callback.message.delete()

@Client.on_callback_query(filters.regex(r"^prem_history$"))
async def prem_history(client, callback):
    user_id = callback.from_user.id
    history = await db.get_user_history(user_id)

    if not history:
        await callback.answer("No history yet.", show_alert=True)
        return

    text = "**📂 My Recent History**\n\n"
    for item in history:
        title = item.get("title", "Unknown")[:30]
        code = item.get("code")
        link = f"https://t.me/{Config.BOT_USERNAME}?start={code}"
        text += f"• [{title}]({link})\n"

    markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_to_prem")]])
    await callback.edit_message_text(text, reply_markup=markup, disable_web_page_preview=True)

@Client.on_callback_query(filters.regex(r"^back_to_prem$"))
async def back_to_prem(client, callback):
    # Re-show premium menu. Need to fetch expiry again.
    user_id = callback.from_user.id
    user = await db.users_col.find_one({"user_id": user_id})
    expiry = user.get("premium_expiry", 0)
    try:
        dt = datetime.fromtimestamp(expiry).strftime('%Y-%m-%d %H:%M')
    except:
        dt = "Unknown"

    text = (
        "🌟 **Premium Dashboard**\n\n"
        f"👤 **User:** `{user_id}`\n"
        f"📅 **Expires:** `{dt}`\n\n"
        "__Thank you for supporting us!__"
    )
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("📂 My History", callback_data="prem_history")],
        [InlineKeyboardButton("⚡ Priority Mode: ON", callback_data="noop")],
        [InlineKeyboardButton("❌ Close", callback_data="close_menu")]
    ])
    await callback.edit_message_text(text, reply_markup=markup)
