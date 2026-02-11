from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from config import Config
from db import db
from log import get_logger
import asyncio
import time

logger = get_logger(__name__)

# State: {user_id: {"step": str, "data": dict}}
broadcast_states = {}

# --- Menu ---

@Client.on_callback_query(filters.regex(r"^admin_broadcast_menu$"))
async def admin_broadcast_menu(client, callback):
    text = "**📢 Broadcast System**\n\nCreate a new broadcast to all users."
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ New Broadcast", callback_data="start_broadcast")],
        [InlineKeyboardButton("🔙 Back", callback_data="admin_growth")]
    ])
    await callback.edit_message_text(text, reply_markup=markup)

# --- Wizard ---

@Client.on_callback_query(filters.regex(r"^start_broadcast$"))
async def start_broadcast(client, callback):
    broadcast_states[callback.from_user.id] = {"step": "wait_message", "data": {}}
    await callback.message.delete()
    await client.send_message(
        callback.from_user.id,
        "**📢 New Broadcast**\n\n"
        "Please send the **Message** you want to broadcast.\n"
        "(Text, Photo, Video, Sticker supported)."
    )

@Client.on_message(filters.user(Config.ADMIN_ID) & (filters.text | filters.photo | filters.video | filters.sticker) & ~filters.command(["admin", "cancel"]), group=3)
async def broadcast_input(client, message):
    user_id = message.from_user.id
    if user_id not in broadcast_states: return

    state = broadcast_states[user_id]
    step = state["step"]

    if step == "wait_message":
        # Save message details
        # We can copy the message directly later.
        state["data"]["message_id"] = message.id
        state["data"]["chat_id"] = message.chat.id

        state["step"] = "wait_confirm"

        # Show Options
        text = "**📢 Broadcast Preview**\n\nMessage received. Configure settings:"
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("📌 Pin: No", callback_data="toggle_pin")],
            [InlineKeyboardButton("🔔 Silent: No", callback_data="toggle_silent")],
            [InlineKeyboardButton("🚀 Send Now", callback_data="send_broadcast")],
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel_broadcast")]
        ])

        await message.reply(text, reply_markup=markup, quote=True)

@Client.on_callback_query(filters.regex(r"^toggle_(pin|silent)$"))
async def toggle_bc_option(client, callback):
    user_id = callback.from_user.id
    if user_id not in broadcast_states: return

    opt = callback.data.split("_")[1]
    data = broadcast_states[user_id]["data"]

    # Toggle
    current = data.get(opt, False)
    data[opt] = not current

    # Re-render markup
    pin_txt = f"📌 Pin: {'Yes' if data.get('pin') else 'No'}"
    silent_txt = f"🔔 Silent: {'Yes' if data.get('silent') else 'No'}"

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton(pin_txt, callback_data="toggle_pin")],
        [InlineKeyboardButton(silent_txt, callback_data="toggle_silent")],
        [InlineKeyboardButton("🚀 Send Now", callback_data="send_broadcast")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_broadcast")]
    ])

    await callback.edit_message_reply_markup(reply_markup=markup)

@Client.on_callback_query(filters.regex(r"^cancel_broadcast$"))
async def cancel_bc(client, callback):
    if callback.from_user.id in broadcast_states:
        del broadcast_states[callback.from_user.id]
    await callback.message.delete()
    await client.send_message(callback.from_user.id, "❌ Broadcast cancelled.")

@Client.on_callback_query(filters.regex(r"^send_broadcast$"))
async def send_broadcast(client, callback):
    user_id = callback.from_user.id
    if user_id not in broadcast_states: return

    data = broadcast_states[user_id]["data"]
    msg_id = data["message_id"]
    from_chat = data["chat_id"]
    pin = data.get("pin", False)
    silent = data.get("silent", False)

    del broadcast_states[user_id] # Clear state

    await callback.message.delete()
    status_msg = await client.send_message(user_id, "⏳ **Starting Broadcast...**\nInitializing user list...")

    # Start Background Task
    asyncio.create_task(run_broadcast(client, user_id, status_msg, from_chat, msg_id, pin, silent))

async def run_broadcast(client, admin_id, status_msg, from_chat, msg_id, pin, silent):
    # Fetch all users
    # db.users_col.find({}, {"user_id": 1})
    cursor = db.users_col.find({}, {"user_id": 1})
    users = await cursor.to_list(length=100000)
    total = len(users)

    sent = 0
    failed = 0
    blocked = 0

    start_time = time.time()

    for i, u in enumerate(users):
        uid = u["user_id"]
        try:
            # Copy Message
            m = await client.copy_message(
                chat_id=uid,
                from_chat_id=from_chat,
                message_id=msg_id,
                disable_notification=silent
            )
            if pin:
                try: await m.pin(disable_notification=silent)
                except: pass
            sent += 1
        except Exception as e:
            # Check for block
            if "400 PEER_ID_INVALID" in str(e) or "403 USER_IS_BLOCKED" in str(e) or "InputUserDeactivated" in str(e):
                blocked += 1
                # Mark as inactive in DB?
            else:
                failed += 1
                # FloodWait?
                if "420 FLOOD_WAIT" in str(e):
                    wait_sec = int(str(e).split()[5]) # Extract seconds
                    await asyncio.sleep(wait_sec)

        # Batch sleep to respect limits (30 req/sec max usually)
        # 20 per batch with 1s sleep is safe.
        if i % 20 == 0:
            await asyncio.sleep(1)

        # Update Status every 100
        if i % 100 == 0 and i > 0:
            elapsed = time.time() - start_time
            speed = i / elapsed
            eta = (total - i) / speed

            try:
                await status_msg.edit(
                    f"📢 **Broadcasting...**\n\n"
                    f"✅ Sent: `{sent}`\n"
                    f"❌ Failed: `{failed}`\n"
                    f"🚫 Blocked: `{blocked}`\n"
                    f"📊 Progress: `{i}/{total}`\n"
                    f"⏱ ETA: `{int(eta)}s`"
                )
            except: pass

    # Final Report
    duration = time.time() - start_time
    await client.send_message(
        admin_id,
        f"✅ **Broadcast Complete!**\n\n"
        f"👥 Total Users: `{total}`\n"
        f"✅ Sent: `{sent}`\n"
        f"❌ Failed: `{failed}`\n"
        f"🚫 Blocked: `{blocked}`\n"
        f"⏱ Duration: `{int(duration)}s`"
    )
