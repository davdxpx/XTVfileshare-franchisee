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
                f"📢 **New Channel Request**\n\n"
                f"**Title:** {chat.title}\n"
                f"**ID:** `{chat.id}`\n"
                f"**Username:** @{chat.username or 'None'}\n\n"
                "Do you want to accept this channel?",
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("✅ Accept", callback_data=f"chan_ask_type|{chat.id}"),
                        InlineKeyboardButton("❌ Reject", callback_data=f"chan_reject|{chat.id}")
                    ]
                ])
            )
        except Exception as e:
            logger.error(f"Failed to notify admin: {e}")

# --- Callback: Accept/Reject Channel ---
@Client.on_callback_query(filters.regex(r"^chan_(ask_type|reject|set_type)\|"))
async def handle_channel_decision(client: Client, callback: CallbackQuery):
    if callback.from_user.id != Config.ADMIN_ID:
        await callback.answer("You are not authorized.", show_alert=True)
        return

    data = callback.data.split("|")
    action = data[0]
    chat_id = int(data[1])

    if action == "chan_ask_type":
        # Ask for type
        await callback.edit_message_text(
            "✅ **Accepted.** Now select the channel type:",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("🗄 DB Channel", callback_data=f"chan_set_type|{chat_id}|storage"),
                    InlineKeyboardButton("🔒 Force Sub", callback_data=f"chan_set_type|{chat_id}|force_sub")
                ]
            ])
        )

    elif action == "chan_set_type":
        ctype = data[2]
        try:
            chat = await client.get_chat(chat_id)
            invite_link = None

            if ctype == "force_sub":
                # Generate invite link for force sub
                try:
                    invite = await client.create_chat_invite_link(chat_id, name="Fileshare Bot FS")
                    invite_link = invite.invite_link
                except Exception as e:
                    logger.warning(f"Failed to create invite link: {e}")
                    # Try getting existing or username
                    invite_link = chat.invite_link or (f"https://t.me/{chat.username}" if chat.username else None)

            await db.add_channel(chat_id, chat.title, chat.username, ctype, invite_link)

            label = "Storage Channel" if ctype == "storage" else "Force Sub Channel"
            await callback.edit_message_text(
                f"✅ **Channel Configured!**\n\n"
                f"Title: {chat.title}\n"
                f"Type: **{label}**\n"
                f"Link: {invite_link or 'N/A'}"
            )

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
