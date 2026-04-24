#config.py
import os
from dotenv import load_dotenv

load_dotenv()

PASSWORD = os.getenv("BOT_PASSWORD")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_TELEGRAM_ID = int(os.getenv("ADMIN_TELEGRAM_ID", "0"))

GIGACHAT_AUTH_KEY = os.getenv("GIGACHAT_AUTH_KEY")
GIGACHAT_AUTH_URL = os.getenv("GIGACHAT_AUTH_URL")
GIGACHAT_API_URL = os.getenv("GIGACHAT_API_URL")

SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
EMAIL_LOGIN = os.getenv("EMAIL_LOGIN")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")

MAX_ACTIVE_TASKS = int(os.getenv("MAX_ACTIVE_TASKS", "25"))

DB_FILE = os.getenv("DB_FILE", "tasks.db")
LOG_FILE = os.getenv("LOG_FILE", "logs/bot.log")