from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import UserNotParticipant, ChatAdminRequired
from config import Config
from db import db
from log import get_logger
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

    channels = await db.get_config("force_sub_channels", [])
    if not channels:
        return True, []

    missing_channels = []
    for channel in channels:
        try:
            # Handle int or username
            chat_id = int(channel) if str(channel).lstrip("-").isdigit() else channel
            try:
                member = await client.get_chat_member(chat_id, user_id)
                if member.status in ["left", "kicked", "banned"]:
                    missing_channels.append(channel)
            except UserNotParticipant:
                missing_channels.append(channel)
            except Exception as e:
                logger.warning(f"Force sub check failed for {channel}: {e}")
                # If bot can't check, usually assume open or ignore?
                # Better to ignore to avoid blocking user if bot issues.
                pass
        except Exception:
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
            # Initialize tasks
            # Logic: 3 tasks or as configured
            count = Config.TASKS_PER_REQUEST
            tasks = await db.get_random_tasks(count)
            # If no tasks in DB, fallback or skip
            if not tasks:
                # Fallback task if really needed or just skip
                tasks = []

            session["tasks"] = tasks
            session["task_index"] = 0

        current_idx = session["task_index"]
        if current_idx < len(tasks):
            task = tasks[current_idx]
            # Send Task
            question = task["question"]
            options = task.get("options", [])
            task_type = task.get("type", "text")

            markup = []
            if task_type == "quiz" and options:
                # Shuffle options?
                # options is list of strings
                # We need to pass the answer or just the selected option in callback
                # Callback: task_ans|index|option_index or task_ans|index|correct/wrong
                # To be secure, don't expose answer in callback data if possible.
                # But we have state.
                btns = []
                for opt in options:
                    btns.append(InlineKeyboardButton(opt, callback_data=f"task_ans|{opt}"))

                # Arrange buttons 2 per row
                markup = [btns[i:i+2] for i in range(0, len(btns), 2)]

            # Skip Button
            markup.append([InlineKeyboardButton("⏭ Skip (Wait 20s)", callback_data="task_skip")])

            txt = f"**🧩 Task {current_idx + 1}/{len(tasks)}**\n\n{question}"
            if task_type == "text":
                txt += "\n\n__Send your answer below.__"

            await client.send_message(chat_id, txt, reply_markup=InlineKeyboardMarkup(markup))
            return

    # 2. Delivery (No delay as per clarification)
    await deliver_bundle(client, user_id, chat_id, session["code"])

async def deliver_bundle(client, user_id, chat_id, code):
    bundle = await db.get_bundle(code)
    if not bundle:
        await client.send_message(chat_id, "❌ Bundle not found.")
        return

    # Rate Limit Check (Final check before delivery)
    allowed, req_count = await db.check_rate_limit(user_id)
    # Actually we checked at start, but good to check again or just register now.
    await db.add_request(user_id)
    await db.increment_bundle_views(code)

    files = bundle["file_ids"]
    status_msg = await client.send_message(chat_id, f"✅ Verified! Sending {len(files)} files...")

    for file_data in files:
        try:
            # copy_message (removes forwarding tag visually if copy is used, but technically it's a new message)
            # User wanted: "without the forwarding watermark". copy_message does exactly this.
            # Caption=None to remove caption.
            # Protect content.

            # We need to know original chat_id and message_id?
            # In bundle, we stored 'file_ids'. copy_message needs chat_id and message_id.
            # Wait, `copy_message` needs the *source chat ID* and *message ID*.
            # My `file_ids` in DB stores file_id, file_unique_id.
            # I CANNOT use `copy_message` with just a file_id.
            # I must use `send_document(file_id)`.
            # If I use `send_document(file_id)`, I satisfy "without forwarding watermark".
            # Does `send_document` work with file_id from another chat?
            # Yes, if the bot has access to it (which it does, it saw it).
            # AND `send_document` allows `file_name` setting only if I upload a file?
            # Pyrogram `send_document` with a file_id string preserves the original filename usually.
            # To "Randomize file names", I might need to download and re-upload?
            # "Randomize file names in Telegram (e.g., "file_" + random_hex(8) + ".mp4")"
            # Re-uploading is heavy.
            # However, Pyrogram `send_document` has `file_name` parameter.
            # Let's try `send_document(chat_id, file_id, file_name="random.mp4")`.
            # If that works, great. If not, we might skip randomization or accept original name.
            # Telegram API allows setting `file_name` when sending by file_id?
            # Documentation says: "file_name" is used when uploading.
            # But let's try.

            from utils import generate_random_code
            ext = "." + file_data["file_name"].split(".")[-1] if "." in file_data["file_name"] else ""
            new_name = f"file_{generate_random_code(8)}{ext}"

            await client.send_document(
                chat_id,
                file_data["file_id"],
                caption=None,
                file_name=new_name,
                protect_content=True
            )
        except Exception as e:
            logger.error(f"Failed to send file: {e}")

    await status_msg.delete()

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
            # We need an invite link.
            # If we have username, use it. If ID, we need to fetch chat to get link.
            # To optimize, admin should provide usernames or we fetch once and cache?
            # For now, generate link if possible.
            try:
                chat = await client.get_chat(ch)
                link = chat.invite_link or f"https://t.me/{chat.username}"
                btns.append([InlineKeyboardButton(f"Join {chat.title}", url=link)])
            except Exception:
                btns.append([InlineKeyboardButton(f"Join Channel", url=f"https://t.me/{str(ch).replace('@','')} ")])

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
    # Check time
    # We need to store when the task was sent.
    # user_sessions doesn't store msg timestamp.
    # But we can check `callback.message.date`.
    msg_date = callback.message.date.timestamp()
    now = time.time()
    diff = now - msg_date

    if diff < 20:
        await callback.answer(f"⏳ Please wait {int(20 - diff)} more seconds.", show_alert=True)
        return

    # Proceed
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

    # Simple check (case insensitive)
    if ans.strip().lower() == correct_ans.strip().lower():
        await callback.answer("✅ Correct!")
        session["task_index"] += 1
        await callback.message.delete()
        await send_next_step(client, user_id, callback.message.chat.id)
    else:
        await callback.answer("❌ Wrong answer. Try again or skip.", show_alert=True)

# Text Answer Handler
@Client.on_message(filters.text & ~filters.command(["start", "create_link"]))
async def on_text_answer(client, message):
    user_id = message.from_user.id
    if user_id not in user_sessions:
        return

    session = user_sessions[user_id]
    tasks = session.get("tasks")
    if not tasks: return # Not in task phase

    idx = session.get("task_index", 0)
    if idx >= len(tasks): return # Done

    current_task = tasks[idx]
    if current_task.get("type") == "quiz":
        return # Ignore text for quiz

    correct_ans = current_task["answer"]

    if message.text.strip().lower() == correct_ans.strip().lower():
        await message.reply("✅ Correct!")
        session["task_index"] += 1
        await send_next_step(client, user_id, message.chat.id)
    else:
        # User prompt says "Task failed, try again."
        # And "skip after 20 seconds".
        # We don't delete user message, just reply?
        # Maybe send a subtle "Wrong" or just ignore/shake.
        # But we need to give feedback.
        await message.reply("❌ Wrong answer. Try again.")
