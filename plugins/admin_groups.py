from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram import ContinuePropagation
from config import Config
from db import db
from utils.helpers import generate_random_code
from utils.tmdb import get_tmdb_details
from log import get_logger

logger = get_logger(__name__)

# State for group wizard
# {user_id: {"state": "...", "data": ...}}
group_states = {}

@Client.on_callback_query(filters.regex(r"^admin_grouped_bundles$"))
async def admin_grouped_bundles(client, callback):
    text = "**📦 Grouped Bundles**\n\nManage your content groups here."
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 List Groups", callback_data="list_groups")],
        [InlineKeyboardButton("➕ Create Group (Manual)", callback_data="add_group_start")],
        [InlineKeyboardButton("🔙 Back", callback_data="admin_main")]
    ])
    await callback.edit_message_text(text, reply_markup=markup)

@Client.on_callback_query(filters.regex(r"^list_groups$"))
async def list_groups(client, callback):
    groups = await db.get_all_groups()
    if not groups:
        await callback.answer("No groups found.", show_alert=True)
        # Still show menu if empty
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Create Group", callback_data="add_group_start")],
            [InlineKeyboardButton("🔙 Back", callback_data="admin_grouped_bundles")]
        ])
        try:
            await callback.edit_message_text("No groups found.", reply_markup=markup)
        except: pass
        return

    # Pagination? Let's just show recent 20 for now.
    recent = list(reversed(groups))[:20]

    markup = []
    for g in recent:
        title = g.get("title", "Untitled")
        code = g.get("code")
        count = len(g.get("bundles", []))
        markup.append([InlineKeyboardButton(f"{title} ({count})", callback_data=f"view_group|{code}")])

    markup.append([InlineKeyboardButton("🔙 Back", callback_data="admin_grouped_bundles")])
    await callback.edit_message_text("**📋 Select a Group:**", reply_markup=InlineKeyboardMarkup(markup))

@Client.on_callback_query(filters.regex(r"^view_group\|"))
async def view_group(client, callback):
    code = callback.data.split("|")[1]
    group = await db.get_group(code)
    if not group:
        await callback.answer("Group not found.", show_alert=True)
        await list_groups(client, callback)
        return

    title = group.get("title", "Untitled")
    tmdb_id = group.get("tmdb_id", "N/A")
    bundles = group.get("bundles", [])

    bot_username = Config.BOT_USERNAME
    link = f"https://t.me/{bot_username}?start=group_{code}"

    text = (
        f"**📦 Group: {title}**\n\n"
        f"🆔 TMDb: `{tmdb_id}`\n"
        f"🔗 Link: `{link}`\n"
        f"📂 Bundles: `{len(bundles)}`"
    )

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Rename", callback_data=f"rename_group|{code}")],
        [InlineKeyboardButton("📂 Manage Bundles", callback_data=f"manage_group_bundles|{code}")],
        [InlineKeyboardButton("🗑 Delete Group", callback_data=f"del_group_confirm|{code}")],
        [InlineKeyboardButton("🔙 Back", callback_data="list_groups")]
    ])
    await callback.edit_message_text(text, reply_markup=markup)

@Client.on_callback_query(filters.regex(r"^manage_group_bundles\|"))
async def manage_group_bundles(client, callback):
    code = callback.data.split("|")[1]
    group = await db.get_group(code)
    if not group: return

    bundle_codes = group.get("bundles", [])
    if not bundle_codes:
        await callback.answer("No bundles in this group.", show_alert=True)
        # Show empty list?
        markup = [[InlineKeyboardButton("🔙 Back", callback_data=f"view_group|{code}")]]
        await callback.edit_message_text(f"**📂 Bundles in {group.get('title')}**\n(Empty)", reply_markup=InlineKeyboardMarkup(markup))
        return

    markup = []
    for b_code in bundle_codes:
        # Fetch bundle details for name
        bundle = await db.get_bundle(b_code)
        if bundle:
            b_title = bundle.get("title", b_code)
            # Add Remove button
            markup.append([
                InlineKeyboardButton(f"{b_title}", callback_data="noop"),
                InlineKeyboardButton("🗑 Remove", callback_data=f"rem_bund_from_grp|{code}|{b_code}")
            ])
        else:
            # Bundle might be deleted
             markup.append([
                InlineKeyboardButton(f"{b_code} (Deleted)", callback_data="noop"),
                InlineKeyboardButton("🗑 Clean", callback_data=f"rem_bund_from_grp|{code}|{b_code}")
            ])

    markup.append([InlineKeyboardButton("🔙 Back", callback_data=f"view_group|{code}")])
    await callback.edit_message_text(f"**📂 Bundles in {group.get('title')}**", reply_markup=InlineKeyboardMarkup(markup))

@Client.on_callback_query(filters.regex(r"^rem_bund_from_grp\|"))
async def remove_bundle_from_group(client, callback):
    _, g_code, b_code = callback.data.split("|")
    await db.remove_bundle_from_group(g_code, b_code)
    await callback.answer("Removed!", show_alert=True)
    await manage_group_bundles(client, callback) # Refresh

@Client.on_callback_query(filters.regex(r"^del_group_confirm\|"))
async def del_group_confirm(client, callback):
    code = callback.data.split("|")[1]
    await db.delete_group(code)
    await callback.answer("Group deleted!", show_alert=True)
    await list_groups(client, callback)

@Client.on_callback_query(filters.regex(r"^rename_group\|"))
async def rename_group_start(client, callback):
    code = callback.data.split("|")[1]
    group_states[callback.from_user.id] = {"state": "wait_group_rename", "code": code}
    await callback.message.delete()
    await client.send_message(
        callback.from_user.id,
        f"**✏️ Rename Group**\n\nCode: `{code}`\n\nEnter new title:"
    )

# --- Add Group Wizard ---

@Client.on_callback_query(filters.regex(r"^add_group_start$"))
async def add_group_start(client, callback):
    group_states[callback.from_user.id] = {"state": "wait_group_tmdb"}
    await callback.message.delete()
    await client.send_message(
        callback.from_user.id,
        "**➕ Create Group**\n\n"
        "Enter **TMDb ID** to scan for bundles and create a group.\n"
        "(e.g. `12345`)"
    )

async def finish_create_group(client, user_id, message):
    state = group_states.get(user_id)
    if not state: return

    tmdb_id = state.get("tmdb_id")
    mtype = state.get("type")
    season = state.get("season")

    # Check if exists
    existing = await db.get_group_by_tmdb(tmdb_id, mtype, season)
    if existing:
        await message.reply(f"❌ Group already exists: **{existing.get('title')}**\nCode: `{existing.get('code')}`")
        del group_states[user_id]
        return

    # Scan for bundles
    query = {
        "tmdb_id": str(tmdb_id),
        "media_type": mtype
    }
    if season is not None:
        query["season"] = int(season)

    # We need to access bundles_col directly as get_all_bundles doesn't filter
    # And loading all bundles is bad if many.
    # Using private access to col for now as this is a plugin
    cursor = db.bundles_col.find(query)
    found_bundles = await cursor.to_list(length=100)

    if not found_bundles:
        await message.reply("⚠️ No existing bundles found with this metadata. Creating empty group.")

    bundle_codes = [b["code"] for b in found_bundles]

    # Get Title
    details = await get_tmdb_details(tmdb_id, mtype)
    if details:
        clean_title = details.get("name") or details.get("title") or "Untitled"
        year = (details.get("first_air_date") or details.get("release_date") or "")[:4]

        if mtype == "tv" and season:
            group_title = f"{clean_title} S{season}"
        else:
            group_title = f"{clean_title} ({year})"
    else:
        group_title = f"Group {tmdb_id}"

    code = generate_random_code()
    await db.create_group(code, group_title, tmdb_id, mtype, season, bundle_codes)

    text = (
        f"✅ **Group Created!**\n\n"
        f"Title: `{group_title}`\n"
        f"Bundles Added: `{len(bundle_codes)}`\n"
        f"Code: `{code}`"
    )
    await message.reply(text)
    del group_states[user_id]


@Client.on_callback_query(filters.regex(r"^grp_type_"))
async def group_type_select(client, callback):
    user_id = callback.from_user.id
    if user_id not in group_states: return

    mtype = callback.data.split("_")[2] # movie or tv
    group_states[user_id]["type"] = mtype

    if mtype == "tv":
        group_states[user_id]["state"] = "wait_group_season"
        await callback.edit_message_text("✅ Series selected.\n\n**Enter Season Number:** (e.g. 1)")
    else:
        # Movie -> Proceed
        group_states[user_id]["season"] = None
        await callback.message.delete()
        await finish_create_group(client, user_id, callback.message)

@Client.on_message(filters.user(Config.ADMIN_ID) & filters.text & ~filters.command(["admin", "cancel"]), group=3)
async def group_input_handler(client, message):
    user_id = message.from_user.id
    if user_id not in group_states:
        raise ContinuePropagation

    state = group_states[user_id]
    s_key = state.get("state")

    if s_key == "wait_group_rename":
        new_title = message.text.strip()
        code = state["code"]
        await db.update_group_title(code, new_title)
        await message.reply(f"✅ Group renamed to: `{new_title}`")
        del group_states[user_id]
        return

    if s_key == "wait_group_tmdb":
        try:
            tmdb_id = message.text.strip() # keep as string for flexibility? db uses string.
            if not tmdb_id.isdigit():
                 await message.reply("❌ ID must be numeric.")
                 return

            # Ask Type
            group_states[user_id] = {"state": "wait_group_type", "tmdb_id": tmdb_id}

            markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("🎬 Movie", callback_data="grp_type_movie")],
                [InlineKeyboardButton("📺 Series", callback_data="grp_type_tv")]
            ])
            await message.reply(f"✅ ID: `{tmdb_id}`\n\n**Select Type:**", reply_markup=markup)
        except Exception as e:
            await message.reply(f"❌ Error: {e}")
        return

    if s_key == "wait_group_season":
        try:
            season = int(message.text.strip())
            state["season"] = season
            await finish_create_group(client, user_id, message)
        except:
            await message.reply("❌ Invalid number.")
        return
