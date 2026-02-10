import logging
import sys

# ANSI Colors for Railway
class Colors:
    RESET = "\033[0m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    BOLD = "\033[1m"
    CYAN = "\033[36m"

class ConsoleFormatter(logging.Formatter):
    """Formatierung für Railway Console mit Farben und Emojis"""

    FORMATS = {
        logging.DEBUG:    "🐞",
        logging.INFO:     "ℹ️ ",
        logging.WARNING:  "⚠️ ",
        logging.ERROR:    "❌ ",
        logging.CRITICAL: "🔥 "
    }

    COLOR_MAP = {
        logging.DEBUG:    Colors.CYAN,
        logging.INFO:     Colors.GREEN,
        logging.WARNING:  Colors.YELLOW,
        logging.ERROR:    Colors.RED + Colors.BOLD,
        logging.CRITICAL: Colors.RED + Colors.BOLD
    }

    def format(self, record):
        emoji = self.FORMATS.get(record.levelno, "")
        color = self.COLOR_MAP.get(record.levelno, Colors.RESET)

        # Format: [TIME] [EMOJI] LEVEL :: MESSAGE
        log_fmt = (
            f"{Colors.BLUE}[%(asctime)s]{Colors.RESET} "
            f"{color}{emoji}%(levelname)-8s{Colors.RESET} :: "
            f"{color}%(message)s{Colors.RESET}"
        )

        formatter = logging.Formatter(log_fmt, datefmt="%H:%M:%S")
        return formatter.format(record)

def get_logger(name):
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    # Console Handler
    if not logger.handlers:
        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(ConsoleFormatter())
        logger.addHandler(ch)

    # Suppress verbose loggers
    logging.getLogger("pyrogram").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    return logger
