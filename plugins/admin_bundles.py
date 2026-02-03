from pyrogram import Client, filters
from pyrogram.types import Message
from config import Config
from db import db
from utils import generate_random_code, get_file_id
from log import get_logger
import asyncio

logger = get_logger(__name__)

# Simple in-memory state
# {user_id: {"step": str, "data": dict}}
admin_states = {}

async def process_bundle_creation(client, message, channel_id, start_id, end_id):
    if start_id > end_id:
        start_id, end_id = end_id, start_id

    status_msg = await message.reply("⏳ **Processing bundle...** Fetching messages.")

    try:
        # Check if channel is approved
        if not await db.is_channel_approved(channel_id):
            await status_msg.edit("❌ This channel is not in the approved database channels list.")
            return

        # Fetch messages
        # Chunking just in case, though 100 is standard limit usually
        all_messages = []
        ids = list(range(start_id, end_id + 1))
        chunk_size = 200

        for i in range(0, len(ids), chunk_size):
            chunk = ids[i:i + chunk_size]
            msgs = await client.get_messages(channel_id, chunk)
            if not isinstance(msgs, list): # Single message case
                msgs = [msgs]
            all_messages.extend(msgs)

        file_ids = []
        # Title usually comes from the first message caption/filename or generated
        title = f"Bundle {start_id}-{end_id}"

        for msg in all_messages:
            if not msg: continue
            fid, fname, fsize, fmime = get_file_id(msg)
            if fid:
                file_ids.append({
                    "file_id": fid,
                    "file_unique_id": getattr(msg.document or msg.video or msg.audio or msg.photo, "file_unique_id", "unknown"),
                    "file_name": fname,
                    "file_size": fsize,
                    "mime_type": fmime
                })
                # Use first file name as bundle title if generic
                if title.startswith("Bundle") and fname:
                    title = fname

        if not file_ids:
            await status_msg.edit("❌ No files found in the specified range.")
            return

        # Create Code
        code = generate_random_code()

        # Save to DB
        await db.create_bundle(
            code=code,
            file_ids=file_ids,
            source_channel=channel_id,
            title=title,
            original_range={"start": start_id, "end": end_id}
        )

        bot_username = Config.BOT_USERNAME
        link = f"https://t.me/{bot_username}?start={code}"

        await status_msg.edit(
            f"✅ **Bundle Created!**\n\n"
            f"📄 Files: {len(file_ids)}\n"
            f"🔗 Link: `{link}`\n"
            f"🆔 Code: `{code}`"
        )

    except Exception as e:
        logger.error(f"Bundle creation failed: {e}")
        await status_msg.edit(f"❌ Error: {e}")

# --- Interactive Workflow ---

@Client.on_message(filters.command("create_link") & filters.user(Config.ADMIN_ID))
async def create_link_start(client: Client, message: Message):
    # Check args for Manual Mode
    args = message.command
    if len(args) == 4:
        # /create_link channel_id start end
        try:
            channel_id = int(args[1])
            start_id = int(args[2])
            end_id = int(args[3])
            await process_bundle_creation(client, message, channel_id, start_id, end_id)
            return
        except ValueError:
            await message.reply("❌ Invalid format. Use: `/create_link channel_id start_id end_id`")
            return

    # Interactive Mode
    admin_states[message.from_user.id] = {"step": "wait_start_msg", "data": {}}
    await message.reply(
        "🔄 **Link Creation Mode**\n\n"
        "Please **forward** the **first message** of the bundle from the storage channel."
    )

@Client.on_message(filters.user(Config.ADMIN_ID) & filters.forwarded)
async def on_forward_received(client: Client, message: Message):
    user_id = message.from_user.id
    if user_id not in admin_states:
        return

    state = admin_states[user_id]
    step = state["step"]

    if step == "wait_start_msg":
        if not message.forward_from_chat:
            await message.reply("❌ Please forward from a channel.")
            return

        # Save start info
        state["data"]["channel_id"] = message.forward_from_chat.id
        state["data"]["start_id"] = message.forward_from_message_id
        state["step"] = "wait_end_msg"

        await message.reply(
            f"✅ Start set to ID `{message.forward_from_message_id}` from `{message.forward_from_chat.title}`.\n\n"
            "Now **forward** the **last message**."
        )

    elif step == "wait_end_msg":
        if not message.forward_from_chat:
            await message.reply("❌ Please forward from a channel.")
            return

        if message.forward_from_chat.id != state["data"]["channel_id"]:
            await message.reply("❌ Channel mismatch! Please forward from the same channel.")
            return

        end_id = message.forward_from_message_id
        start_id = state["data"]["start_id"]
        channel_id = state["data"]["channel_id"]

        # Cleanup state
        del admin_states[user_id]

        await process_bundle_creation(client, message, channel_id, start_id, end_id)

@Client.on_message(filters.command("cancel") & filters.user(Config.ADMIN_ID))
async def cancel_creation(client, message):
    if message.from_user.id in admin_states:
        del admin_states[message.from_user.id]
        await message.reply("❌ Operation cancelled.")
    else:
        await message.reply("Nothing to cancel.")
