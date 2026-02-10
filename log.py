import logging
import os
import sys
from logging.handlers import RotatingFileHandler

# Create logs directory if it doesn't exist
if not os.path.exists("logs"):
    os.makedirs("logs")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        RotatingFileHandler("logs/bot.log", maxBytes=5000000, backupCount=5),
        logging.StreamHandler(sys.stdout)
    ]
)

# Suppress pyrogram info logs that are too verbose
logging.getLogger("pyrogram").setLevel(logging.WARNING)

def get_logger(name: str):
    return logging.getLogger(name)
