# Flower shop order bot → Google Sheets

Telegram bot for a small shop (demo: flower shop «Півонія»). Customers order in Telegram, orders land in a **Google Sheet**, the owner changes the status in the sheet — and the customer sees it in the bot.

Telegram-бот для невеликого магазину: замовлення в Telegram → Google Таблиця → власник змінює статус у таблиці → клієнт бачить його в боті.

## Features
- **Catalog from the sheet**: the owner edits products, prices and "in stock" right in Google Sheets — no admin panel needed.
- Cart with quantities, checkout step by step: name, phone (contact button), pickup or delivery, address, date, comment, summary.
- Delivery cost rule (free from a set amount).
- New order → row in sheet «Замовлення» + instant notification to the owner.
- Owner changes the status in the sheet (Нове → Підтверджено → Доставляється → Виконано); the customer sees current statuses via the «📦 Мої замовлення» button.
- Google side is a tiny Apps Script web app protected by a secret key; no Google service accounts.

## Stack
Python 3, aiogram 3 (FSM), aiohttp, Google Apps Script, systemd.

## Setup
1. Create a bot in [@BotFather](https://t.me/BotFather).
2. Google Sheets → Extensions → Apps Script → paste `apps_script/Code.gs` → run `setup()` (creates sheets + sample catalog, prints `SHEET_SECRET`) → Deploy as Web app (Execute as: Me, Access: Anyone).
3. `cp .env.example .env` and fill `BOT_TOKEN`, `SHEET_URL`, `SHEET_SECRET`; send `/myid` to the bot and put it into `ADMIN_ID`.
4. Run:
   ```bash
   python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
   .venv/bin/python bot.py
   ```
   or as a service: `deploy/orders-bot.service` (systemd user unit).
