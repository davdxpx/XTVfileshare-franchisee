from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from config import Config
from db import db
from plugins.admin_bundles import admin_states # Re-use state management if possible, or create shared one

# Shared state for admin inputs (move to a shared file if needed, but for now accessing directly or redefining)
# Ideally, we should move admin_states to a shared module.
# For now, let's assume we can import it or define a local one if the other is strictly local.
# Looking at plugins/admin_bundles.py, admin_states is a global dict.
# We should probably refactor `admin_states` to `utils.py` or a new `state.py` to be clean.
# But to avoid breaking changes right now, I will import it if I can, or use a new one for panel actions.
# Let's use a new dict for panel specific inputs to be safe.
panel_states = {}

# --- Main Admin Panel ---

@Client.on_message(filters.command("admin") & filters.user(Config.ADMIN_ID))
async def admin_panel(client: Client, message: Message):
    await show_main_menu(message)

async def show_main_menu(message_or_callback):
    text = "**🛡️ Admin Panel**\nSelect a category to manage:"
    markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 Stats", callback_data="admin_stats"),
            InlineKeyboardButton("⚙️ Settings", callback_data="admin_settings")
        ],
        [
            InlineKeyboardButton("📢 Channels", callback_data="admin_channels"),
            InlineKeyboardButton("📦 Bundles", callback_data="admin_bundles")
        ],
        [
            InlineKeyboardButton("📝 Tasks", callback_data="admin_tasks")
        ],
        [
            InlineKeyboardButton("❌ Close", callback_data="admin_close")
        ]
    ])

    if isinstance(message_or_callback, Message):
        await message_or_callback.reply(text, reply_markup=markup)
    else:
        await message_or_callback.edit_message_text(text, reply_markup=markup)

@Client.on_callback_query(filters.regex(r"^admin_main$"))
async def back_to_main(client, callback):
    await show_main_menu(callback)

@Client.on_callback_query(filters.regex(r"^admin_close$"))
async def close_panel(client, callback):
    await callback.message.delete()

# --- Stats ---

@Client.on_callback_query(filters.regex(r"^admin_stats$"))
async def show_stats(client, callback):
    bundles = await db.get_all_bundles()
    total_views = sum(b.get("views", 0) for b in bundles)
    popular = sorted(bundles, key=lambda x: x.get("views", 0), reverse=True)[:5]

    pop_text = ""
    for p in popular:
        pop_text += f"- {p.get('title')} ({p.get('views', 0)} views)\n"

    text = (
        f"**📊 Statistics**\n\n"
        f"Total Bundles: {len(bundles)}\n"
        f"Total Requests: {total_views}\n\n"
        f"**🔥 Popular Bundles:**\n{pop_text}"
    )

    markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_main")]])
    await callback.edit_message_text(text, reply_markup=markup)

# --- Settings ---

@Client.on_callback_query(filters.regex(r"^admin_settings$"))
async def show_settings(client, callback):
    fs_enabled = await db.get_config("force_sub_enabled", False)
    tasks_enabled = await db.get_config("tasks_enabled", False)

    fs_text = "✅ Force Sub" if fs_enabled else "❌ Force Sub"
    task_text = "✅ Tasks" if tasks_enabled else "❌ Tasks"

    markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(fs_text, callback_data="toggle_fs_panel"),
            InlineKeyboardButton(task_text, callback_data="toggle_task_panel")
        ],
        [InlineKeyboardButton("🔙 Back", callback_data="admin_main")]
    ])

    await callback.edit_message_text("**⚙️ Settings**\nToggle features below:", reply_markup=markup)

@Client.on_callback_query(filters.regex(r"^toggle_(fs|task)_panel$"))
async def toggle_setting_panel(client, callback):
    setting = callback.data.split("_")[1] # fs or task
    if setting == "fs":
        curr = await db.get_config("force_sub_enabled", False)
        await db.update_config("force_sub_enabled", not curr)
    elif setting == "task":
        curr = await db.get_config("tasks_enabled", False)
        await db.update_config("tasks_enabled", not curr)

    await show_settings(client, callback)

# --- Channels ---

@Client.on_callback_query(filters.regex(r"^admin_channels$"))
async def show_channels(client, callback):
    channels = await db.get_approved_channels()

    markup = []
    if channels:
        for ch in channels:
            markup.append([
                InlineKeyboardButton(f"{ch.get('title')} ({ch.get('chat_id')})", callback_data=f"view_ch|{ch.get('chat_id')}")
            ])
    else:
        markup.append([InlineKeyboardButton("No channels found.", callback_data="noop")])

    markup.append([InlineKeyboardButton("🔙 Back", callback_data="admin_main")])

    await callback.edit_message_text("**📢 Storage Channels**\nClick to manage:", reply_markup=InlineKeyboardMarkup(markup))

@Client.on_callback_query(filters.regex(r"^view_ch\|"))
async def view_channel(client, callback):
    chat_id = int(callback.data.split("|")[1])
    # Need to fetch details? We have ID.
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("🗑 Remove Channel", callback_data=f"del_ch|{chat_id}")],
        [InlineKeyboardButton("🔙 Back", callback_data="admin_channels")]
    ])
    await callback.edit_message_text(f"**Channel Details**\nID: `{chat_id}`", reply_markup=markup)

@Client.on_callback_query(filters.regex(r"^del_ch\|"))
async def delete_channel(client, callback):
    chat_id = int(callback.data.split("|")[1])
    await db.remove_channel(chat_id)
    await callback.answer("Channel removed!", show_alert=True)
    await show_channels(client, callback)

# --- Bundles ---

@Client.on_callback_query(filters.regex(r"^admin_bundles$"))
async def show_bundles(client, callback):
    bundles = await db.get_all_bundles()
    # Just show count and option to create
    text = f"**📦 Bundles**\n\nTotal Created: {len(bundles)}\n\nUse the button below to start the interactive link creation."
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Create New Link", callback_data="start_create_link")],
        [InlineKeyboardButton("🔙 Back", callback_data="admin_main")]
    ])
    await callback.edit_message_text(text, reply_markup=markup)

@Client.on_callback_query(filters.regex(r"^start_create_link$"))
async def start_create_link_panel(client, callback):
    # We can trigger the existing command handler logic?
    # Or just tell user what to do.
    # The existing logic in admin_bundles.py uses `admin_states`.
    # We can invoke it by sending a fake message or just replicating the state init.

    from plugins.admin_bundles import admin_states

    admin_states[callback.from_user.id] = {"step": "wait_start_msg", "data": {}}

    await callback.message.delete()
    await client.send_message(
        callback.from_user.id,
        "🔄 **Link Creation Mode**\n\n"
        "Please **forward** the **first message** of the bundle from the storage channel."
    )

# --- Tasks ---

@Client.on_callback_query(filters.regex(r"^admin_tasks$"))
async def show_tasks(client, callback):
    tasks = await db.get_all_tasks()
    text = f"**📝 Tasks**\n\nTotal Tasks: {len(tasks)}"

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add Task", callback_data="panel_add_task")],
        [InlineKeyboardButton("📄 List All (Text)", callback_data="panel_list_tasks")],
        [InlineKeyboardButton("🔙 Back", callback_data="admin_main")]
    ])
    await callback.edit_message_text(text, reply_markup=markup)

@Client.on_callback_query(filters.regex(r"^panel_list_tasks$"))
async def panel_list_tasks(client, callback):
    tasks = await db.get_all_tasks()
    if not tasks:
        await callback.answer("No tasks.", show_alert=True)
        return

    text = "**📝 Tasks List:**\n\n"
    for t in tasks:
        opts = f" (Options: {', '.join(t.get('options', []))})" if t.get('options') else ""
        text += f"🔹 Q: {t['question']}\n   A: {t['answer']}{opts}\n\n"
        if len(text) > 3500: break # Truncate for now

    # We can't edit message with too long text usually, send new message?
    # Or just edit if fits.
    try:
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_tasks")]])
        await callback.edit_message_text(text, reply_markup=markup)
    except:
        await callback.message.delete()
        await client.send_message(callback.from_user.id, text)
        # Send menu again
        await show_main_menu(client.send_message(callback.from_user.id, "Menu:"))

@Client.on_callback_query(filters.regex(r"^panel_add_task$"))
async def panel_add_task(client, callback):
    panel_states[callback.from_user.id] = "wait_task_input"
    await callback.message.delete()
    await client.send_message(
        callback.from_user.id,
        "**➕ Add Task**\n\n"
        "Send the task in this format:\n"
        "`Question | Answer | Option1, Option2`\n\n"
        "Example:\n`What is 2+2? | 4`\n"
        "Or Quiz: `Capital? | Paris | London, Paris`\n\n"
        "Send /cancel to cancel."
    )

@Client.on_message(filters.user(Config.ADMIN_ID) & filters.text & ~filters.command(["admin", "cancel"]))
async def handle_panel_input(client, message):
    user_id = message.from_user.id
    if user_id in panel_states and panel_states[user_id] == "wait_task_input":
        text = message.text
        parts = [p.strip() for p in text.split("|")]

        if len(parts) < 2:
            await message.reply("❌ Format error. Try again: `Question | Answer`")
            return

        question = parts[0]
        answer = parts[1]
        options = []
        task_type = "text"

        if len(parts) > 2 and parts[2]:
            raw_opts = parts[2]
            options = [o.strip() for o in raw_opts.split(",")]
            task_type = "quiz" if options else "text"

        await db.add_task(question, answer, options, task_type)
        await message.reply(f"✅ Task Added!\n\nQ: {question}\nA: {answer}")

        del panel_states[user_id]
        await show_main_menu(message)
