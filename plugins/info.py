from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from config import Config

@Client.on_message(filters.command("info"))
async def info_handler(client, message):
    text = (
        "🤖 **Bot Info**\n\n"
        f"ℹ️ **Version:** {Config.BOT_VERSION}\n"
        "👥 **Für:** @XTVglobal Netzwerk\n"
    )

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("👨‍💻 Entwickler", callback_data="dev_contact")]
    ])

    await message.reply_text(text, reply_markup=markup)

@Client.on_callback_query(filters.regex("dev_contact"))
async def dev_contact_handler(client, callback: CallbackQuery):
    await callback.answer("🔜 Kontaktmöglichkeit folgt bald!", show_alert=True)
