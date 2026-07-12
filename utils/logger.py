# utils/logger.py
import os
import logging
from logging.handlers import RotatingFileHandler
import requests

class TelegramHandler(logging.Handler):
    """Handler khusus untuk mengirim log ERROR ke Telegram."""
    def __init__(self, bot_token: str, chat_id: str):
        super().__init__()
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    def emit(self, record):
        log_entry = self.format(record)
        # Kirim jika levelnya WARNING atau lebih tinggi
        if record.levelno >= logging.WARNING:
            payload = {
                "chat_id": self.chat_id,
                "text": f"⚠️ **[DYADIX ALERT - {record.levelname}]**\n\n```\n{log_entry[:4000]}\n```",
                "parse_mode": "Markdown"
            }
            try:
                requests.post(self.api_url, json=payload, timeout=5)
            except Exception:
                pass  # Jangan biarkan error pengiriman Telegram merusak aplikasi utama

def setup_global_logger():
    log_dir = "data/logs"
    os.makedirs(log_dir, exist_ok=True)

    # Logger Utama
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # Bersihkan handler bawaan jika ada
    root_logger.handlers = []

    # 1. Format Log
    log_format = logging.Formatter(
        "%(asctime)s [%(levelname)s] [%(name)s:%(lineno)d] %(message)s"
    )

    # 2. Console Handler (Untuk pemantauan Terminal/PM2)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_format)
    console_handler.setLevel(logging.INFO)
    root_logger.addHandler(console_handler)

    # 3. Rotating File Handler (Untuk semua log info ke atas)
    # File berotasi jika ukurannya mencapai 10MB, dan menyimpan maksimal 5 backup file log lama.
    file_handler = RotatingFileHandler(
        filename=os.path.join(log_dir, "dyadix_info.log"),
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding="utf-8"
    )
    file_handler.setFormatter(log_format)
    file_handler.setLevel(logging.INFO)
    root_logger.addHandler(file_handler)

    # 4. Error File Handler (Khusus ERROR saja agar gampang dicari)
    error_file_handler = RotatingFileHandler(
        filename=os.path.join(log_dir, "dyadix_errors.log"),
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=3,
        encoding="utf-8"
    )
    error_file_handler.setFormatter(log_format)
    error_file_handler.setLevel(logging.WARNING)  # Menyaring WARNING & ERROR
    root_logger.addHandler(error_file_handler)

    # 5. Telegram Alert Handler (Mengambil token dari ENV)
    tg_token = os.getenv("TELEGRAM_BOT")
    tg_chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if tg_token and tg_chat_id:
        tg_handler = TelegramHandler(tg_token, tg_chat_id)
        tg_handler.setFormatter(log_format)
        tg_handler.setLevel(logging.WARNING)
        root_logger.addHandler(tg_handler)

    logging.info("🌟 Centralized Logging System Initialized Successfully!")
