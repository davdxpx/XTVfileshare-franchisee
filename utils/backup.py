import os
import shutil
import asyncio
import time
from datetime import datetime
from config import Config
from db import db
from log import get_logger

logger = get_logger(__name__)

async def run_backup(client):
    """
    Dumps MongoDB, zips it, and sends to CEO/Backup Channel.
    """
    logger.info("Starting Database Backup...")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = f"backup_{timestamp}"
    zip_filename = f"backup_{timestamp}.zip"

    # Construct mongodump command
    # Mask password for logging if needed, but here we construct cmd string
    # Use MAIN_URI as per 3-DB architecture (MONGO_URI deprecated/fallback)
    uri = Config.MAIN_URI

    # Using shell execution
    cmd = f"mongodump --uri=\"{uri}\" --out=\"{backup_dir}\" --gzip"

    try:
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            err_msg = stderr.decode()
            logger.error(f"Mongodump failed: {err_msg}")
            if Config.CEO_ID:
                try:
                    await client.send_message(Config.CEO_ID, f"❌ **Backup Failed!**\n\nError: `{err_msg[:500]}`")
                except: pass
            return False

        # Zip it
        shutil.make_archive(backup_dir, 'zip', backup_dir)
        final_zip = f"{backup_dir}.zip"

        caption = (
            f"🗄 **Database Backup**\n"
            f"📅 {timestamp}\n"
            f"🤖 Bot: {Config.BOT_USERNAME}"
        )

        # Send to CEO
        if Config.CEO_ID:
            try:
                await client.send_document(Config.CEO_ID, document=final_zip, caption=caption)
            except Exception as e:
                logger.error(f"Failed to send backup to CEO: {e}")

        # Send to Channel
        if Config.BACKUP_CHANNEL_ID:
            try:
                await client.send_document(Config.BACKUP_CHANNEL_ID, document=final_zip, caption=caption)
            except Exception as e:
                logger.error(f"Failed to send backup to Channel: {e}")

        logger.info("Backup completed and sent.")

        # Cleanup
        if os.path.exists(backup_dir):
            shutil.rmtree(backup_dir)
        if os.path.exists(final_zip):
            os.remove(final_zip)

        return True

    except Exception as e:
        logger.error(f"Backup Exception: {e}")
        if Config.CEO_ID:
            try:
                await client.send_message(Config.CEO_ID, f"❌ **Backup Exception!**\n\nError: `{e}`")
            except: pass
        return False
