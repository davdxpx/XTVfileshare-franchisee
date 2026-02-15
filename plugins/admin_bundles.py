from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from config import Config
from db import db
from utils.helpers import generate_random_code, get_file_id
from utils.tmdb import search_tmdb, get_tmdb_details
from log import get_logger
import asyncio

logger = get_logger(__name__)

# State management for wizard
# {user_id: {"step": str, "data": dict}}
admin_states = {}

# --- Helper to cancel ---
async def cancel_process(client, user_id, message=None):
    if user_id in admin_states:
        del admin_states[user_id]
    if message:
        await message.reply("❌ Operation cancelled.")

# --- Start Creation (Command) ---

@Client.on_message(filters.command("create_link") & filters.user(Config.ADMIN_ID))
async def create_link_start(client: Client, message: Message):
    # Support Manual? Maybe just deprecate manual for now or keep it simple.
    # The requirement is "personalisieren den vorgang viel besser".
    # Let's stick to interactive only for the rich metadata flow.

    admin_states[message.from_user.id] = {"step": "wait_start_msg", "data": {}}
    await message.reply(
        "🔄 **Bundle Wizard**\n\n"
        "Please **forward** the **first message** of the bundle from the storage channel."
    )

@Client.on_message(filters.user(list(Config.ADMIN_IDS)) & filters.forwarded)
async def on_forward_received(client: Client, message: Message):
    user_id = message.from_user.id

    # Auto-trigger single file mode if not in state
    if user_id not in admin_states:
        if message.forward_from_chat:
            # Single file forward trigger
            admin_states[user_id] = {
                "step": "select_media_type", # Jump straight to type selection
                "data": {
                    "channel_id": message.forward_from_chat.id,
                    "start_id": message.forward_from_message_id,
                    "end_id": message.forward_from_message_id # Single file
                }
            }
            markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("🎬 Movie", callback_data="type_movie")],
                [InlineKeyboardButton("📺 Series", callback_data="type_tv")],
                [InlineKeyboardButton("📝 Subtitles", callback_data="type_subs")]
            ])
            await message.reply(
                "⚡ **Single File Forward Detected**\n\n"
                "Creating bundle from this message.\n"
                "**Select Content Type:**",
                reply_markup=markup
            )
            return
        return

    state = admin_states[user_id]
    step = state["step"]

    if step == "wait_start_msg":
        if not message.forward_from_chat:
            await message.reply("❌ Please forward from a channel.")
            return

        state["data"]["channel_id"] = message.forward_from_chat.id
        state["data"]["start_id"] = message.forward_from_message_id
        state["step"] = "wait_end_msg"

        await message.reply(
            f"✅ Start set: `{message.forward_from_message_id}`\n"
            "Now **forward** the **last message**."
        )

    elif step == "wait_end_msg":
        if not message.forward_from_chat:
            await message.reply("❌ Please forward from a channel.")
            return

        if message.forward_from_chat.id != state["data"]["channel_id"]:
            await message.reply("❌ Channel mismatch! Forward from the same channel.")
            return

        state["data"]["end_id"] = message.forward_from_message_id

        # Now fetch file count to confirm?
        # Let's move to Media Type selection
        state["step"] = "select_media_type"

        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎬 Movie", callback_data="type_movie")],
            [InlineKeyboardButton("📺 Series", callback_data="type_tv")],
            [InlineKeyboardButton("📝 Subtitles", callback_data="type_subs")]
        ])

        await message.reply(
            "✅ Range Defined.\n\n**Select Content Type:**",
            reply_markup=markup
        )

# --- Wizard Callbacks ---

@Client.on_callback_query(filters.regex(r"^type_"))
async def on_media_type_select(client, callback):
    user_id = callback.from_user.id
    if user_id not in admin_states:
        await callback.answer("Session expired.", show_alert=True)
        return

    mtype = callback.data.split("_")[1] # movie, tv, subs
    admin_states[user_id]["data"]["media_type"] = mtype

    # Next: Title Input
    admin_states[user_id]["step"] = "wait_title_query"
    await callback.edit_message_text(
        f"Selected: **{mtype.upper()}**\n\n"
        "Please send the **Title** to search on TMDb (e.g. 'The Rookie')."
    )

from pyrogram import ContinuePropagation

@Client.on_message(filters.user(list(Config.ADMIN_IDS)) & filters.text & ~filters.command(["cancel", "create_link", "admin", "start"]), group=1)
async def on_text_input(client, message):
    user_id = message.from_user.id
    if user_id not in admin_states:
        raise ContinuePropagation

    state = admin_states[user_id]
    step = state["step"]

    if step == "wait_title_query":
        query = message.text
        mtype = state["data"]["media_type"]
        search_type = "tv" if mtype == "tv" or mtype == "subs" else "movie" # Assuming subs usually for series? Or ask?
        # User said: "Bei Untertiteln sowas ähnliches... Bei Film/Filmen ebenfalls fragen."
        # Let's assume subs can be for both, but usually series.
        # Actually user example: "Subtitles for The Rookie S1 E1".
        # Let's search 'tv' if series/subs, 'movie' if movie.
        # Wait, subs could be for movie.
        # Let's default 'subs' to 'tv' search for now based on context, or maybe search both?
        # Simpler: If subs, we might need to ask "Movie or Series?" before?
        # But for now, let's treat subs same as Series if user implies Series structure (S1 E1).

        results = await search_tmdb(query, search_type)

        if not results:
            await message.reply("❌ No results found on TMDb. Try another title.")
            return

        # Show results buttons
        buttons = []
        for r in results[:5]: # Top 5
            title = r.get("name") or r.get("title")
            year = (r.get("first_air_date") or r.get("release_date") or "")[:4]
            tid = r.get("id")
            buttons.append([InlineKeyboardButton(f"{title} ({year})", callback_data=f"tmdb_{tid}")])

        buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel_wizard")])

        state["step"] = "wait_tmdb_select"
        await message.reply("🔎 **Select the correct result:**", reply_markup=InlineKeyboardMarkup(buttons))

    elif step == "wait_season_num":
        # Expecting integer (1-20)
        try:
            season = int(message.text)
            state["data"]["season_number"] = season
            state["step"] = "wait_ep_count"
            await message.reply(f"✅ Season {season}.\n\n**How many episodes are in this season?** (e.g. 20)")
        except ValueError:
            await message.reply("❌ Please enter a valid number.")

    elif step == "wait_ep_count":
        try:
            count = int(message.text)
            state["data"]["episode_count"] = count
            state["step"] = "wait_bundle_eps"

            # Buttons for easy selection
            markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("All Episodes", callback_data="eps_all")],
                [InlineKeyboardButton("Manual Input (e.g. 1-5)", callback_data="eps_manual")]
            ])
            await message.reply(
                f"✅ {count} Episodes.\n\n**Which episodes are in this BUNDLE?**",
                reply_markup=markup
            )
        except ValueError:
            await message.reply("❌ Please enter a valid number.")

    elif step == "wait_manual_eps":
        # "1,3,5" or "1-5"
        state["data"]["bundle_episodes"] = message.text
        # Go to Quality (Series)
        state["step"] = "wait_quality"
        state["data"]["qualities"] = []
        await show_quality_menu(message, [])

    elif step == "wait_custom_title":
        text = message.text
        if text.strip() != "/skip":
            state["data"]["custom_title"] = text
        await finalize_bundle(client, user_id, message)

@Client.on_callback_query(filters.regex(r"^tmdb_"))
async def on_tmdb_select(client, callback):
    user_id = callback.from_user.id
    if user_id not in admin_states:
        await callback.answer("Expired.")
        return

    tmdb_id = callback.data.split("_")[1]
    admin_states[user_id]["data"]["tmdb_id"] = tmdb_id
    mtype = admin_states[user_id]["data"]["media_type"]

    if mtype == "tv":
        # Ask Season
        admin_states[user_id]["step"] = "wait_season_num"
        await callback.edit_message_text("✅ Selected.\n\n**Which Season is it?** (Send number 1-20)")
    elif mtype == "subs":
        # Assuming subs follow Series flow for now based on "The Rookie S1 E1" example
        admin_states[user_id]["step"] = "wait_season_num"
        await callback.edit_message_text("✅ Selected (Subs).\n\n**Which Season?**")
    else: # Movie
        # Ask Qualities
        # Checkbox style? "720p", "1080p".
        # We can simulate checkboxes by editing message, but simpler to just ask user to select ONE main quality or type?
        # User said: "different quality levels... selectable as a checkbox or button".
        # Let's do a multi-select menu.
        admin_states[user_id]["step"] = "wait_quality"
        admin_states[user_id]["data"]["qualities"] = []
        await show_quality_menu(callback, [])

async def show_quality_menu(message_or_callback, selected):
    # qual_720p, qual_1080p, qual_4k, qual_done
    options = ["720p", "1080p", "2160p (4K)", "HDR", "H.265"]
    buttons = []
    for opt in options:
        prefix = "✅ " if opt in selected else ""
        buttons.append(InlineKeyboardButton(f"{prefix}{opt}", callback_data=f"qual_{opt}"))

    # 2 per row
    rows = [buttons[i:i+2] for i in range(0, len(buttons), 2)]
    rows.append([InlineKeyboardButton("Done / Continue ➡️", callback_data="qual_done")])

    text = "**Select Qualities/Features:**\n(Click to toggle, then Done)"
    markup = InlineKeyboardMarkup(rows)

    if isinstance(message_or_callback, Message):
        await message_or_callback.reply(text, reply_markup=markup)
    else:
        await message_or_callback.edit_message_text(text, reply_markup=markup)

@Client.on_callback_query(filters.regex(r"^qual_"))
async def on_quality_toggle(client, callback):
    user_id = callback.from_user.id
    if user_id not in admin_states: return

    data = callback.data.split("_")[1]
    current_selected = admin_states[user_id]["data"]["qualities"]

    if data == "done":
        # Move to Title
        admin_states[user_id]["step"] = "wait_custom_title"
        await callback.message.delete()
        await client.send_message(user_id, "📝 **Custom Title**\n\nEnter a custom title for this bundle, or send `/skip` to use default.")
        return

    if data in current_selected:
        current_selected.remove(data)
    else:
        current_selected.append(data)

    admin_states[user_id]["data"]["qualities"] = current_selected
    await show_quality_menu(callback, current_selected)

@Client.on_callback_query(filters.regex(r"^eps_"))
async def on_eps_select(client, callback):
    user_id = callback.from_user.id
    mode = callback.data.split("_")[1]

    if mode == "all":
        admin_states[user_id]["data"]["bundle_episodes"] = "All"
        # Move to Quality selection (Series)
        admin_states[user_id]["step"] = "wait_quality"
        admin_states[user_id]["data"]["qualities"] = []
        await show_quality_menu(callback, [])

    elif mode == "manual":
        admin_states[user_id]["step"] = "wait_manual_eps"
        await callback.edit_message_text("⌨️ **Enter Episodes:**\n\nExamples: `1-5` or `1,3,5`")

async def auto_group_bundle(client, bundle_code, tmdb_id, media_type, season, bundle_title, episodes_label=None):
    if not tmdb_id:
        return None, None

    # Determine episode grouping logic
    # If media_type is TV and episodes_label looks like a single episode "5", we group by that.
    # If "All", we group by season (episode_val=None or "All"?). Let's stick to None for "Season Pack".
    # User requirement: "eine episode hochlade ... dann will ich auch so ein menü".

    episode_val = None
    if media_type == "tv" and episodes_label:
        # Check if single integer
        if episodes_label.isdigit():
            episode_val = episodes_label
        # Else (e.g. "1-5", "All"), we treat as Season Pack (None) or specific range?
        # User implies single episode grouping. Ranges are usually unique packs.
        # Let's group ONLY if it is a single episode number.

    # Check if group exists
    group = await db.get_group_by_tmdb(tmdb_id, media_type, season, episode_val)

    if group:
        await db.add_bundle_to_group(group["code"], bundle_code)
        logger.info(f"Auto-grouped bundle {bundle_code} into {group['title']}")
        return group["title"], group["code"]
    else:
        # Create new group
        details = await get_tmdb_details(tmdb_id, media_type)

        if details:
            clean_title = details.get("name") or details.get("title") or "Untitled"
            year = (details.get("first_air_date") or details.get("release_date") or "")[:4]

            if media_type == "tv" and season:
                if episode_val:
                    group_title = f"{clean_title} S{season} E{episode_val}"
                else:
                    group_title = f"{clean_title} S{season}"
            else:
                group_title = f"{clean_title} ({year})"
        else:
            # Fallback
            group_title = bundle_title or f"Group {tmdb_id}"

        code = generate_random_code()
        await db.create_group(code, group_title, tmdb_id, media_type, season, [bundle_code], episode_val)
        logger.info(f"Created new group {group_title} for {bundle_code}")
        return group_title, code

async def finalize_bundle(client, user_id, message_obj):
    state = admin_states[user_id]
    data = state["data"]

    # Extract existing data
    channel_id = data["channel_id"]
    start_id = data["start_id"]
    end_id = data.get("end_id", start_id) # if single

    # Process files (Fetching IDs)
    status_msg = await client.send_message(user_id, "⏳ **Finalizing Bundle...** Fetching files.")

    # Re-use logic from old create_bundle
    if start_id > end_id: start_id, end_id = end_id, start_id

    file_ids = []

    try:
        # Check channel
        if not await db.is_channel_approved(channel_id):
            await status_msg.edit("❌ Channel not approved.")
            return

        ids = list(range(start_id, end_id + 1))
        chunk_size = 200
        all_messages = []
        for i in range(0, len(ids), chunk_size):
            chunk = ids[i:i + chunk_size]
            msgs = await client.get_messages(channel_id, chunk)
            if not isinstance(msgs, list): msgs = [msgs]
            all_messages.extend(msgs)

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

        if not file_ids:
            await status_msg.edit("❌ No files found.")
            return

        # Generate Code
        code = generate_random_code()

        # Title logic
        bundle_title = data.get("custom_title")
        if not bundle_title:
             # Fallback
             bundle_title = f"Bundle {code}"
             # Or try to construct from TMDb if we had it stored?
             # We didn't store TMDb title in 'data' explicitly, but we can perhaps leave it as code or generic.
             # Ideally we should have stored TMDb title in state if we wanted to use it as default.

        # Save Bundle
        await db.create_bundle(
            code=code,
            file_ids=file_ids,
            source_channel=channel_id,
            title=bundle_title,
            original_range={"start": start_id, "end": end_id},
            # New Metadata
            tmdb_id=data.get("tmdb_id"),
            media_type=data.get("media_type"),
            season=data.get("season_number"),
            episodes_label=data.get("bundle_episodes"),
            qualities=data.get("qualities"),
            episode_count_total=data.get("episode_count")
        )

        await db.add_log("create_bundle", user_id, f"Created {code} ({bundle_title})")

        # Get TMDb Cache Title if possible
        tmdb_title_cache = None
        tmdb_year_cache = None

        if data.get("tmdb_id"):
             details = await get_tmdb_details(data.get("tmdb_id"), data.get("media_type"))
             if details:
                 tmdb_title_cache = details.get("name") or details.get("title")
                 date = details.get("release_date") or details.get("first_air_date") or ""
                 tmdb_year_cache = date[:4] if date else ""

        # Update Bundle with Cached Metadata (Async update after insert or re-insert?)
        # Better to update the doc we just inserted or update create_bundle to accept kwargs properly (it does).
        # But we already called create_bundle above. Let's just update it.
        await db.bundles_col.update_one(
            {"code": code},
            {"$set": {"tmdb_title": tmdb_title_cache, "tmdb_year": tmdb_year_cache}}
        )

        # Mark Request as Done (Integration)
        if data.get("tmdb_id") and data.get("media_type"):
             try:
                 await db.mark_request_done(data.get("tmdb_id"), data.get("media_type"))
                 logger.info(f"Marked request {data.get('tmdb_id')} as done.")
             except Exception as e:
                 logger.error(f"Failed to mark request done: {e}")

        # Auto Grouping
        group_title, group_code = await auto_group_bundle(
            client, code, data.get("tmdb_id"),
            data.get("media_type"), data.get("season_number"), bundle_title,
            data.get("bundle_episodes")
        )

        bot_username = Config.BOT_USERNAME
        link = f"https://t.me/{bot_username}?start={code}"

        msg_text = (
            f"✅ **Bundle Created!**\n\n"
            f"🎬 Type: {data.get('media_type')}\n"
            f"🆔 TMDb: {data.get('tmdb_id')}\n"
            f"📄 Files: {len(file_ids)}\n"
            f"🔗 Link: `{link}`"
        )

        if group_title:
            group_link = f"https://t.me/{bot_username}?start=group_{group_code}"
            msg_text += f"\n\n🔗 **Group:** `{group_title}`\n🔗 **Group Link:** `{group_link}`"

        await status_msg.edit(msg_text)

        del admin_states[user_id]

    except Exception as e:
        logger.error(f"Bundle Error: {e}")
        await status_msg.edit(f"❌ Error: {e}")

@Client.on_callback_query(filters.regex(r"^cancel_wizard$"))
async def cancel_wiz(client, callback):
    await cancel_process(client, callback.from_user.id, callback.message)

# --- Full Push Request Flow (FSM) ---

@Client.on_callback_query(filters.regex(r"^req_push_menu$"))
async def req_push_menu(client, callback):
    """Entry point for Request Push Menu"""
    user_id = callback.from_user.id
    # Initialize state
    admin_states[user_id] = {
        "flow": "push_request",
        "step": "select_bundles",
        "page": 0,
        "selected": []
    }
    await show_push_bundle_list(client, callback)

async def show_push_bundle_list(client, callback_query):
    user_id = callback_query.from_user.id
    state = admin_states.get(user_id)
    if not state or state.get("flow") != "push_request":
        await callback_query.answer("Session expired.", show_alert=True)
        return

    page = state.get("page", 0)
    selected = state.get("selected", [])
    limit = 10

    # Fetch local bundles only (PrivateDB)
    # We might need a helper in db to fetch paginated or just fetch all and slice
    # Since bundles_col_private isn't huge yet, fetch all is okay for now.
    all_bundles = await db.get_all_bundles()
    # Filter or sort? Reverse chronological usually best.
    all_bundles.reverse()

    total_bundles = len(all_bundles)
    start_idx = page * limit
    end_idx = start_idx + limit
    page_bundles = all_bundles[start_idx:end_idx]

    markup = []

    # List Bundles as Toggle Buttons
    for b in page_bundles:
        code = b["code"]
        title = b.get("title", "Untitled")[:20]
        # Checkmark if selected
        mark = "✅" if code in selected else "⬜"
        markup.append([
            InlineKeyboardButton(f"{mark} {title}", callback_data=f"push_toggle|{code}")
        ])

    # Pagination Control
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data="push_page_prev"))
    if end_idx < total_bundles:
        nav_row.append(InlineKeyboardButton("Next ➡️", callback_data="push_page_next"))
    if nav_row:
        markup.append(nav_row)

    # Action Buttons
    action_row = []
    if selected:
        action_row.append(InlineKeyboardButton(f"🚀 Preview ({len(selected)})", callback_data="push_preview"))

    action_row.append(InlineKeyboardButton("❌ Cancel", callback_data="cancel_wizard"))
    markup.append(action_row)

    text = f"**📡 Request Push**\n\nSelect bundles to push to CEO:\nPage {page+1}"

    try:
        await callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(markup))
    except Exception:
        pass # Message not modified

@Client.on_callback_query(filters.regex(r"^push_toggle\|"))
async def on_push_toggle(client, callback):
    user_id = callback.from_user.id
    state = admin_states.get(user_id)
    if not state: return

    code = callback.data.split("|")[1]
    if code in state["selected"]:
        state["selected"].remove(code)
    else:
        state["selected"].append(code)

    await show_push_bundle_list(client, callback)

@Client.on_callback_query(filters.regex(r"^push_page_"))
async def on_push_page(client, callback):
    user_id = callback.from_user.id
    state = admin_states.get(user_id)
    if not state: return

    direction = callback.data.split("_")[2]
    if direction == "prev":
        state["page"] = max(0, state["page"] - 1)
    elif direction == "next":
        state["page"] += 1

    await show_push_bundle_list(client, callback)

@Client.on_callback_query(filters.regex(r"^push_preview$"))
async def on_push_preview(client, callback):
    user_id = callback.from_user.id
    state = admin_states.get(user_id)
    if not state or not state["selected"]:
        await callback.answer("Nothing selected!", show_alert=True)
        return

    # Generate Preview
    selected_codes = state["selected"]
    preview_text = "**📡 Push Request Preview**\n\n"

    valid_bundles = []

    for code in selected_codes:
        b = await db.get_bundle(code)
        if not b: continue
        valid_bundles.append(b)

        title = b.get("title", "Untitled")
        tmdb = b.get("tmdb_id", "N/A")
        files = len(b.get("file_ids", []))
        quals = ", ".join(b.get("qualities", [])) or "Standard"

        preview_text += (
            f"🔹 **{title}**\n"
            f"   Code: `{code}` | TMDb: `{tmdb}`\n"
            f"   Files: `{files}` | Quality: `{quals}`\n\n"
        )

    if not valid_bundles:
        await callback.answer("No valid bundles found.", show_alert=True)
        return

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"✅ Confirm & Send ({len(valid_bundles)})", callback_data="push_confirm")],
        [InlineKeyboardButton("🔙 Edit Selection", callback_data="push_back_edit")]
    ])

    await callback.edit_message_text(preview_text, reply_markup=markup)

@Client.on_callback_query(filters.regex(r"^push_back_edit$"))
async def on_push_back(client, callback):
    # Just show list again, state is preserved
    await show_push_bundle_list(client, callback)

@Client.on_callback_query(filters.regex(r"^push_confirm$"))
async def on_push_confirm(client, callback):
    user_id = callback.from_user.id
    state = admin_states.get(user_id)
    if not state: return

    if not Config.CEO_CHANNEL_ID:
        await callback.answer("CEO Channel not configured!", show_alert=True)
        return

    selected_codes = state["selected"]

    # Check duplicates in MainDB?
    # Requirement: "Check MainDB read-only for duplicates before send."
    # If a bundle with same code exists in MainDB, warn? Or duplicate content?
    # Usually code is unique random. Unlikely collision.
    # Maybe check TMDb ID collision? "Did we already push this?"
    # Let's check code collision in MainDB just in case.

    duplicates = []
    final_push_list = []

    for code in selected_codes:
        # Check MainDB directly
        # We can use db.get_bundle but that checks Private first.
        # Use db.bundles_col_main directly or implement a specific check method.
        # Accessing private attr `bundles_col_main` from here is okay? Yes, python.
        exists_main = await db.bundles_col_main.find_one({"code": code})
        if exists_main:
            duplicates.append(code)
        else:
            final_push_list.append(code)

    if duplicates:
        await callback.answer(f"⚠️ Skipped {len(duplicates)} duplicates already in Global DB.", show_alert=True)

    if not final_push_list:
        await callback.answer("No bundles to push.", show_alert=True)
        return

    # Send Notification
    try:
        from datetime import datetime
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        msg_text = (
            f"🚀 **Push Request Incoming!**\n"
            f"📅 Time: `{ts}`\n"
            f"👤 Nehmer: `{user_id}`\n\n"
            "**Bundles:**\n"
        )

        for code in final_push_list:
            b = await db.get_bundle(code)
            title = b.get("title", "Untitled")
            tmdb = b.get("tmdb_id", "N/A")
            msg_text += f"📦 `{code}`: {title} (TMDb: {tmdb})\n"

        await client.send_message(Config.CEO_CHANNEL_ID, msg_text)
        await db.add_log("push_request_bulk", user_id, f"Requested push for {len(final_push_list)} bundles.")

        await callback.edit_message_text(f"✅ **Sent!**\n\nRequest for {len(final_push_list)} bundles sent to CEO.")
        del admin_states[user_id]

    except Exception as e:
        logger.error(f"Push send error: {e}")
        await callback.answer("Failed to send request.", show_alert=True)
