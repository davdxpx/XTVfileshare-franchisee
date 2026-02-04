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
            InlineKeyboardButton("📢 DB Channels", callback_data="admin_channels"),
            InlineKeyboardButton("🔒 Force-Subs", callback_data="admin_force_subs")
        ],
        [
            InlineKeyboardButton("📦 Bundles", callback_data="admin_bundles"),
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

    share_enabled = await db.get_config("force_share_enabled", False)
    share_text = "✅ Force Share" if share_enabled else "❌ Force Share"

    markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(fs_text, callback_data="toggle_fs_panel"),
            InlineKeyboardButton(task_text, callback_data="toggle_task_panel")
        ],
        [
            InlineKeyboardButton(share_text, callback_data="toggle_share_panel"),
            InlineKeyboardButton("📝 Set Share Config", callback_data="set_share_config")
        ],
        [InlineKeyboardButton("🔙 Back", callback_data="admin_main")]
    ])

    await callback.edit_message_text("**⚙️ Settings**\nToggle features below:", reply_markup=markup)

@Client.on_callback_query(filters.regex(r"^toggle_(fs|task|share)_panel$"))
async def toggle_setting_panel(client, callback):
    setting = callback.data.split("_")[1] # fs, task, share
    if setting == "fs":
        curr = await db.get_config("force_sub_enabled", False)
        await db.update_config("force_sub_enabled", not curr)
    elif setting == "task":
        curr = await db.get_config("tasks_enabled", False)
        await db.update_config("tasks_enabled", not curr)
    elif setting == "share":
        curr = await db.get_config("force_share_enabled", False)
        await db.update_config("force_share_enabled", not curr)

    await show_settings(client, callback)

@Client.on_callback_query(filters.regex(r"^set_share_config$"))
async def set_share_config_start(client, callback):
    panel_states[callback.from_user.id] = "wait_share_link"
    await callback.message.delete()
    await client.send_message(
        callback.from_user.id,
        "**📝 Set Share Link**\n\n"
        "First, send the **Link** (Channel/Group/Bot) that users should share.\n"
        "Example: `https://t.me/mychannel`"
    )

# --- Channels (Storage) ---

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

# --- Force Subs ---

@Client.on_callback_query(filters.regex(r"^admin_force_subs$"))
async def show_force_subs(client, callback):
    channels = await db.get_force_sub_channels()

    markup = []
    if channels:
        for ch in channels:
            markup.append([
                InlineKeyboardButton(f"{ch.get('title')} ({ch.get('chat_id')})", callback_data=f"view_ch|{ch.get('chat_id')}")
            ])
    else:
        markup.append([InlineKeyboardButton("No FS channels.", callback_data="noop")])

    markup.append([InlineKeyboardButton("➕ Add Channel (Manual)", callback_data="panel_add_fs_manual")])
    markup.append([InlineKeyboardButton("🔙 Back", callback_data="admin_main")])

    await callback.edit_message_text("**🔒 Force Sub Channels**\nClick to manage:", reply_markup=InlineKeyboardMarkup(markup))

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
    # Determine type to return to correct menu? Or just go to main.
    # We can check type before deleting if we want perfectly correct navigation,
    # but removing and going back to main or trying to refresh current view is harder since we don't pass 'origin'.
    # Let's try to detect based on what view we are in? No context.
    # Just go back to main or try to guess.

    await db.remove_channel(chat_id)
    await callback.answer("Channel removed!", show_alert=True)
    await show_main_menu(callback)

@Client.on_callback_query(filters.regex(r"^panel_add_fs_manual$"))
async def panel_add_fs_manual(client, callback):
    panel_states[callback.from_user.id] = "wait_fs_input"
    await callback.message.delete()
    await client.send_message(
        callback.from_user.id,
        "**➕ Add Force Sub Channel**\n\n"
        "Please add the bot as Admin to the channel first!\n\n"
        "Then send the **Channel ID** (e.g. -100123456) or **Username** (@channel).\n"
        "Or forward a message from it."
    )

# --- Bundles ---

@Client.on_callback_query(filters.regex(r"^admin_bundles$"))
async def show_bundles(client, callback):
    bundles = await db.get_all_bundles()
    text = f"**📦 Bundles**\n\nTotal Created: {len(bundles)}\n\nManage your bundles below."
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Create New Link", callback_data="start_create_link")],
        [InlineKeyboardButton("✏️ Manage Bundles", callback_data="panel_manage_bundles")],
        [InlineKeyboardButton("🔙 Back", callback_data="admin_main")]
    ])
    await callback.edit_message_text(text, reply_markup=markup)

@Client.on_callback_query(filters.regex(r"^panel_manage_bundles$"))
async def manage_bundles_menu(client, callback):
    bundles = await db.get_all_bundles()
    if not bundles:
        await callback.answer("No bundles found.", show_alert=True)
        return

    # Sort recent
    recent = list(reversed(bundles))[:10]

    markup = []
    for b in recent:
        title = b.get("title", "Untitled")[:25]
        code = b.get("code")
        markup.append([InlineKeyboardButton(f"{title} ({code})", callback_data=f"manage_bund|{code}")])

    markup.append([InlineKeyboardButton("🔙 Back", callback_data="admin_bundles")])

    await callback.edit_message_text("**Select Bundle to Manage:**", reply_markup=InlineKeyboardMarkup(markup))

@Client.on_callback_query(filters.regex(r"^manage_bund\|"))
async def manage_single_bundle(client, callback):
    code = callback.data.split("|")[1]
    bundle = await db.get_bundle(code)
    if not bundle:
        await callback.answer("Bundle not found.", show_alert=True)
        await manage_bundles_menu(client, callback)
        return

    title = bundle.get("title", "Untitled")
    views = bundle.get("views", 0)

    text = f"**📦 Bundle Info**\n\nTitle: `{title}`\nCode: `{code}`\nViews: `{views}`"
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Rename", callback_data=f"rename_bund|{code}")],
        [InlineKeyboardButton("🗑 Delete", callback_data=f"del_bund_confirm|{code}")],
        [InlineKeyboardButton("🔙 Back", callback_data="panel_manage_bundles")]
    ])
    await callback.edit_message_text(text, reply_markup=markup)

@Client.on_callback_query(filters.regex(r"^del_bund_confirm\|"))
async def del_bund_confirm(client, callback):
    code = callback.data.split("|")[1]
    await db.delete_bundle(code)
    await callback.answer("Bundle deleted!", show_alert=True)
    await manage_bundles_menu(client, callback)

@Client.on_callback_query(filters.regex(r"^rename_bund\|"))
async def rename_bund_start(client, callback):
    code = callback.data.split("|")[1]
    panel_states[callback.from_user.id] = {"state": "wait_bundle_rename", "code": code}
    await callback.message.delete()
    await client.send_message(
        callback.from_user.id,
        f"**✏️ Rename Bundle**\n\nCode: `{code}`\n\nEnter new title (or /cancel):"
    )

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
        [InlineKeyboardButton("➕ Bulk Add Tasks", callback_data="panel_bulk_add_task")],
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

@Client.on_callback_query(filters.regex(r"^panel_bulk_add_task$"))
async def panel_bulk_add_task(client, callback):
    panel_states[callback.from_user.id] = "wait_bulk_task_input"
    await callback.message.delete()
    await client.send_message(
        callback.from_user.id,
        "**➕ Bulk Add Tasks**\n\n"
        "Send a list of tasks. **One task per line.**\n"
        "Format per line: `Question | Answer | Option1, Option2`\n\n"
        "Example:\n"
        "Q1? | A1\n"
        "Q2? | A2 | Opt1, Opt2\n\n"
        "Send /cancel to cancel."
    )

# Use ContinuePropagation to allow other handlers to run if not in state
from pyrogram import ContinuePropagation

@Client.on_message(filters.user(Config.ADMIN_ID) & filters.text & ~filters.command(["admin", "cancel", "start", "create_link"]), group=1)
async def handle_panel_input(client, message):
    user_id = message.from_user.id
    if user_id not in panel_states:
        raise ContinuePropagation

    # Check if state is dict (complex state) or str (legacy simple state)
    raw_state = panel_states[user_id]
    state_key = raw_state if isinstance(raw_state, str) else raw_state.get("state")

    if state_key == "wait_bundle_rename":
        code = raw_state["code"]
        new_title = message.text
        await db.update_bundle_title(code, new_title)
        await message.reply(f"✅ Bundle renamed to: `{new_title}`")
        del panel_states[user_id]
        await show_main_menu(message)
        return

    if state_key == "wait_share_link":
        link = message.text.strip()
        # Basic validation
        if not link.startswith("http") and not link.startswith("t.me"):
             await message.reply("⚠️ Warning: Link should start with http or t.me. Proceeding anyway.")

        # Save partially or just pass to next step?
        # Update state to wait for text
        panel_states[user_id] = {"state": "wait_share_text_final", "link": link}
        await message.reply(
            "✅ Link saved.\n\n"
            "**Now send the Text message** that accompanies the link:\n"
            "Example: `Hey, check out this cool bot!`"
        )
        return

    if state_key == "wait_share_text_final":
        text = message.text
        link = raw_state["link"]

        await db.update_config("force_share_link", link)
        await db.update_config("force_share_text", text)

        await message.reply(f"✅ **Force Share Configured!**\n\nLink: `{link}`\nText: `{text}`")
        del panel_states[user_id]
        await show_main_menu(message)
        return

    if state_key == "wait_fs_input":
        text = message.text
        chat_id = None

        # Try to parse ID
        if text.lstrip("-").isdigit():
            chat_id = int(text)
        elif text.startswith("@"):
            # We need to resolve username
            try:
                chat = await client.get_chat(text)
                chat_id = chat.id
            except Exception:
                await message.reply("❌ Could not resolve username. Make sure bot is admin or use ID.")
                return
        elif message.forward_from_chat:
             chat_id = message.forward_from_chat.id
        else:
             await message.reply("❌ Invalid input. Send ID, Username, or Forward.")
             return

        # Add as Force Sub
        try:
            chat = await client.get_chat(chat_id)
            invite = None
            try:
                invite_obj = await client.create_chat_invite_link(chat_id, name="Fileshare Bot FS")
                invite = invite_obj.invite_link
            except:
                invite = chat.invite_link

            await db.add_channel(chat_id, chat.title, chat.username, "force_sub", invite)
            await message.reply(f"✅ Added **{chat.title}** as Force Sub channel.")
            del panel_states[user_id]
            await show_main_menu(message)
        except Exception as e:
            await message.reply(f"❌ Error adding channel: {e}")

    elif state_key == "wait_task_input":
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

    elif state_key == "wait_bulk_task_input":
        text = message.text
        # Using raw text is safer for splitting.
        lines = text.split("\n")
        added = 0
        failed = 0

        for line in lines:
            line = line.strip()
            if not line: continue

            # Simple parsing: Q | A | Opts
            parts = [p.strip() for p in line.split("|")]
            if len(parts) < 2:
                # Try to be lenient? No, strict format needed for machine processing.
                failed += 1
                continue

            question = parts[0]
            answer = parts[1]
            options = []
            task_type = "text"

            if len(parts) > 2 and parts[2]:
                raw_opts = parts[2]
                options = [o.strip() for o in raw_opts.split(",")]
                task_type = "quiz" if options else "text"

            await db.add_task(question, answer, options, task_type)
            added += 1

        await message.reply(f"✅ Processed!\nAdded: {added}\nFailed: {failed}")
        del panel_states[user_id]
        await show_main_menu(message)

# Ensure cancel works for panel states explicitly
@Client.on_message(filters.command("cancel") & filters.user(Config.ADMIN_ID), group=1)
async def cancel_panel(client, message):
    user_id = message.from_user.id
    if user_id in panel_states:
        del panel_states[user_id]
        await message.reply("❌ Panel action cancelled.")
    else:
        # Let other handlers (like admin_bundles) handle it
        raise ContinuePropagation
