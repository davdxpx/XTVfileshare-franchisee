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
    # Franchisee: List ONLY PrivateDB groups
    groups = await db.groups_col_private.find({}).to_list(length=1000)
    logger.info(f"Groups loaded from PrivateDB: {len(groups)}")

    if not groups:
        await callback.answer("No local groups found.", show_alert=True)
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
    await db.add_log("delete_group", callback.from_user.id, f"Deleted {code}")
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

# --- Add Group Wizard (Scan Mode) ---

@Client.on_callback_query(filters.regex(r"^add_group_start$"))
async def add_group_start(client, callback):
    await callback.edit_message_text("⏳ **Scanning Bundles...**\nThis may take a moment.")

    # 1. Fetch all bundles that have tmdb_id
    # We want bundles where tmdb_id exists and is not null
    # Optimally, we use aggregation to group them

    pipeline = [
        {"$match": {"tmdb_id": {"$exists": True, "$ne": None}}},
        {"$group": {
            "_id": {
                "tmdb_id": "$tmdb_id",
                "media_type": "$media_type",
                "season": "$season",
                "episode_val": "$episodes_label" # New: Group by episode label too
            },
            "count": {"$sum": 1},
            "sample_title": {"$first": "$title"},
            "tmdb_title": {"$first": "$tmdb_title"},
            "tmdb_year": {"$first": "$tmdb_year"}
        }}
    ]

    results = await db.bundles_col.aggregate(pipeline).to_list(length=100)

    if not results:
        await callback.edit_message_text(
            "❌ No bundles found with TMDb metadata.\n\n"
            "Create bundles using the wizard first.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_grouped_bundles")]])
        )
        return

    # 2. Filter out existing groups
    # This is O(N) but manageable for now
    candidates = []

    for r in results:
        meta = r["_id"]
        tmdb_id = meta.get("tmdb_id")
        mtype = meta.get("media_type", "movie")
        season = meta.get("season")
        ep_label = meta.get("episode_val")

        # Determine episode_val for grouping logic
        # If label is digit, we group by it. If not (e.g. range or All), we group by Season (None).
        # Wait, if we group by "All" in aggregation, we get separate groups for "All" and "1-5".
        # But our DB logic for get_group_by_tmdb uses episode_val=None for Season Packs.
        # So if ep_label is NOT a digit, we treat it as None for checking existence.

        target_ep_val = ep_label if (ep_label and ep_label.isdigit()) else None

        # Check if group exists
        exists = await db.get_group_by_tmdb(tmdb_id, mtype, season, target_ep_val)

        if not exists:
            # Candidate!
            title = r.get("tmdb_title")
            year = r.get("tmdb_year")

            if not title:
                title = r.get("sample_title") or f"ID: {tmdb_id}"

            # Format display
            if mtype == "tv" and season:
                if target_ep_val:
                    display = f"{title} S{season} E{target_ep_val}"
                else:
                    display = f"{title} S{season}"
            else:
                display = f"{title}"

            if year: display += f" ({year})"

            # Avoid duplicates if multiple non-digit labels (e.g. "All" and "1-5") map to same Season group
            # We should probably merge them in display?
            # Or just show them. If we create group for "All", "1-5" will be auto-added later?
            # No, manual creation creates ONE group.
            # Let's verify if we already added a candidate for this target_ep_val

            # Unique key for candidates list
            cand_key = f"{tmdb_id}_{mtype}_{season}_{target_ep_val}"

            # Append if not seen (simple de-dupe logic needed?)
            # Actually, aggregation groups by specific label. "All" and "1-5" are distinct.
            # If both map to target_ep_val=None, we might show two buttons that do the same thing (Create Season Group).
            # That's fine.

            candidates.append({
                "display": display,
                "count": r["count"],
                "meta": meta,
                "target_ep": target_ep_val
            })

    if not candidates:
        await callback.edit_message_text(
            "✅ All bundles are already grouped!",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_grouped_bundles")]])
        )
        return

    # 3. Show List
    # Limit to 20 candidates
    markup = []
    for c in candidates[:20]:
        meta = c["meta"]
        # Encode data: create_grp|tmdb_id|type|season|ep_val
        # Shorten to stay within limits.

        sid = meta['tmdb_id']
        mt = meta.get('media_type')
        sea = meta.get('season')
        if sea is None: sea = "x"

        ep = c["target_ep"]
        if ep is None: ep = "x"

        # Format: cg|id|type|s|e (shorter prefix)
        data_str = f"cg|{sid}|{mt}|{sea}|{ep}"

        btn_text = f"{c['display']} ({c['count']} bundles)"
        markup.append([InlineKeyboardButton(btn_text, callback_data=data_str)])

    markup.append([InlineKeyboardButton("🔙 Back", callback_data="admin_grouped_bundles")])

    await callback.edit_message_text(
        f"**➕ Found {len(candidates)} Ungrouped Sets**\nSelect one to create a group:",
        reply_markup=InlineKeyboardMarkup(markup)
    )

@Client.on_callback_query(filters.regex(r"^cg\|"))
async def create_group_click(client, callback):
    try:
        parts = callback.data.split("|")
        # cg|id|type|s|e
        tmdb_id = parts[1]
        mtype = parts[2]
        season_str = parts[3]
        ep_str = parts[4]

        season = int(season_str) if season_str != "x" else None
        target_ep = ep_str if ep_str != "x" else None

        await callback.edit_message_text("⏳ **Creating Group...** fetching details...")

        # 1. Fetch details for nice title
        details = await get_tmdb_details(tmdb_id, mtype)
        if details:
            clean_title = details.get("name") or details.get("title") or "Untitled"
            year = (details.get("first_air_date") or details.get("release_date") or "")[:4]

            if mtype == "tv" and season:
                if target_ep:
                    group_title = f"{clean_title} S{season} E{target_ep}"
                else:
                    group_title = f"{clean_title} S{season}"
            else:
                group_title = f"{clean_title} ({year})"
        else:
            group_title = f"Group {tmdb_id}"

        # 2. Find bundles (Matching the criteria)
        query = {
            "tmdb_id": str(tmdb_id),
            "media_type": mtype
        }
        if season is not None:
            query["season"] = int(season)

        # Filter by episode label if target_ep is set
        if target_ep:
            query["episodes_label"] = target_ep
        else:
             # If Season Pack, we want ALL non-single-episode bundles?
             # Or just everything that isn't a single episode?
             # For simplicity, if creating a Season Group, we pull "All", "1-5", etc.
             # But NOT single episodes (which belong to their own groups).
             # So label must NOT be digit?
             # regex for NOT digit: {"$not": re.compile(r"^\d+$")}
             # But MongoDB $regex might be heavy.
             # Let's simplify: Pull everything that matches.
             # If a bundle is "E5" and we create "S1" group, it might get added?
             # Auto-group logic separates them. Manual creation should too.
             # If target_ep is None, we skip bundles where label IS digit.
             # Or we rely on the user to create the E5 group separately.
             # Let's try to be smart:
             query["episodes_label"] = {"$not": {"$regex": r"^\d+$"}}

        cursor = db.bundles_col.find(query)
        bundles = await cursor.to_list(length=100)
        bundle_codes = [b["code"] for b in bundles]

        # 3. Create
        code = generate_random_code()
        await db.create_group(code, group_title, tmdb_id, mtype, season, bundle_codes, target_ep)

        await db.add_log("create_group", callback.from_user.id, f"Created {group_title} ({code})")

        # Mark Request as Done
        try:
             await db.mark_request_done(tmdb_id, mtype)
             logger.info(f"Marked request {tmdb_id} as done via Group Wizard.")
        except Exception as e:
             logger.error(f"Failed to mark request done: {e}")

        await callback.edit_message_text(
            f"✅ **Group Created!**\n\n"
            f"Title: `{group_title}`\n"
            f"Bundles: `{len(bundle_codes)}`\n\n"
            f"Code: `{code}`",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_grouped_bundles")]])
        )

    except Exception as e:
        logger.error(f"Group create error: {e}")
        await callback.edit_message_text(f"❌ Error: {e}")

@Client.on_message(filters.user(list(Config.ADMIN_IDS)) & filters.text & ~filters.command(["admin", "cancel"]), group=3)
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
        await db.add_log("rename_group", user_id, f"Renamed {code} to {new_title}")
        await message.reply(f"✅ Group renamed to: `{new_title}`")
        del group_states[user_id]
        return
