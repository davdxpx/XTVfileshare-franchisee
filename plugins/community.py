import asyncio
import time
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from config import Config
from db import db
from log import get_logger

logger = get_logger(__name__)

# --- /share - Referral Menu ---

@Client.on_message(filters.command(["share", "invite", "referral"]))
async def share_menu(client: Client, message: Message):
    user_id = message.from_user.id
    await show_referral_menu(client, message.chat.id, user_id)

async def show_referral_menu(client, chat_id, user_id, message_to_edit=None):
    count = await db.get_referral_count(user_id)
    target = await db.get_config("referral_target", 10)
    reward_hours = await db.get_config("referral_reward_hours", 24)
    bot_username = Config.BOT_USERNAME

    # Generate Progress Bar
    # [███░░░░░░░] 3/10
    percent = min(count / target, 1.0) if target > 0 else 1.0
    filled = int(percent * 10)
    bar = "█" * filled + "░" * (10 - filled)

    link = f"https://t.me/{bot_username}?start=ref_{user_id}"

    from urllib.parse import quote
    share_text = quote("🚀 Check out this awesome FileShare Bot! Get Movies & Series for free.\n\n👇 Click here:")
    share_url = f"https://t.me/share/url?url={link}&text={share_text}"

    text = (
        f"**🚀 Invite & Earn Premium**\n\n"
        f"Invite friends to unlock **{reward_hours} hours** of Premium access (Skip all Quests!).\n\n"
        f"**Your Progress:**\n"
        f"`[{bar}]` **{count}/{target}**\n\n"
        f"🔗 **Your Unique Link:**\n`{link}`\n\n"
        f"__Tap the button below to share!__"
    )

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("↗️ Share with Friends", url=share_url)],
        [InlineKeyboardButton("🔄 Refresh Status", callback_data="ref_refresh")],
        [InlineKeyboardButton("🏆 Top Referrers", callback_data="ref_top_10")]
    ])

    if message_to_edit:
        await message_to_edit.edit_text(text, reply_markup=markup)
    else:
        await client.send_message(chat_id, text, reply_markup=markup)

@Client.on_callback_query(filters.regex(r"^ref_refresh$"))
async def ref_refresh(client, callback):
    await show_referral_menu(client, callback.message.chat.id, callback.from_user.id, callback.message)

@Client.on_callback_query(filters.regex(r"^ref_top_10$"))
async def ref_top_10(client, callback):
    # Fetch top 10
    top_users = await db.get_top_referrers(10)

    text = "**🏆 Top 10 Referrers**\n\n"
    if not top_users:
        text += "No data yet."
    else:
        for idx, u in enumerate(top_users, 1):
            name = u.get("first_name", "User")
            # We might not have names stored if we only store user_id in basic docs.
            # If so, show ID hidden or partial.
            # Ideally store name on start.
            uid = str(u.get("user_id"))
            hid_id = f"{uid[:3]}***{uid[-2:]}"
            count = u.get("referral_count", 0)
            medal = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"{idx}."
            text += f"{medal} **{hid_id}** — {count} Invites\n"

    markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="ref_refresh")]])
    await callback.edit_message_text(text, reply_markup=markup)

# --- /daily - Daily Bonus ---

@Client.on_message(filters.command("daily"))
async def daily_command(client, message):
    enabled = await db.get_config("daily_bonus_enabled", False)
    if not enabled:
        await message.reply("❌ Daily Bonus is currently disabled.")
        return

    user_id = message.from_user.id
    ready = await db.get_daily_status(user_id)

    if ready:
        reward = await db.get_config("daily_bonus_reward", 1) # Hours
        await db.claim_daily_bonus(user_id, reward)
        await message.reply(f"✅ **Daily Bonus Claimed!**\n\nYou received **{reward} hours** of Premium access! 🎉\nCome back tomorrow!")
    else:
        # Calculate time left?
        # Requires fetching last_daily timestamp.
        # Simpler:
        await message.reply("⏳ **Cooldown!** You have already claimed your bonus today.\nCome back later.")

# --- /redeem - Coupons ---

@Client.on_message(filters.command("redeem"))
async def redeem_command(client, message):
    args = message.command
    if len(args) < 2:
        await message.reply("ℹ️ Usage: `/redeem <CODE>`")
        return

    code = args[1]
    user_id = message.from_user.id

    success, reason = await db.redeem_coupon(code, user_id)

    if success:
        await message.reply("✅ **Coupon Redeemed!**\nPremium access added to your account.")
    else:
        if reason == "already_used":
            await message.reply("❌ You have already used this coupon.")
        elif reason == "limit_reached":
            await message.reply("❌ This coupon has reached its usage limit.")
        else:
            await message.reply("❌ Invalid Code.")

# Quest logic is in plugins/user_start.py and plugins/quest.py
# This file handles shared features like Referrals, Coupons, Daily Bonus.

async def process_referral_reward(client, referrer_id):
    # Increment count
    new_count = await db.increment_referral(referrer_id)
    # Check Target
    target = await db.get_config("referral_target", 10)

    # Notify Referrer (Optional, maybe not every single one?)
    # "👤 New User Joined! (1/10)"
    try:
        await client.send_message(referrer_id, f"👤 **New User Joined!**\n\nProgress: `{new_count}/{target}`")
    except: pass

    if new_count >= target:
        # Check if already rewarded for this cycle?
        # Ideally we reset count or allow multiple cycles.
        # Simple Logic: Every multiple of target? Or just once?
        # User implies "Invite 10 -> Reward". Resetting count is cleaner or tracking cycles.
        # Let's assume One-Time or Cumulative.
        # If Cumulative: if new_count % target == 0
        if new_count % target == 0:
            reward_hours = await db.get_config("referral_reward_hours", 24)
            await db.add_premium_user(referrer_id, reward_hours / 24.0)
            try:
                await client.send_message(referrer_id, f"🎉 **Target Reached!**\n\nYou invited {target} users!\n🎁 **Reward:** {reward_hours}h Premium Access granted!")
            except: pass

@Client.on_callback_query(filters.regex(r"^ref_verify\|"))
async def ref_verify_callback(client, callback):
    # Data: ref_verify|chat_id|referrer_id
    try:
        parts = callback.data.split("|")
        chat_id = int(parts[1])
        referrer_id = int(parts[2])
        user_id = callback.from_user.id

        # Verify Membership
        try:
            member = await client.get_chat_member(chat_id, user_id)
            if member.status in ["left", "kicked", "banned"]:
                await callback.answer("❌ You haven't joined yet!", show_alert=True)
                return
        except Exception as e:
             # If bot can't see, we might assume success or fail.
             # Fail is safer.
             await callback.answer(f"❌ Verification failed. Try again in a moment.", show_alert=True)
             return

        # Success!
        await callback.message.delete()
        await callback.answer("✅ Success! Welcome!")

        # Check Cross-Franchise Bonus
        try:
            me = await client.get_me()
            referrer_origin = await db.get_user_origin(referrer_id)
            # If referrer is from another bot (and not None)
            if referrer_origin and referrer_origin != me.id:
                # Grant Bonus
                bonus_hours = await db.get_config("cross_ref_bonus", 6)
                await db.add_premium_user(referrer_id, bonus_hours / 24.0)
                try:
                    await client.send_message(referrer_id, f"🌐 **Cross-Franchise Bonus!**\n\n+ {bonus_hours}h Premium for inviting a user from another network node!")
                except: pass
        except Exception as e:
            logger.error(f"Cross-ref check failed: {e}")

        # Reward
        await process_referral_reward(client, referrer_id)

        # Send Welcome Msg
        await client.send_message(user_id, "👋 **Welcome to XTV Fileshare Bot!**\n\nYou can now use the bot freely.")

    except Exception as e:
        logger.error(f"Ref verify error: {e}")
