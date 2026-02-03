from pyrogram import Client, filters
from pyrogram.types import ChatMemberUpdated, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
from pyrogram.enums import ChatMemberStatus
from config import Config
from db import db
from log import get_logger

logger = get_logger(__name__)

# --- Event: Bot added to channel ---
@Client.on_chat_member_updated()
async def on_bot_promoted(client: Client, chat_member: ChatMemberUpdated):
    # Check if the update is about the bot itself
    me = await client.get_me()
    if chat_member.new_chat_member.user.id != me.id:
        return

    # Check if promoted to Admin
    if chat_member.new_chat_member.status == ChatMemberStatus.ADMINISTRATOR:
        chat = chat_member.chat
        logger.info(f"Bot promoted to admin in {chat.title} ({chat.id})")

        # Notify Admin
        try:
            await client.send_message(
                Config.ADMIN_ID,
                f"📢 **New Database Channel Request**\n\n"
                f"**Title:** {chat.title}\n"
                f"**ID:** `{chat.id}`\n"
                f"**Username:** @{chat.username or 'None'}",
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("✅ Accept", callback_data=f"chan_accept|{chat.id}"),
                        InlineKeyboardButton("❌ Reject", callback_data=f"chan_reject|{chat.id}")
                    ]
                ])
            )
        except Exception as e:
            logger.error(f"Failed to notify admin: {e}")

# --- Callback: Accept/Reject Channel ---
@Client.on_callback_query(filters.regex(r"^chan_(accept|reject)\|"))
async def handle_channel_decision(client: Client, callback: CallbackQuery):
    if callback.from_user.id != Config.ADMIN_ID:
        await callback.answer("You are not authorized.", show_alert=True)
        return

    action, chat_id = callback.data.split("|")
    chat_id = int(chat_id)

    if action == "chan_accept":
        # We need to fetch chat details again to store them, or just rely on what we have?
        # Better to fetch to be sure.
        try:
            chat = await client.get_chat(chat_id)
            await db.add_channel(chat_id, chat.title, chat.username)
            await callback.edit_message_text(
                f"✅ **Channel Approved**\n\nTitle: {chat.title}\nID: `{chat.id}`"
            )
            await callback.answer("Channel approved!")

            # Optionally send a message to the channel confirming?
            # "Bot is now active here." - User didn't ask for it, but it's good practice.
            # I'll skip it to keep it stealthy as requested ("private").

        except Exception as e:
            await callback.answer(f"Error: {e}", show_alert=True)

    elif action == "chan_reject":
        # Maybe leave the chat?
        try:
            await client.leave_chat(chat_id)
            await callback.edit_message_text(f"❌ **Channel Rejected**\nID: `{chat_id}`\nBot left the channel.")
        except Exception as e:
            await callback.edit_message_text(f"❌ **Channel Rejected**\nID: `{chat_id}`\n(Failed to leave: {e})")

# --- Command: List Channels ---
@Client.on_message(filters.command("list_channels") & filters.user(Config.ADMIN_ID))
async def list_channels(client: Client, message: Message):
    channels = await db.get_approved_channels()
    if not channels:
        await message.reply("No approved channels.")
        return

    text = "**📂 Approved Storage Channels:**\n\n"
    for ch in channels:
        text += f"🔹 **{ch.get('title')}** (`{ch.get('chat_id')}`)\n"

    await message.reply(text)
