from datetime import date, timedelta

from aiogram.types import (InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton,
                           ReplyKeyboardMarkup, ReplyKeyboardRemove)

import config

BTN_CATALOG = "🛍 Каталог"
BTN_CART = "🧺 Кошик"
BTN_ORDERS = "📦 Мої замовлення"
BTN_INFO = "ℹ️ Про нас"
WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Нд"]

main_menu = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text=BTN_CATALOG), KeyboardButton(text=BTN_CART)],
              [KeyboardButton(text=BTN_ORDERS), KeyboardButton(text=BTN_INFO)]],
    resize_keyboard=True)

remove = ReplyKeyboardRemove()


def ib(text, data):
    return InlineKeyboardButton(text=text, callback_data=data)


def catalog_kb(items):
    rows = [[ib(f"{p['name']} — {p['price']:g} грн", f"item:{p['id']}")] for p in items]
    rows.append([ib("🧺 Перейти до кошика", "cart")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def item_kb(item_id, qty_in_cart):
    label = f"🧺 У кошику: {qty_in_cart}" if qty_in_cart else "🧺 Кошик"
    return InlineKeyboardMarkup(inline_keyboard=[
        [ib("➖", f"dec:{item_id}"), ib("➕ Додати", f"inc:{item_id}")],
        [ib("⬅️ До каталогу", "catalog"), ib(label, "cart")],
    ])


def cart_kb(has_items):
    rows = []
    if has_items:
        rows.append([ib("✅ Оформити замовлення", "checkout")])
        rows.append([ib("🗑 Очистити", "clear"), ib("🛍 Каталог", "catalog")])
    else:
        rows.append([ib("🛍 Відкрити каталог", "catalog")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


phone_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="📱 Надіслати мій номер", request_contact=True)],
              [KeyboardButton(text="❌ Скасувати")]],
    resize_keyboard=True, one_time_keyboard=True)

cancel_kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Скасувати")]], resize_keyboard=True)

delivery_kb = InlineKeyboardMarkup(inline_keyboard=[
    [ib("🚚 Доставка", "dlv:delivery"), ib("🏪 Самовивіз", "dlv:pickup")],
])


def dates_kb():
    today = date.today()
    btns = []
    for i in range(config.DAYS_AHEAD):
        d = today + timedelta(days=i)
        name = "Сьогодні" if i == 0 else "Завтра" if i == 1 else f"{WEEKDAYS[d.weekday()]} {d:%d.%m}"
        btns.append(ib(name, f"date:{d.isoformat()}"))
    return InlineKeyboardMarkup(inline_keyboard=[btns[i:i + 2] for i in range(0, len(btns), 2)])


skip_kb = InlineKeyboardMarkup(inline_keyboard=[[ib("Без коментаря ➡️", "skip_comment")]])

confirm_kb = InlineKeyboardMarkup(inline_keyboard=[
    [ib("✅ Підтвердити", "confirm")],
    [ib("✏️ Змінити кошик", "cart"), ib("❌ Скасувати", "cancel")],
])
