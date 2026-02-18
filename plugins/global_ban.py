from pyrogram import Client, StopPropagation
from pyrogram.types import Message, CallbackQuery
from db import db
from log import get_logger

logger = get_logger(__name__)

@Client.on_message(group=-1)
async def check_global_ban_message(client: Client, message: Message):
    """
    High-priority handler to check if a user is globally banned.
    If banned, stop propagation immediately.
    """
    user_id = message.from_user.id if message.from_user else None
    if not user_id:
        return

    is_banned = await db.is_user_banned(user_id)
    logger.info(f"Global ban check: user {user_id} → banned: {is_banned}")

    if is_banned:
        raise StopPropagation

@Client.on_callback_query(group=-1)
async def check_global_ban_callback(client: Client, callback_query: CallbackQuery):
    """
    High-priority handler to check if a user is globally banned via callback.
    If banned, stop propagation immediately.
    """
    user_id = callback_query.from_user.id if callback_query.from_user else None
    if not user_id:
        return

    is_banned = await db.is_user_banned(user_id)
    logger.info(f"Global ban check: user {user_id} → banned: {is_banned}")

    if is_banned:
        raise StopPropagation
