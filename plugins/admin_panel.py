from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from config import Config
from db import db
from log import get_logger
from pyrogram import ContinuePropagation
from datetime import datetime

logger = get_logger(__name__)

# Shared state for admin inputs
panel_states = {}

# --- Main Admin Panel ---

@Client.on_message(filters.command("admin") & filters.user(list(Config.ADMIN_IDS)))
async def admin_panel(client: Client, message: Message):
    user_id = message.from_user.id
    logger.info(f"user_id check: {user_id} vs {Config.ADMIN_IDS}")
    await show_main_menu(message)

async def show_main_menu(message_or_callback):
    text = "**🛡️ Admin Panel**\nSelect a category to manage:"
    markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 Stats", callback_data="admin_stats"),
            InlineKeyboardButton("🏢 Franchise Dashboard", callback_data="admin_franchise_dash")
        ],
        [
            InlineKeyboardButton("⚙️ Settings", callback_data="admin_settings_menu"),
            InlineKeyboardButton("💰 Monetization", callback_data="admin_monetization")
        ],
        [
            InlineKeyboardButton("🚀 Community Growth", callback_data="admin_growth"),
            InlineKeyboardButton("📦 Bundles", callback_data="admin_bundles")
        ],
        [
            InlineKeyboardButton("📦 Grouped Bundles", callback_data="admin_grouped_bundles"),
            InlineKeyboardButton("📢 Channels", callback_data="admin_channels_menu")
        ],
        [
            InlineKeyboardButton("📝 Tasks", callback_data="admin_tasks"),
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

# --- Franchise Dashboard ---

@Client.on_callback_query(filters.regex(r"^admin_franchise_dash$"))
async def show_franchise_dash(client, callback):
    # Franchise Stats
    total_users = await db.get_total_users() # Shared

    # Bundle Stats
    local_bundles = len(await db.get_all_bundles()) # Private only
    global_bundles = await db.get_global_bundles_count()

    text = (
        "**🏢 Franchise Dashboard**\n\n"
        "🌐 **Network Stats (Shared):**\n"
        f"• Total Users: `{total_users}`\n"
        f"• Global Bundles: `{global_bundles}`\n\n"
        "🏠 **Local Stats (PrivateDB):**\n"
        f"• Local Bundles: `{local_bundles}`\n"
        "• Push Status: 🟢 Active\n\n"
        "__Growth Tips:__\n"
        "💡 Request push for 5+ bundles to grow network reach.\n"
        "💡 Create unique local bundles to attract users.\n"
        "💡 Use 'Request Push' to share top content globally!"
    )

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("📡 Request Push Menu", callback_data="req_push_menu")],
        [InlineKeyboardButton("🔙 Back", callback_data="admin_main")]
    ])
    await callback.edit_message_text(text, reply_markup=markup)

@Client.on_callback_query(filters.regex(r"^admin_stats$"))
async def show_stats(client, callback):
    bundles = await db.get_all_bundles()
    total_views = sum(b.get("views", 0) for b in bundles)
    popular = sorted(bundles, key=lambda x: x.get("views", 0), reverse=True)[:5]

    # New Metrics
    total_users = await db.get_total_users()
    active_24h = await db.get_active_users_24h()
    new_users_24h = await db.get_new_users_count(1)
    new_users_week = await db.get_new_users_count(7)

    prem_users = await db.users_col.count_documents({"is_premium": True})

    pop_text = ""
    for p in popular:
        pop_text += f"- {p.get('title')} ({p.get('views', 0)} views)\n"

    text = (
        f"**📊 Statistics Dashboard**\n\n"
        f"👥 **Users:**\n"
        f"• Total: `{total_users}`\n"
        f"• Active (24h): `{active_24h}`\n"
        f"• New (24h): `{new_users_24h}`\n"
        f"• New (Week): `{new_users_week}`\n\n"
        f"💎 **Premium:** `{prem_users}` active\n\n"
        f"📦 **Content:**\n"
        f"• Bundles: `{len(bundles)}`\n"
        f"• Total Views: `{total_views}`\n\n"
        f"**🔥 Top Bundles:**\n{pop_text}"
    )

    markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_main")]])
    await callback.edit_message_text(text, reply_markup=markup)

# --- Channels Menu (Storage, Force Subs, Share) ---

@Client.on_callback_query(filters.regex(r"^admin_channels_menu$"))
async def admin_channels_menu(client, callback):
    text = "**📢 Channel Management**"
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("🗄️ DB Channels (Storage)", callback_data="admin_channels")],
        [InlineKeyboardButton("🔒 Force-Sub Channels", callback_data="admin_force_subs")],
        # [InlineKeyboardButton("🏢 Franchise Channels", callback_data="admin_franchise_channels")], # CEO Only
        [InlineKeyboardButton("📢 Force-Share Channels", callback_data="admin_share_channels")],
        [InlineKeyboardButton("🔙 Back", callback_data="admin_main")]
    ])
    await callback.edit_message_text(text, reply_markup=markup)

# --- Settings Menu ---

@Client.on_callback_query(filters.regex(r"^admin_settings_menu$"))
async def admin_settings_menu(client, callback):
    text = "**⚙️ Settings**"
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("🛠️ General Config", callback_data="admin_settings_general")],
        [InlineKeyboardButton("📦 Group Config", callback_data="admin_settings_groups")],
        [InlineKeyboardButton("🛡️ Anti-Leech Config", callback_data="admin_settings_leech")],
        [InlineKeyboardButton("🔙 Back", callback_data="admin_main")]
    ])
    await callback.edit_message_text(text, reply_markup=markup)

@Client.on_callback_query(filters.regex(r"^admin_settings_groups$"))
async def admin_settings_groups(client, callback):
    enabled = await db.get_config("grouped_bundles_enabled", True)
    redirect = await db.get_config("single_bundle_redirect", True)

    text = (
        "**📦 Group Settings**\n\n"
        f"Enable Groups: `{enabled}`\n"
        f"Smart Redirect: `{redirect}`\n"
        "__(If enabled, specific quality links will open the Group Menu if multiple options exist)__"
    )

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"Toggle Groups ({enabled})", callback_data="toggle_grp_enabled")],
        [InlineKeyboardButton(f"Toggle Redirect ({redirect})", callback_data="toggle_grp_redirect")],
        [InlineKeyboardButton("🔙 Back", callback_data="admin_settings_menu")]
    ])
    await callback.edit_message_text(text, reply_markup=markup)

@Client.on_callback_query(filters.regex(r"^toggle_grp_"))
async def toggle_group_settings(client, callback):
    mode = callback.data.split("_")[2]
    if mode == "enabled":
        curr = await db.get_config("grouped_bundles_enabled", True)
        await db.update_config("grouped_bundles_enabled", not curr)
    elif mode == "redirect":
        curr = await db.get_config("single_bundle_redirect", True)
        await db.update_config("single_bundle_redirect", not curr)

    await admin_settings_groups(client, callback)

@Client.on_callback_query(filters.regex(r"^admin_settings_general$"))
async def admin_settings_general(client, callback):
    fs_enabled = await db.get_config("force_sub_enabled", False)
    tasks_enabled = await db.get_config("tasks_enabled", False)
    share_enabled = await db.get_config("force_share_enabled", False)

    fs_text = "✅ Force Sub" if fs_enabled else "❌ Force Sub"
    task_text = "✅ Tasks" if tasks_enabled else "❌ Tasks"
    share_text = "✅ Force Share" if share_enabled else "❌ Force Share"

    markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(fs_text, callback_data="toggle_fs_panel"),
            InlineKeyboardButton(task_text, callback_data="toggle_task_panel")
        ],
        [InlineKeyboardButton(share_text, callback_data="toggle_share_panel")],
        [InlineKeyboardButton("🔙 Back", callback_data="admin_settings_menu")]
    ])
    await callback.edit_message_text("**🛠️ General Config**\nToggle features:", reply_markup=markup)

@Client.on_callback_query(filters.regex(r"^toggle_(fs|task|share)_panel$"))
async def toggle_setting_panel(client, callback):
    setting = callback.data.split("_")[1]
    if setting == "fs":
        curr = await db.get_config("force_sub_enabled", False)
        await db.update_config("force_sub_enabled", not curr)
    elif setting == "task":
        curr = await db.get_config("tasks_enabled", False)
        await db.update_config("tasks_enabled", not curr)
    elif setting == "share":
        curr = await db.get_config("force_share_enabled", False)
        await db.update_config("force_share_enabled", not curr)
    await admin_settings_general(client, callback)

@Client.on_callback_query(filters.regex(r"^admin_settings_leech$"))
async def admin_settings_leech(client, callback):
    curr = await db.get_config("auto_delete_time", 0)
    text = f"**🛡️ Anti-Leech (Auto-Delete)**\n\nCurrent: `{curr} minutes` (0 = Disabled)"
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Set Time", callback_data="set_autodel_time")],
        [InlineKeyboardButton("🔙 Back", callback_data="admin_settings_menu")]
    ])
    await callback.edit_message_text(text, reply_markup=markup)

@Client.on_callback_query(filters.regex(r"^set_autodel_time$"))
async def set_autodel_time(client, callback):
    panel_states[callback.from_user.id] = "wait_autodel_input"
    await callback.message.delete()
    await client.send_message(callback.from_user.id, "**🛡️ Set Auto-Delete Time**\n\nEnter minutes (0 to disable):")

# --- Monetization ---

@Client.on_callback_query(filters.regex(r"^admin_monetization$"))
async def admin_monetization(client, callback):
    text = "**💰 Monetization**"
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("🌟 Manage Premium Users", callback_data="admin_premium_users")],
        [InlineKeyboardButton("🔙 Back", callback_data="admin_main")]
    ])
    await callback.edit_message_text(text, reply_markup=markup)

@Client.on_callback_query(filters.regex(r"^admin_premium_users$"))
async def admin_premium_users(client, callback):
    text = "**🌟 Premium Users Management**"
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add Premium User", callback_data="add_prem_user")],
        [InlineKeyboardButton("➖ Remove Premium User", callback_data="rem_prem_user")],
        [InlineKeyboardButton("📋 List Active", callback_data="list_prem_users")],
        [InlineKeyboardButton("🔙 Back", callback_data="admin_monetization")]
    ])
    await callback.edit_message_text(text, reply_markup=markup)

@Client.on_callback_query(filters.regex(r"^add_prem_user$"))
async def add_prem_user(client, callback):
    panel_states[callback.from_user.id] = "wait_prem_add_id"
    await callback.message.delete()
    await client.send_message(callback.from_user.id, "**➕ Add Premium User**\n\nSend User ID:")

@Client.on_callback_query(filters.regex(r"^rem_prem_user$"))
async def rem_prem_user(client, callback):
    panel_states[callback.from_user.id] = "wait_prem_rem_id"
    await callback.message.delete()
    await client.send_message(callback.from_user.id, "**➖ Remove Premium User**\n\nSend User ID:")

@Client.on_callback_query(filters.regex(r"^list_prem_users$"))
async def list_prem_users(client, callback):
    users = await db.get_premium_users()
    if not users:
        await callback.answer("No premium users.", show_alert=True)
        return

    out = "🌟 **Premium Users:**\n"
    for u in users[:50]:
        expiry = u.get('premium_expiry', 0)
        try:
            dt = datetime.fromtimestamp(expiry).strftime('%Y-%m-%d %H:%M')
        except:
            dt = "Invalid"
        out += f"`{u['user_id']}` (Expires: {dt})\n"

    await callback.message.delete()
    await client.send_message(callback.from_user.id, out)
    await show_main_menu(client.send_message(callback.from_user.id, "Menu:"))

# --- Community Growth ---

@Client.on_callback_query(filters.regex(r"^admin_growth$"))
async def admin_growth(client, callback):
    text = "**🚀 Community Growth & Engagement**"
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Broadcast Tool", callback_data="admin_broadcast_menu")],
        [InlineKeyboardButton("🔗 Referral Settings", callback_data="admin_referral_settings")],
        [InlineKeyboardButton("📅 Daily Bonus", callback_data="admin_daily_bonus")],
        [InlineKeyboardButton("🎟️ Coupons", callback_data="admin_coupons")],
        [InlineKeyboardButton("🔙 Back", callback_data="admin_main")]
    ])
    await callback.edit_message_text(text, reply_markup=markup)

# --- Coupons ---

@Client.on_callback_query(filters.regex(r"^admin_coupons$"))
async def admin_coupons(client, callback):
    coupons = await db.get_all_coupons()
    text = f"**🎟️ Coupons**\n\nActive Codes: {len(coupons)}"

    markup = [
        [InlineKeyboardButton("➕ Create Coupon", callback_data="create_coupon_start")],
        [InlineKeyboardButton("🔙 Back", callback_data="admin_growth")]
    ]

    if coupons:
        list_text = "\n\n"
        for c in coupons:
             list_text += f"`{c['code']}`: {c['reward_hours']}h (Used: {c['used_count']}/{c['usage_limit']})\n"
        text += list_text
        # Add Delete buttons? simpler to just list for now or use command to delete.
        # Let's add delete button
        markup.insert(1, [InlineKeyboardButton("🗑 Delete Coupon", callback_data="del_coupon_start")])

    await callback.edit_message_text(text, reply_markup=InlineKeyboardMarkup(markup))

@Client.on_callback_query(filters.regex(r"^create_coupon_start$"))
async def create_coupon_start(client, callback):
    panel_states[callback.from_user.id] = "wait_coupon_code"
    await callback.message.delete()
    await client.send_message(callback.from_user.id, "**🎟️ Create Coupon**\n\nEnter the **Code** (e.g. `SUMMER24`):")

@Client.on_callback_query(filters.regex(r"^del_coupon_start$"))
async def del_coupon_start(client, callback):
    panel_states[callback.from_user.id] = "wait_coupon_del"
    await callback.message.delete()
    await client.send_message(callback.from_user.id, "**🗑 Delete Coupon**\n\nEnter the **Code** to delete:")

# --- Daily Bonus ---

@Client.on_callback_query(filters.regex(r"^admin_daily_bonus$"))
async def admin_daily_bonus(client, callback):
    enabled = await db.get_config("daily_bonus_enabled", False)
    reward = await db.get_config("daily_bonus_reward", 1)

    status = "✅ Enabled" if enabled else "❌ Disabled"

    text = (
        f"**📅 Daily Bonus**\n\n"
        f"Status: {status}\n"
        f"Reward: `{reward} hours` Premium"
    )

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("Toggle Status", callback_data="toggle_daily_bonus")],
        [InlineKeyboardButton("✏️ Set Reward", callback_data="set_daily_reward")],
        [InlineKeyboardButton("🔙 Back", callback_data="admin_growth")]
    ])
    await callback.edit_message_text(text, reply_markup=markup)

@Client.on_callback_query(filters.regex(r"^toggle_daily_bonus$"))
async def toggle_daily_bonus(client, callback):
    curr = await db.get_config("daily_bonus_enabled", False)
    await db.update_config("daily_bonus_enabled", not curr)
    await admin_daily_bonus(client, callback)

@Client.on_callback_query(filters.regex(r"^set_daily_reward$"))
async def set_daily_reward(client, callback):
    panel_states[callback.from_user.id] = "wait_daily_reward"
    await callback.message.delete()
    await client.send_message(callback.from_user.id, "**Set Daily Reward**\n\nEnter hours:")

@Client.on_callback_query(filters.regex(r"^admin_referral_settings$"))
async def admin_referral_settings(client, callback):
    target = await db.get_config("referral_target", 10)
    hours = await db.get_config("referral_reward_hours", 24)

    text = (
        f"**🔗 Referral Settings**\n\n"
        f"Target Invites: `{target}`\n"
        f"Reward (Hours): `{hours}`"
    )
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Set Target", callback_data="set_ref_target")],
        [InlineKeyboardButton("✏️ Set Reward Duration", callback_data="set_ref_reward")],
        [InlineKeyboardButton("🔙 Back", callback_data="admin_growth")]
    ])
    await callback.edit_message_text(text, reply_markup=markup)

@Client.on_callback_query(filters.regex(r"^set_ref_target$"))
async def set_ref_target(client, callback):
    panel_states[callback.from_user.id] = "wait_ref_target"
    await callback.message.delete()
    await client.send_message(callback.from_user.id, "**Set Referral Target**\n\nHow many invites for reward?")

@Client.on_callback_query(filters.regex(r"^set_ref_reward$"))
async def set_ref_reward(client, callback):
    panel_states[callback.from_user.id] = "wait_ref_reward"
    await callback.message.delete()
    await client.send_message(callback.from_user.id, "**Set Reward Duration**\n\nHow many hours of Premium?")


# --- Force Share Channels ---

@Client.on_callback_query(filters.regex(r"^admin_share_channels$"))
async def show_share_channels(client, callback):
    channels = await db.get_share_channels()

    markup = []
    if channels:
        for ch in channels:
            link = ch.get("link", "Link")
            markup.append([
                InlineKeyboardButton(f"{link[:20]}...", callback_data=f"view_share|{link}")
            ])
    else:
        markup.append([InlineKeyboardButton("No Share Channels.", callback_data="noop")])

    markup.append([InlineKeyboardButton("➕ Add Share Channel", callback_data="add_share_start")])
    markup.append([InlineKeyboardButton("🔙 Back", callback_data="admin_channels_menu")])

    await callback.edit_message_text("**📢 Force-Share Channels**\nClick to manage:", reply_markup=InlineKeyboardMarkup(markup))

@Client.on_callback_query(filters.regex(r"^add_share_start$"))
async def add_share_start(client, callback):
    panel_states[callback.from_user.id] = "wait_share_link"
    await callback.message.delete()
    await client.send_message(
        callback.from_user.id,
        "**➕ Add Share Channel**\n\n"
        "1. Send the **Link** you want users to share.\n"
        "(e.g. `https://t.me/mychannel`)"
    )

@Client.on_callback_query(filters.regex(r"^view_share\|"))
async def view_share_channel(client, callback):
    link = callback.data.split("|")[1]
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("🗑 Remove", callback_data=f"del_share|{link}")],
        [InlineKeyboardButton("🔙 Back", callback_data="admin_share_channels")]
    ])
    await callback.edit_message_text(f"**Share Channel**\n\nLink: `{link}`", reply_markup=markup)

@Client.on_callback_query(filters.regex(r"^del_share\|"))
async def delete_share_channel(client, callback):
    link = callback.data.split("|")[1]
    await db.remove_share_channel(link)
    await callback.answer("Removed!", show_alert=True)
    await show_share_channels(client, callback)

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

    markup.append([InlineKeyboardButton("🔙 Back", callback_data="admin_channels_menu")])

    await callback.edit_message_text("**📢 Storage Channels**\nClick to manage:", reply_markup=InlineKeyboardMarkup(markup))

# --- Force Subs ---

@Client.on_callback_query(filters.regex(r"^admin_force_subs$"))
async def show_force_subs(client, callback):
    # Split Global (MainDB) and Local (PrivateDB)
    main_fs = await db.channels_col_main.find({"approved": True, "type": "force_sub"}).to_list(length=100)
    local_fs = await db.channels_col_private.find({"approved": True, "type": "force_sub"}).to_list(length=100)

    markup = []

    # Global Section
    if main_fs:
        markup.append([InlineKeyboardButton("🌍 -- Global (Read-Only) --", callback_data="noop")])
        for ch in main_fs:
            # No edit action for global
            markup.append([
                InlineKeyboardButton(f"🔒 {ch.get('title')}", callback_data=f"view_global_fs|{ch.get('chat_id')}")
            ])

    # Local Section
    if local_fs:
        markup.append([InlineKeyboardButton("🏠 -- Local (Manage) --", callback_data="noop")])
        for ch in local_fs:
            markup.append([
                InlineKeyboardButton(f"{ch.get('title')}", callback_data=f"view_ch|{ch.get('chat_id')}")
            ])

    if not main_fs and not local_fs:
        markup.append([InlineKeyboardButton("No FS channels.", callback_data="noop")])

    markup.append([InlineKeyboardButton("➕ Add Local Channel", callback_data="panel_add_fs_manual")])
    markup.append([InlineKeyboardButton("🔙 Back", callback_data="admin_channels_menu")])

    await callback.edit_message_text("**🔒 Force Sub Channels**\nClick to manage:", reply_markup=InlineKeyboardMarkup(markup))

@Client.on_callback_query(filters.regex(r"^view_global_fs\|"))
async def view_global_fs(client, callback):
    chat_id = callback.data.split("|")[1]
    await callback.answer("Read-only – managed by CEO.", show_alert=True)

# --- Franchise Channels ---

@Client.on_callback_query(filters.regex(r"^admin_franchise_channels$"))
async def show_franchise_channels(client, callback):
    channels = await db.get_franchise_channels()

    markup = []
    if channels:
        for ch in channels:
            markup.append([
                InlineKeyboardButton(f"{ch.get('title')} ({ch.get('chat_id')})", callback_data=f"view_ch|{ch.get('chat_id')}")
            ])
    else:
        markup.append([InlineKeyboardButton("No Franchise channels.", callback_data="noop")])

    markup.append([InlineKeyboardButton("➕ Add Franchise Channel", callback_data="panel_add_franchise_manual")])
    markup.append([InlineKeyboardButton("🔙 Back", callback_data="admin_channels_menu")])

    await callback.edit_message_text("**🏢 Franchise Channels**\nGlobal mandatory channels:\nClick to manage:", reply_markup=InlineKeyboardMarkup(markup))

@Client.on_callback_query(filters.regex(r"^panel_add_franchise_manual$"))
async def panel_add_franchise_manual(client, callback):
    panel_states[callback.from_user.id] = "wait_franchise_input"
    await callback.message.delete()
    await client.send_message(
        callback.from_user.id,
        "**➕ Add Franchise Channel**\n\n"
        "Please add the bot as Admin to the channel first!\n\n"
        "Then send the **Channel ID** or **Username**.\n"
        "Or forward a message from it."
    )

@Client.on_callback_query(filters.regex(r"^view_ch\|"))
async def view_channel(client, callback):
    chat_id = int(callback.data.split("|")[1])
    # Need to fetch details? We have ID.
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("🗑 Remove Channel", callback_data=f"del_ch|{chat_id}")],
        [InlineKeyboardButton("🔙 Back", callback_data="admin_channels_menu")]
    ])
    await callback.edit_message_text(f"**Channel Details**\nID: `{chat_id}`", reply_markup=markup)

@Client.on_callback_query(filters.regex(r"^del_ch\|"))
async def delete_channel(client, callback):
    chat_id = int(callback.data.split("|")[1])
    await db.remove_channel(chat_id)
    await callback.answer("Channel removed!", show_alert=True)
    # Go back to main menu is safest as we don't know if it was FS or Storage easily here without querying
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
        [InlineKeyboardButton("📡 Request Push", callback_data=f"req_push|{code}")],
        [InlineKeyboardButton("🗑 Delete", callback_data=f"del_bund_confirm|{code}")],
        [InlineKeyboardButton("🔙 Back", callback_data="panel_manage_bundles")]
    ])
    await callback.edit_message_text(text, reply_markup=markup)

@Client.on_callback_query(filters.regex(r"^req_push\|"))
async def request_push_bundle(client, callback):
    code = callback.data.split("|")[1]
    bundle = await db.get_bundle(code)
    if not bundle:
        await callback.answer("Bundle not found.", show_alert=True)
        return

    if not Config.CEO_CHANNEL_ID:
        await callback.answer("CEO Channel not configured.", show_alert=True)
        return

    try:
        title = bundle.get("title", "Untitled")
        tmdb_id = bundle.get("tmdb_id", "N/A")
        file_count = len(bundle.get("file_ids", []))
        user = callback.from_user

        text = (
            "🚀 **New Push Request**\n\n"
            f"📦 **Bundle:** {title}\n"
            f"🔑 **Code:** `{code}`\n"
            f"🎬 **TMDb:** `{tmdb_id}`\n"
            f"📂 **Files:** `{file_count}`\n\n"
            f"👤 **From:** {user.first_name} (`{user.id}`)"
        )

        await client.send_message(Config.CEO_CHANNEL_ID, text)
        await db.add_log("push_request", user.id, f"Requested push for {code}")
        await callback.answer("✅ Push Request Sent!", show_alert=True)
    except Exception as e:
        logger.error(f"Push Request Error: {e}")
        await callback.answer("❌ Failed to send request.", show_alert=True)

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
        if len(text) > 3500: break

    try:
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_tasks")]])
        await callback.edit_message_text(text, reply_markup=markup)
    except:
        await callback.message.delete()
        await client.send_message(callback.from_user.id, text)
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

# --- Input Handlers ---

@Client.on_message(filters.user(list(Config.ADMIN_IDS)) & filters.text & ~filters.command(["admin", "cancel", "start", "create_link"]), group=1)
async def handle_panel_input(client, message):
    user_id = message.from_user.id
    if user_id not in panel_states:
        raise ContinuePropagation

    raw_state = panel_states[user_id]
    state_key = raw_state if isinstance(raw_state, str) else raw_state.get("state")

    # New Handlers
    if state_key == "wait_autodel_input":
        try:
            val = int(message.text.strip())
            await db.update_config("auto_delete_time", val)
            await db.add_log("config_update", user_id, f"Auto-Delete set to {val}")
            await message.reply(f"✅ Auto-Delete set to {val} mins.")
        except:
            await message.reply("❌ Invalid number.")
        del panel_states[user_id]
        await show_main_menu(message)
        return

    # Coupon Steps
    if state_key == "wait_coupon_code":
        code = message.text.strip().upper()
        panel_states[user_id] = {"state": "wait_coupon_reward", "code": code}
        await message.reply(f"Code: `{code}`\n\n**Reward Hours?** (e.g. 24)")
        return

    if state_key == "wait_coupon_reward":
        try:
            hours = int(message.text)
            code = raw_state["code"]
            panel_states[user_id] = {"state": "wait_coupon_limit", "code": code, "reward": hours}
            await message.reply(f"Reward: {hours}h.\n\n**Usage Limit?** (e.g. 100)")
        except:
            await message.reply("❌ Number needed.")
        return

    if state_key == "wait_coupon_limit":
        try:
            limit = int(message.text)
            code = raw_state["code"]
            reward = raw_state["reward"]

            await db.create_coupon(code, reward, limit)
            await db.add_log("create_coupon", user_id, f"Created {code}")
            await message.reply(f"✅ Coupon Created!\n`{code}` -> {reward}h (Max {limit})")
            del panel_states[user_id]
            await show_main_menu(message)
        except:
            await message.reply("❌ Number needed.")
        return

    if state_key == "wait_coupon_del":
        code = message.text.strip().upper()
        await db.delete_coupon(code)
        await db.add_log("delete_coupon", user_id, f"Deleted {code}")
        await message.reply(f"✅ Coupon `{code}` deleted (if it existed).")
        del panel_states[user_id]
        await show_main_menu(message)
        return

    if state_key == "wait_daily_reward":
        try:
            val = int(message.text)
            await db.update_config("daily_bonus_reward", val)
            await db.add_log("config_update", user_id, f"Daily Reward set to {val}")
            await message.reply(f"✅ Daily Reward set to {val} hours.")
        except:
            await message.reply("❌ Number.")
        del panel_states[user_id]
        await show_main_menu(message)
        return

    if state_key == "wait_prem_add_id":
        try:
            target_id = int(message.text.strip())
            panel_states[user_id] = {"state": "wait_prem_duration", "target_id": target_id}
            await message.reply("**⏳ Duration**\n\nEnter days (e.g. 30):")
        except:
             await message.reply("❌ Invalid ID.")
        return

    if state_key == "wait_prem_duration":
        try:
            days = float(message.text.strip())
            target_id = raw_state["target_id"]
            await db.add_premium_user(target_id, days)
            await db.add_log("add_premium", user_id, f"Added Premium to {target_id} ({days}d)")
            await message.reply(f"✅ User {target_id} is now Premium for {days} days.")
        except:
            await message.reply("❌ Invalid number.")
        del panel_states[user_id]
        await show_main_menu(message)
        return

    if state_key == "wait_prem_rem_id":
        try:
            target_id = int(message.text.strip())
            await db.remove_premium_user(target_id)
            await db.add_log("remove_premium", user_id, f"Removed Premium from {target_id}")
            await message.reply(f"✅ User {target_id} removed from Premium.")
        except:
            await message.reply("❌ Invalid ID.")
        del panel_states[user_id]
        await show_main_menu(message)
        return

    if state_key == "wait_ref_target":
        try:
            val = int(message.text.strip())
            await db.update_config("referral_target", val)
            await message.reply(f"✅ Target set to {val}.")
        except:
             await message.reply("❌ Invalid.")
        del panel_states[user_id]
        await show_main_menu(message)
        return

    if state_key == "wait_ref_reward":
        try:
            val = int(message.text.strip())
            await db.update_config("referral_reward_hours", val)
            await message.reply(f"✅ Reward set to {val} hours.")
        except:
             await message.reply("❌ Invalid.")
        del panel_states[user_id]
        await show_main_menu(message)
        return

    # Existing Handlers
    if state_key == "wait_bundle_rename":
        code = raw_state["code"]
        new_title = message.text
        await db.update_bundle_title(code, new_title)
        await db.add_log("rename_bundle", user_id, f"Renamed {code} to {new_title}")
        await message.reply(f"✅ Bundle renamed to: `{new_title}`")
        del panel_states[user_id]
        await show_main_menu(message)
        return

    if state_key == "wait_share_link":
        link = message.text.strip()
        if not link.startswith("http") and not link.startswith("t.me"):
             await message.reply("⚠️ Warning: Link should start with http or t.me. Proceeding anyway.")
        panel_states[user_id] = {"state": "wait_share_text_final", "link": link}
        await message.reply(
            "✅ Link saved.\n\n"
            "**Now send the Text message** that accompanies the link:\n"
            "👉 Use `{channel_link}` as a placeholder for the link.\n\n"
            "Example: `Hey, check this out: {channel_link}`"
        )
        return

    if state_key == "wait_share_text_final":
        text = message.text
        link = raw_state["link"]
        await db.add_share_channel(link, text)
        await message.reply(f"✅ **Share Channel Added!**\n\nLink: `{link}`\nText: `{text}`")
        del panel_states[user_id]
        await show_main_menu(message)
        return

    if state_key == "wait_fs_input":
        text = message.text
        chat_id = None
        if text.lstrip("-").isdigit():
            chat_id = int(text)
        elif text.startswith("@"):
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

    elif state_key == "wait_franchise_input":
        text = message.text
        chat_id = None
        if text.lstrip("-").isdigit():
            chat_id = int(text)
        elif text.startswith("@"):
            try:
                chat = await client.get_chat(text)
                chat_id = chat.id
            except Exception:
                await message.reply("❌ Could not resolve username.")
                return
        elif message.forward_from_chat:
             chat_id = message.forward_from_chat.id
        else:
             await message.reply("❌ Invalid input.")
             return

        try:
            chat = await client.get_chat(chat_id)
            invite = None
            try:
                invite_obj = await client.create_chat_invite_link(chat_id, name="Fileshare Bot Franchise")
                invite = invite_obj.invite_link
            except:
                invite = chat.invite_link

            # Add with force_sub type AND is_franchise=True
            await db.add_channel(chat_id, chat.title, chat.username, "force_sub", invite)
            await db.set_channel_franchise_status(chat_id, True)

            await message.reply(f"✅ Added **{chat.title}** as Franchise Channel.")
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
        lines = text.split("\n")
        added = 0
        failed = 0
        for line in lines:
            line = line.strip()
            if not line: continue
            parts = [p.strip() for p in line.split("|")]
            if len(parts) < 2:
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

@Client.on_message(filters.command("cancel") & filters.user(list(Config.ADMIN_IDS)), group=1)
async def cancel_panel(client, message):
    user_id = message.from_user.id
    if user_id in panel_states:
        del panel_states[user_id]
        await message.reply("❌ Panel action cancelled.")
    else:
        raise ContinuePropagation
