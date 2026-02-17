from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from config import Config
from db import db
from log import get_logger
import secrets
import string
import time
import asyncio

logger = get_logger(__name__)

# Local state management for franchise operations
franchise_states = {}

# --- Helper Functions ---

def generate_password(length=12):
    """Generates a strong random password."""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    password = ''.join(secrets.choice(alphabet) for i in range(length))
    return password

async def delayed_delete(client, chat_id, message_ids, delay=1800):
    """Deletes messages after a delay (in seconds)."""
    # Use DB queue for persistence
    delete_at = time.time() + delay
    if isinstance(message_ids, int):
        message_ids = [message_ids]
    await db.add_to_delete_queue(chat_id, message_ids, delete_at)

# --- CEO: Add Franchisee Flow ---

@Client.on_message(filters.command(["add", "add_franchisee"]) & filters.user(Config.CEO_ID))
async def add_franchisee_start(client: Client, message: Message):
    franchise_states[message.from_user.id] = {"state": "wait_user_id", "data": {}}
    await message.reply(
        "**🏢 Add New Franchisee**\n\n"
        "Please enter the **User ID** of the new Franchisee:\n"
        "(You can get this from their profile or if they forward a message)"
    )

@Client.on_message(filters.text & filters.user(Config.CEO_ID), group=10)
async def franchise_input_handler(client, message):
    user_id = message.from_user.id
    if user_id not in franchise_states:
        return # Not in this flow

    state = franchise_states[user_id]["state"]
    data = franchise_states[user_id]["data"]

    if state == "wait_user_id":
        try:
            target_id = int(message.text.strip())
            data["user_id"] = target_id
            franchise_states[user_id]["state"] = "wait_bot_username"
            await message.reply(
                f"✅ User ID: `{target_id}`\n\n"
                "Now enter their **Bot Username** (without @):\n"
                "(e.g. `MyFileShareBot`)"
            )
        except ValueError:
            await message.reply("❌ Invalid ID. Please enter a number.")
        return

    if state == "wait_bot_username":
        username = message.text.strip().replace("@", "")
        data["bot_username"] = username
        franchise_states[user_id]["state"] = "wait_bot_id"
        await message.reply(
            f"✅ Bot Username: `@{username}`\n\n"
            "Now enter their **Bot ID**:\n"
            "(e.g. `123456789`)"
        )
        return

    if state == "wait_bot_id":
        try:
            bot_id = int(message.text.strip())
            data["bot_id"] = bot_id
            franchise_states[user_id]["state"] = "wait_title"
            await message.reply(
                f"✅ Bot ID: `{bot_id}`\n\n"
                "Enter a **Title** for this Franchise:\n"
                "(e.g. `Movies Node 1`)"
            )
        except ValueError:
            await message.reply("❌ Invalid ID. Please enter a number.")
        return

    if state == "wait_title":
        data["title"] = message.text.strip()
        franchise_states[user_id]["state"] = "wait_uris"
        await message.reply(
            f"✅ Title: `{data['title']}`\n\n"
            "Now, please send the **3 Connection URIs** separated by new lines:\n"
            "1. MainDB (Read-Only)\n"
            "2. UserDB (Shared)\n"
            "3. PrivateDB (Local)\n\n"
            "Example:\n"
            "`mongodb+srv://...`\n"
            "`mongodb+srv://...`\n"
            "`mongodb+srv://...`"
        )
        return

    if state == "wait_uris":
        text = message.text.strip()
        lines = text.split("\n")
        # Allow lenient parsing if they paste a block
        clean_lines = [l.strip() for l in lines if l.strip()]

        if len(clean_lines) < 3:
             await message.reply("❌ Please provide all 3 URIs, separated by new lines.")
             return

        data["main_uri"] = clean_lines[0]
        data["user_uri"] = clean_lines[1]
        data["private_uri"] = clean_lines[2]

        # Proceed to Finish

        # Generate Password
        password = generate_password(16)
        data["password"] = password

        # Generate Franchisee ID
        franchisee_id = f"FR-{data['user_id']}"
        data["franchisee_id"] = franchisee_id

        data["status"] = "active"
        data["joined_at"] = time.time()

        # Save to DB
        await db.add_franchisee(data)

        # Confirm to CEO
        await message.reply(
            f"✅ **Franchisee Added!**\n\n"
            f"ID: `{franchisee_id}`\n"
            f"User: `{data['user_id']}`\n"
            f"Bot: @{data['bot_username']}\n"
            f"Password: ||{password}|| (Hidden)\n\n"
            "🚀 sending welcome message..."
        )

        # Send Welcome Message to Franchisee
        try:
            welcome_text = (
                f"🎉 **Welcome to the XTV Franchise Network!**\n\n"
                f"You have been granted access as a Franchisee.\n\n"
                f"🆔 **Your Franchisee ID:** `{franchisee_id}`\n"
                f"🔐 **Your Access Password:** `{password}`\n\n"
                f"⚠️ **IMPORTANT:**\n"
                f"1. **Save this password immediately.** It is shown ONLY ONCE.\n"
                f"2. You will need it to access the `/myfranchise` command.\n"
                f"3. This message will **self-destruct in 30 minutes** for security.\n\n"
                f"👉 Use `/myfranchise` to view your setup guide and dashboard."
            )
            sent_msg = await client.send_message(data['user_id'], welcome_text)

            # Schedule Auto-Delete (30 mins = 1800s)
            await delayed_delete(client, data['user_id'], sent_msg.id, 1800)

            await client.send_message(user_id, "✅ Welcome message sent and scheduled for deletion.")

        except Exception as e:
            await client.send_message(user_id, f"❌ Failed to send welcome message: {e}\nPlease share the password manually.")

        del franchise_states[user_id]


# --- Franchisee: /myfranchise Command ---

@Client.on_message(filters.command("myfranchise"))
async def my_franchise_handler(client, message):
    user_id = message.from_user.id

    # Check if authorized
    franchisee = await db.get_franchisee(user_id)
    if not franchisee:
        await message.reply("❌ Access Denied. You are not a registered Franchisee.")
        return

    # Check Password
    # We use a simple state to ask for password
    franchise_states[user_id] = {"state": "auth_password", "attempts": 0}
    await message.reply(
        "🔐 **Security Check**\n\n"
        "Please enter your **Franchisee Password** to continue:",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="fran_cancel")]])
    )

@Client.on_message(filters.text & ~filters.command(["myfranchise", "start", "cancel"]), group=11)
async def franchise_auth_handler(client, message):
    user_id = message.from_user.id
    if user_id not in franchise_states:
        return

    state_data = franchise_states[user_id]
    if state_data.get("state") != "auth_password":
        return

    input_pass = message.text.strip()

    # Verify
    is_valid = await db.verify_franchisee_password(user_id, input_pass)

    if is_valid:
        del franchise_states[user_id]
        await show_franchise_menu(client, message.chat.id, user_id)
        # Delete password message for security
        try: await message.delete()
        except: pass
    else:
        state_data["attempts"] += 1
        if state_data["attempts"] >= 3:
            del franchise_states[user_id]
            await message.reply("❌ **Access Denied.** Too many failed attempts.")
            # Audit Log
            await db.add_log("franchise_auth_fail", user_id, "3 failed password attempts")
        else:
            await message.reply(f"❌ **Incorrect Password.** ({state_data['attempts']}/3)\nTry again:")

async def show_franchise_menu(client, chat_id, user_id, message_to_edit=None):
    franchisee = await db.get_franchisee(user_id)
    if not franchisee: return

    text = (
        f"🏢 **Franchise Dashboard**\n"
        f"ID: `{franchisee.get('franchisee_id')}`\n"
        f"Status: `{franchisee.get('status', 'Active').upper()}`\n\n"
        "Select an option:"
    )

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔗 My URIs", callback_data="fran_uris")],
        [InlineKeyboardButton("📚 Setup Guide", callback_data="fran_guide")],
        [InlineKeyboardButton("📊 My Statistics", callback_data="fran_stats")],
        [InlineKeyboardButton("❌ Close", callback_data="fran_close")]
    ])

    if message_to_edit:
        await message_to_edit.edit_text(text, reply_markup=markup)
    else:
        await client.send_message(chat_id, text, reply_markup=markup)

@Client.on_callback_query(filters.regex(r"^fran_"))
async def franchise_callbacks(client, callback):
    action = callback.data.split("_")[1]
    user_id = callback.from_user.id

    if action == "cancel":
        if user_id in franchise_states:
            del franchise_states[user_id]
        await callback.message.delete()
        return

    if action == "close":
        await callback.message.delete()
        return

    if action == "menu":
        await show_franchise_menu(client, callback.message.chat.id, user_id, callback.message)
        return

    if action == "uris":
        # Check privileges (must be franchisee)
        fran = await db.get_franchisee(user_id)
        if not fran:
            await callback.answer("Access Denied.", show_alert=True)
            return

        m_uri = fran.get("main_uri", "Not Set")
        u_uri = fran.get("user_uri", "Not Set")
        p_uri = fran.get("private_uri", "Not Set")

        text = (
            "🔗 **Your Connection URIs**\n\n"
            "Use these in your `.env` file:\n\n"
            f"**MAIN_URI:**\n`{m_uri}`\n\n"
            f"**USER_URI:**\n`{u_uri}`\n\n"
            f"**PRIVATE_URI:**\n`{p_uri}`\n"
        )
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="fran_menu")]])
        await callback.edit_message_text(text, reply_markup=markup)
        return

    if action == "guide":
        text = (
            "📚 **Franchisee Setup Guide**\n\n"
            "1. **Deploy Bot:** Use the Repo `XTVfileshare-Franchisee`.\n"
            "2. **Configure Env:** Copy the URIs from 'My URIs'.\n"
            "3. **Set Variables:**\n"
            "   - `API_ID`, `API_HASH`\n"
            "   - `BOT_TOKEN`\n"
            "   - `CEO_ID` (Ask CEO)\n"
            "4. **Start Bot:** Run `python3 main.py`.\n"
            "5. **Verify:** Use `/myfranchise` here to check status.\n\n"
            "🔐 **Security:**\n"
            "- Keep your **Password** safe.\n"
            "- Do not share your `PRIVATE_URI`."
        )
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="fran_menu")]])
        await callback.edit_message_text(text, reply_markup=markup)
        return

    if action == "stats":
        fran = await db.get_franchisee(user_id)
        pushes = fran.get("pushes_count", 0)
        joined = time.strftime("%Y-%m-%d", time.localtime(fran.get("joined_at", 0)))

        text = (
            "📊 **My Statistics**\n\n"
            f"• **Pushes Requested:** `{pushes}`\n"
            f"• **Joined:** `{joined}`\n"
            f"• **Status:** `{fran.get('status', 'Active')}`"
        )
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="fran_menu")]])
        await callback.edit_message_text(text, reply_markup=markup)
        return


# --- CEO: Manage Franchises Panel ---

@Client.on_callback_query(filters.regex(r"^admin_manage_franchises$"))
async def admin_manage_franchises(client, callback):
    # CEO Only check
    if callback.from_user.id != Config.CEO_ID:
        await callback.answer("CEO Access Only.", show_alert=True)
        return

    franchisees = await db.get_all_franchisees()

    text = f"**🏢 Manage Franchises**\n\nTotal: {len(franchisees)}"

    markup = []
    for f in franchisees:
        title = f.get("title", "Untitled")
        fid = f.get("franchisee_id", "???")
        markup.append([InlineKeyboardButton(f"{title} ({fid})", callback_data=f"manage_fran|{f['user_id']}")])

    markup.append([InlineKeyboardButton("➕ Add New", callback_data="admin_add_fran_start")])
    markup.append([InlineKeyboardButton("🔙 Back", callback_data="admin_main")])

    await callback.edit_message_text(text, reply_markup=InlineKeyboardMarkup(markup))

@Client.on_callback_query(filters.regex(r"^admin_add_fran_start$"))
async def callback_add_start(client, callback):
    # Trigger message flow
    await callback.message.delete()
    # Call the message handler logic manually or ask user to type command?
    # Simulating command is hard. Just send instructions.
    await client.send_message(
        callback.from_user.id,
        "**To Add a Franchisee:**\n\n"
        "Please use the command: `/add`\n"
        "(It handles the interactive setup)"
    )

@Client.on_callback_query(filters.regex(r"^manage_fran\|"))
async def manage_single_franchisee(client, callback):
    target_id = int(callback.data.split("|")[1])
    fran = await db.get_franchisee(target_id)
    if not fran:
        await callback.answer("Franchisee not found.", show_alert=True)
        await admin_manage_franchises(client, callback)
        return

    text = (
        f"**🏢 Franchisee Details**\n\n"
        f"Title: `{fran.get('title')}`\n"
        f"ID: `{fran.get('franchisee_id')}`\n"
        f"User: `{fran.get('user_id')}`\n"
        f"Bot: @{fran.get('bot_username')}\n"
        f"Status: `{fran.get('status')}`"
    )

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("🗑 Remove Access", callback_data=f"del_fran|{target_id}")],
        [InlineKeyboardButton("🔙 Back", callback_data="admin_manage_franchises")]
    ])

    await callback.edit_message_text(text, reply_markup=markup)

@Client.on_callback_query(filters.regex(r"^del_fran\|"))
async def delete_franchisee_handler(client, callback):
    target_id = int(callback.data.split("|")[1])
    await db.delete_franchisee(target_id)
    await callback.answer("Franchisee removed.", show_alert=True)
    await admin_manage_franchises(client, callback)
