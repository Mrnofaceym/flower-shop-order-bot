"""Bot settings. To adapt the bot for a new client, usually only this file and the sheet change."""
import os

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
_admin = os.getenv("ADMIN_ID", "").strip()
ADMIN_ID = int(_admin) if _admin.lstrip("-").isdigit() else None

# Google Apps Script web app (see apps_script/Code.gs)
SHEET_URL = os.getenv("SHEET_URL", "").strip()
SHEET_SECRET = os.getenv("SHEET_SECRET", "").strip()

SHOP_NAME = "Квіткова крамниця «Півонія»"
SHOP_INFO = (
    "🌷 <b>Квіткова крамниця «Півонія»</b>\n"
    "📍 вул. Квіткова, 7\n"
    "🕙 Щодня 09:00–20:00\n"
    "🚚 Доставка по місту — 150 грн, від 2000 грн — безкоштовно"
)

DELIVERY_PRICE = 150
FREE_DELIVERY_FROM = 2000
DAYS_AHEAD = 7            # how many days ahead a client can choose
CATALOG_CACHE_SECONDS = 60
STATUS_CHECK_SECONDS = 60  # how often the bot checks the sheet for status changes
