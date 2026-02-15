from pyrogram import Client, filters
from pyrogram.types import Message
from config import Config
from db import db

# --- Config Management ---

@Client.on_message(filters.command("config") & filters.user(Config.ADMIN_ID))
async def show_config(client: Client, message: Message):
    force_sub = await db.get_config("force_sub_enabled", False)
    tasks_enabled = await db.get_config("tasks_enabled", False)
    fs_channels = await db.get_config("force_sub_channels", [])

    text = (
        "**⚙️ Current Configuration**\n\n"
        f"🔹 **Force Sub Enabled:** `{force_sub}`\n"
        f"🔹 **Tasks Enabled:** `{tasks_enabled}`\n"
        f"🔹 **Force Sub Channels:** `{', '.join(map(str, fs_channels))}`\n"
    )
    await message.reply(text)

@Client.on_message(filters.command("toggle_force_sub") & filters.user(Config.ADMIN_ID))
async def toggle_force_sub(client, message):
    current = await db.get_config("force_sub_enabled", False)
    new_val = not current
    await db.update_config("force_sub_enabled", new_val)
    await message.reply(f"Force Sub set to: `{new_val}`")

@Client.on_message(filters.command("toggle_task") & filters.user(Config.ADMIN_ID))
async def toggle_task(client, message):
    current = await db.get_config("tasks_enabled", False)
    new_val = not current
    await db.update_config("tasks_enabled", new_val)
    await message.reply(f"Tasks set to: `{new_val}`")

@Client.on_message(filters.command("set_force_sub") & filters.user(Config.ADMIN_ID))
async def set_force_sub(client, message):
    # Usage: /set_force_sub @channel1 -100123456
    args = message.command[1:]
    if not args:
        await message.reply("Usage: `/set_force_sub @channel1 id2 ...`")
        return

    # Clean up args (remove empty strings)
    channels = [x for x in args if x]
    await db.update_config("force_sub_channels", channels)
    await message.reply(f"Force Sub channels updated: {channels}")

# --- Task Management ---

@Client.on_message(filters.command("add_task") & filters.user(Config.ADMIN_ID))
async def add_new_task(client, message):
    # Usage: /add_task Question | Answer | Opt1, Opt2
    text = message.text.split(maxsplit=1)
    if len(text) < 2:
        await message.reply("Usage: `/add_task Question | Answer | Opt1, Opt2` (Options are optional)")
        return

    content = text[1]
    parts = [p.strip() for p in content.split("|")]

    if len(parts) < 2:
        await message.reply("Format error. Must have at least Question and Answer separated by `|`.")
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
    await message.reply(f"✅ Task Added!\n\nQ: {question}\nA: {answer}\nType: {task_type}")

@Client.on_message(filters.command("list_tasks") & filters.user(Config.ADMIN_ID))
async def list_tasks(client, message):
    tasks = await db.get_all_tasks()
    if not tasks:
        await message.reply("No tasks found.")
        return

    text = "**📝 Tasks List:**\n\n"
    for t in tasks:
        opts = f" (Options: {', '.join(t.get('options', []))})" if t.get('options') else ""
        text += f"🔹 Q: {t['question']}\n   A: {t['answer']}{opts}\n\n"
        if len(text) > 3500: # Split if too long
            await message.reply(text)
            text = ""

    if text:
        await message.reply(text)

@Client.on_message(filters.command("stats") & filters.user(Config.ADMIN_ID))
async def stats(client, message):
    bundles = await db.get_all_bundles()
    total_views = sum(b.get("views", 0) for b in bundles)
    popular = sorted(bundles, key=lambda x: x.get("views", 0), reverse=True)[:5]

    pop_text = ""
    for p in popular:
        pop_text += f"- {p.get('title')} ({p.get('views', 0)} views)\n"

    await message.reply(
        f"**📊 Statistics**\n\n"
        f"Total Bundles: {len(bundles)}\n"
        f"Total Requests: {total_views}\n\n"
        f"**🔥 Popular Bundles:**\n{pop_text}"
    )
