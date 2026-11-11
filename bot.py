"""Telegram bot that takes orders and writes them to a Google Sheet.

Catalog lives in the sheet too: the owner edits prices/stock there and the bot picks it up.
"""
import asyncio
import html
import logging
import re
from datetime import date

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

import config
import keyboards as kb
import sheets

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
dp = Dispatcher()
carts: dict[int, dict[str, int]] = {}      # user_id -> {item_id: qty}; in memory is enough for a shop bot
SORRY = "😔 Не вдалося зв'язатися з магазином. Спробуйте, будь ласка, за хвилину."


class Checkout(StatesGroup):
    name = State()
    phone = State()
    delivery = State()
    address = State()
    date = State()
    comment = State()
    confirm = State()


def esc(s):
    return html.escape(str(s))


async def find_item(item_id):
    return next((p for p in await sheets.catalog() if p["id"] == item_id), None)


async def cart_lines(user_id):
    """[(item, qty)], total — skips items that disappeared from the catalog."""
    items = {p["id"]: p for p in await sheets.catalog()}
    cart = carts.get(user_id, {})
    for gone in [i for i in cart if i not in items]:
        cart.pop(gone)
    lines = [(items[i], q) for i, q in cart.items() if q > 0]
    return lines, sum(p["price"] * q for p, q in lines)


def delivery_cost(total, delivery):
    if delivery != "delivery":
        return 0
    return 0 if total >= config.FREE_DELIVERY_FROM else config.DELIVERY_PRICE


# ---------- menu ----------
@dp.message(CommandStart())
async def start(m: Message, state: FSMContext):
    await state.clear()
    await m.answer(f"Вітаємо в {esc(config.SHOP_NAME)}! 🌸\n"
                   "Оберіть букет у каталозі, додайте в кошик і оформіть замовлення — "
                   "ми зателефонуємо для підтвердження.", reply_markup=kb.main_menu)


@dp.message(Command("myid"))
async def myid(m: Message):
    await m.answer(f"Ваш Telegram ID: <code>{m.from_user.id}</code>")


@dp.message(F.text == kb.BTN_INFO)
async def info(m: Message):
    await m.answer(config.SHOP_INFO)


@dp.message(F.text == kb.BTN_CATALOG)
@dp.message(Command("catalog"))
async def catalog_msg(m: Message):
    try:
        items = await sheets.catalog()
    except Exception:
        logging.exception("catalog")
        return await m.answer(SORRY)
    await m.answer("🛍 <b>Каталог</b>\nОберіть позицію:", reply_markup=kb.catalog_kb(items))


@dp.callback_query(F.data == "catalog")
async def catalog_cb(c: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        items = await sheets.catalog()
    except Exception:
        logging.exception("catalog")
        return await c.answer(SORRY, show_alert=True)
    await c.message.edit_text("🛍 <b>Каталог</b>\nОберіть позицію:", reply_markup=kb.catalog_kb(items))
    await c.answer()


async def show_item(c: CallbackQuery, item_id):
    p = await find_item(item_id)
    if not p:
        return await c.answer("Цієї позиції вже немає в наявності", show_alert=True)
    qty = carts.get(c.from_user.id, {}).get(item_id, 0)
    text = f"<b>{esc(p['name'])}</b>\n{esc(p['description'])}\n\n💰 {p['price']:g} грн"
    await c.message.edit_text(text, reply_markup=kb.item_kb(item_id, qty))


@dp.callback_query(F.data.startswith("item:"))
async def item_cb(c: CallbackQuery):
    await show_item(c, c.data.split(":", 1)[1])
    await c.answer()


@dp.callback_query(F.data.startswith(("inc:", "dec:")))
async def qty_cb(c: CallbackQuery):
    op, item_id = c.data.split(":", 1)
    cart = carts.setdefault(c.from_user.id, {})
    cart[item_id] = max(0, cart.get(item_id, 0) + (1 if op == "inc" else -1))
    if not cart[item_id]:
        cart.pop(item_id)
    await show_item(c, item_id)
    await c.answer("Додано в кошик ✅" if op == "inc" else "Прибрано")


# ---------- cart ----------
async def cart_text(user_id):
    lines, total = await cart_lines(user_id)
    if not lines:
        return "🧺 Кошик порожній.", False
    rows = [f"• {esc(p['name'])} × {q} = {p['price'] * q:g} грн" for p, q in lines]
    note = (f"\n🚚 Доставка безкоштовна від {config.FREE_DELIVERY_FROM} грн"
            if total < config.FREE_DELIVERY_FROM else "\n🚚 Доставка — безкоштовно")
    return "🧺 <b>Ваш кошик</b>\n" + "\n".join(rows) + f"\n\n<b>Разом: {total:g} грн</b>{note}", True


@dp.message(F.text == kb.BTN_CART)
async def cart_msg(m: Message):
    try:
        text, has = await cart_text(m.from_user.id)
    except Exception:
        logging.exception("cart")
        return await m.answer(SORRY)
    await m.answer(text, reply_markup=kb.cart_kb(has))


@dp.callback_query(F.data == "cart")
async def cart_cb(c: CallbackQuery, state: FSMContext):
    await state.clear()
    text, has = await cart_text(c.from_user.id)
    await c.message.edit_text(text, reply_markup=kb.cart_kb(has))
    await c.answer()


@dp.callback_query(F.data == "clear")
async def clear_cb(c: CallbackQuery):
    carts.pop(c.from_user.id, None)
    await c.message.edit_text("🧺 Кошик очищено.", reply_markup=kb.cart_kb(False))
    await c.answer()


# ---------- checkout ----------
@dp.callback_query(F.data == "checkout")
async def checkout(c: CallbackQuery, state: FSMContext):
    lines, _ = await cart_lines(c.from_user.id)
    if not lines:
        return await c.answer("Кошик порожній", show_alert=True)
    await state.set_state(Checkout.name)
    await c.message.answer("Як до вас звертатися? Напишіть ім'я:", reply_markup=kb.cancel_kb)
    await c.answer()


@dp.message(F.text == "❌ Скасувати")
@dp.callback_query(F.data == "cancel")
async def cancel(event, state: FSMContext):
    await state.clear()
    msg = event.message if isinstance(event, CallbackQuery) else event
    await msg.answer("Оформлення скасовано. Кошик збережено 🧺", reply_markup=kb.main_menu)
    if isinstance(event, CallbackQuery):
        await event.answer()


@dp.message(Checkout.name, F.text)
async def got_name(m: Message, state: FSMContext):
    name = m.text.strip()[:60]
    if len(name) < 2:
        return await m.answer("Напишіть, будь ласка, ім'я (хоча б 2 літери).")
    await state.update_data(name=name)
    await state.set_state(Checkout.phone)
    await m.answer("Залиште номер телефону — натисніть кнопку або напишіть його:", reply_markup=kb.phone_kb)


@dp.message(Checkout.phone, F.contact)
@dp.message(Checkout.phone, F.text)
async def got_phone(m: Message, state: FSMContext):
    phone = m.contact.phone_number if m.contact else m.text
    digits = re.sub(r"\D", "", phone)
    if not 9 <= len(digits) <= 13:
        return await m.answer("Схоже, номер неповний. Приклад: 0671234567")
    await state.update_data(phone="+" + digits if len(digits) > 10 else digits)
    await state.set_state(Checkout.delivery)
    await m.answer("Як бажаєте отримати замовлення?", reply_markup=kb.remove)
    await m.answer("Оберіть варіант:", reply_markup=kb.delivery_kb)


@dp.callback_query(Checkout.delivery, F.data.startswith("dlv:"))
async def got_delivery(c: CallbackQuery, state: FSMContext):
    delivery = c.data.split(":", 1)[1]
    await state.update_data(delivery=delivery)
    if delivery == "delivery":
        await state.set_state(Checkout.address)
        await c.message.edit_text("🚚 Напишіть адресу доставки (вулиця, будинок, квартира):")
    else:
        await state.update_data(address="")
        await state.set_state(Checkout.date)
        await c.message.edit_text("🏪 Самовивіз: " + config.SHOP_INFO.split("\n")[1] +
                                  "\n\nНа який день готувати замовлення?", reply_markup=kb.dates_kb())
    await c.answer()


@dp.message(Checkout.address, F.text)
async def got_address(m: Message, state: FSMContext):
    if len(m.text.strip()) < 5:
        return await m.answer("Напишіть, будь ласка, повну адресу.")
    await state.update_data(address=m.text.strip()[:200])
    await state.set_state(Checkout.date)
    await m.answer("На який день доставити?", reply_markup=kb.dates_kb())


@dp.callback_query(Checkout.date, F.data.startswith("date:"))
async def got_date(c: CallbackQuery, state: FSMContext):
    d = date.fromisoformat(c.data.split(":", 1)[1])
    await state.update_data(date=f"{d:%d.%m.%Y}")
    await state.set_state(Checkout.comment)
    await c.message.edit_text("Додайте коментар: текст листівки, побажання, час доставки — "
                              "або пропустіть цей крок.", reply_markup=kb.skip_kb)
    await c.answer()


async def show_summary(msg: Message, user_id, state: FSMContext):
    d = await state.get_data()
    lines, total = await cart_lines(user_id)
    ship = delivery_cost(total, d["delivery"])
    rows = "\n".join(f"• {esc(p['name'])} × {q} = {p['price'] * q:g} грн" for p, q in lines)
    how = f"🚚 Доставка: {esc(d['address'])}" if d["delivery"] == "delivery" else "🏪 Самовивіз"
    text = (f"<b>Перевірте замовлення</b>\n\n{rows}\n"
            + (f"Доставка: {ship} грн\n" if d["delivery"] == "delivery" else "")
            + f"<b>Разом: {total + ship:g} грн</b>\n\n"
            f"👤 {esc(d['name'])}, {esc(d['phone'])}\n{how}\n📅 {d['date']}\n"
            + (f"💬 {esc(d['comment'])}" if d.get("comment") else ""))
    await state.set_state(Checkout.confirm)
    await msg.answer(text, reply_markup=kb.confirm_kb)


@dp.callback_query(Checkout.comment, F.data == "skip_comment")
async def skip_comment(c: CallbackQuery, state: FSMContext):
    await state.update_data(comment="")
    await c.message.delete()
    await show_summary(c.message, c.from_user.id, state)
    await c.answer()


@dp.message(Checkout.comment, F.text)
async def got_comment(m: Message, state: FSMContext):
    await state.update_data(comment=m.text.strip()[:300])
    await show_summary(m, m.from_user.id, state)


@dp.callback_query(Checkout.confirm, F.data == "confirm")
async def confirm(c: CallbackQuery, state: FSMContext, bot: Bot):
    d = await state.get_data()
    lines, total = await cart_lines(c.from_user.id)
    if not lines:
        await state.clear()
        return await c.answer("Кошик порожній", show_alert=True)
    ship = delivery_cost(total, d["delivery"])
    items = [{"name": p["name"], "qty": q, "price": p["price"]} for p, q in lines]
    if ship:
        items.append({"name": "Доставка", "qty": 1, "price": ship})
    order = {"name": d["name"], "phone": d["phone"], "user_id": c.from_user.id, "items": items,
             "total": total + ship, "delivery": "Доставка" if d["delivery"] == "delivery" else "Самовивіз",
             "address": d.get("address", ""), "date": d["date"], "comment": d.get("comment", "")}
    await c.message.edit_reply_markup(reply_markup=None)
    try:
        number = await sheets.add_order(order)
    except Exception:
        logging.exception("add_order")
        await c.message.answer(SORRY, reply_markup=kb.confirm_kb)
        return await c.answer()
    await state.clear()
    carts.pop(c.from_user.id, None)
    await c.message.answer(f"✅ Замовлення <b>№{number}</b> прийнято!\n"
                           "Ми зателефонуємо найближчим часом для підтвердження. Дякуємо! 🌸",
                           reply_markup=kb.main_menu)
    await c.answer()
    if config.ADMIN_ID:
        rows = "\n".join(f"• {esc(i['name'])} × {i['qty']}" for i in items)
        await bot.send_message(
            config.ADMIN_ID,
            f"🆕 <b>Нове замовлення №{number}</b>\n{rows}\n<b>Сума: {order['total']:g} грн</b>\n\n"
            f"👤 {esc(order['name'])}, {esc(order['phone'])}\n{order['delivery']}"
            + (f": {esc(order['address'])}" if order["address"] else "")
            + f"\n📅 {order['date']}" + (f"\n💬 {esc(order['comment'])}" if order["comment"] else "")
            + "\n\nЗамовлення вже в Google Таблиці.")


# ---------- my orders ----------
@dp.message(F.text == kb.BTN_ORDERS)
async def my_orders(m: Message):
    try:
        orders = await sheets.user_orders(m.from_user.id)
    except Exception:
        logging.exception("orders")
        return await m.answer(SORRY)
    if not orders:
        return await m.answer("У вас ще немає замовлень. Загляньте в каталог 🌷")
    icons = {"Нове": "🟡", "Підтверджено": "🔵", "Доставляється": "🚚", "Виконано": "✅", "Скасовано": "❌"}
    rows = [f"{icons.get(o['status'], '•')} №{o['number']} від {o['created']} — {o['total']:g} грн, "
            f"<b>{esc(o['status'])}</b>" for o in orders]
    await m.answer("📦 <b>Ваші останні замовлення</b>\n" + "\n".join(rows))


async def main():
    missing = [k for k in ("BOT_TOKEN", "SHEET_URL", "SHEET_SECRET") if not getattr(config, k)]
    if missing:
        raise SystemExit("Fill in .env: " + ", ".join(missing))
    bot = Bot(config.BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
