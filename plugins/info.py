import os
import time
import datetime
import platform
import subprocess
import asyncio
import psutil
import pyrogram
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from config import Config

# Helper Functions
def format_uptime(seconds: float) -> str:
    if seconds is None:
        return "Unknown"
    dt = datetime.timedelta(seconds=int(seconds))
    days = dt.days
    hours, remainder = divmod(dt.seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    return f"{days}d {hours}h {minutes}m"

def get_readable_size(size: int) -> str:
    power = 2**10
    n = 0
    power_labels = {0: 'B', 1: 'KB', 2: 'MB', 3: 'GB', 4: 'TB'}
    while size >= power:
        size /= power
        n += 1
    return f"{size:.2f} {power_labels[n]}"

def get_git_commit() -> str:
    # Try Environment Variable (Railway)
    commit = os.getenv("RAILWAY_GIT_COMMIT_SHA")
    if commit:
        return commit[:7]

    # Try Git Command
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"]).decode("ascii").strip()
    except Exception:
        return "Unknown"

async def get_system_stats(client):
    # Developer Info
    try:
        # Try to fetch user info
        user = await client.get_users("davdxpx")
        dev_name = user.first_name
        if user.last_name:
            dev_name += f" {user.last_name}"
        # Use HTML link for user
        dev_link = f"tg://user?id={user.id}"
    except Exception:
        # Fallback
        dev_name = "𝕏0L0™"
        dev_link = "https://t.me/davdxpx"

    # System Stats (Wrap in try/except for robustness)
    try:
        # Run blocking psutil calls in a thread
        cpu_percent = await asyncio.to_thread(psutil.cpu_percent, interval=0.5)
        mem = await asyncio.to_thread(psutil.virtual_memory)
        ram_used = get_readable_size(mem.used)
        ram_total = get_readable_size(mem.total)
    except Exception:
        cpu_percent = "N/A"
        ram_used = "N/A"
        ram_total = "N/A"

    # Tech Stack
    python_ver = platform.python_version()
    pyro_ver = pyrogram.__version__

    # Git
    git_hash = get_git_commit()

    # Uptime
    if Config.START_TIME:
        uptime_seconds = time.time() - Config.START_TIME
    else:
        uptime_seconds = 0
    uptime_str = format_uptime(uptime_seconds)

    # Date
    now_utc = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    return {
        "dev_name": dev_name,
        "dev_link": dev_link,
        "cpu": cpu_percent,
        "ram_used": ram_used,
        "ram_total": ram_total,
        "python_ver": python_ver,
        "pyro_ver": pyro_ver,
        "git_hash": git_hash,
        "uptime": uptime_str,
        "date": now_utc
    }

def build_info_text(stats, ping_ms):
    return (
        "🤖 <b>Bot Status Panel</b>\n"
        f"👤 Developer: <a href='{stats['dev_link']}'>{stats['dev_name']}</a>\n"
        "🟢 Status: Online\n"
        f"⏳ Uptime: {stats['uptime']}\n\n"
        "💻 <b>System</b>\n"
        "├ OS: Linux (Railway)\n"
        f"├ CPU: {stats['cpu']}%\n"
        f"└ RAM: {stats['ram_used']} / {stats['ram_total']}\n\n"
        "🛠 <b>Tech Stack</b>\n"
        f"├ Python: v{stats['python_ver']}\n"
        f"└ Pyrogram: v{stats['pyro_ver']}\n\n"
        "📡 <b>Connection</b>\n"
        f"├ Ping: {int(ping_ms)}ms\n"
        f"└ Version: {stats['git_hash']}\n\n"
        f"📅 {stats['date']}"
    )

@Client.on_message(filters.command("info"))
async def info_handler(client, message):
    # Calculate Ping (Time since message received)
    start_time = time.time()

    stats = await get_system_stats(client)

    # Use message timestamp if available, otherwise processing time
    if message.date:
        ping_ms = (time.time() - message.date.timestamp()) * 1000
    else:
        ping_ms = (time.time() - start_time) * 1000

    if ping_ms < 0:
        ping_ms = 0

    text = build_info_text(stats, ping_ms)

    markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔄 Refresh", callback_data="info_refresh"),
            InlineKeyboardButton("❌ Close", callback_data="info_close")
        ]
    ])

    await message.reply_text(text, reply_markup=markup, parse_mode=pyrogram.enums.ParseMode.HTML)

@Client.on_callback_query(filters.regex("^info_refresh$"))
async def info_refresh_handler(client, callback: CallbackQuery):
    start_time = time.time()

    stats = await get_system_stats(client)

    # For refresh, use processing time as ping
    end_time = time.time()
    ping_ms = (end_time - start_time) * 1000
    if ping_ms < 1:
        ping_ms = 1

    text = build_info_text(stats, ping_ms)

    try:
        await callback.message.edit_text(text, reply_markup=callback.message.reply_markup, parse_mode=pyrogram.enums.ParseMode.HTML)
        await callback.answer("Refreshed!")
    except Exception:
        # If text didn't change (e.g. extremely fast refresh), ignore error
        await callback.answer("Already updated!", show_alert=False)

@Client.on_callback_query(filters.regex("^info_close$"))
async def info_close_handler(client, callback: CallbackQuery):
    try:
        await callback.message.delete()
    except Exception:
        pass
