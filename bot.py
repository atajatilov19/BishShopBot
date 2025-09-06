import logging
import sqlite3
from datetime import datetime

from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
from aiogram.utils import executor
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup

# ============ НАСТРОЙКИ (уже с твоими данными) ============
TOKEN = "8347167643:AAFoKAXwAjaSHTUkdQ2hFzqirC5CGpoLEdI"
CHANNEL_USERNAME = "@bishsh0p"          # канал
ADMIN_USERNAME = "nuyuki_1"             # твой ник без @
SUPPORT_USERNAME = "nuyuki_1"           # поддержка
DISCUSSION_URL = "https://t.me/bishsh0p"  # ссылка на чат обсуждения (потом заменишь на реальную при желании)

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN, parse_mode="HTML")
dp = Dispatcher(bot, storage=MemoryStorage())

BOT_USERNAME = None
DB_PATH = "data.db"

# -------------------- БАЗА --------------------
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = db(); cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, balance INTEGER DEFAULT 0)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT, description TEXT, price INTEGER, photo_file_id TEXT, channel_message_id INTEGER)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS qrcodes (amount INTEGER PRIMARY KEY, file_id TEXT)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS topups (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount INTEGER, status TEXT, created_at TEXT)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS purchases (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, product_id INTEGER, amount INTEGER, created_at TEXT)""")
    conn.commit(); conn.close()

def get_or_create_user(u: types.User):
    conn = db(); cur = conn.cursor()
    cur.execute("SELECT 1 FROM users WHERE user_id=?", (u.id,))
    if not cur.fetchone():
        cur.execute("INSERT INTO users(user_id, username, balance) VALUES(?,?,0)", (u.id, u.username or ""))
        conn.commit()
    conn.close()

def get_balance(uid:int)->int:
    conn = db(); cur = conn.cursor()
    cur.execute("SELECT balance FROM users WHERE user_id=?", (uid,))
    row = cur.fetchone(); conn.close()
    return int(row["balance"]) if row else 0

def add_balance(uid:int, amount:int):
    conn = db(); cur = conn.cursor()
    cur.execute("UPDATE users SET balance=COALESCE(balance,0)+? WHERE user_id=?", (amount, uid))
    conn.commit(); conn.close()

def deduct_balance(uid:int, amount:int)->bool:
    if get_balance(uid) < amount: return False
    conn = db(); cur = conn.cursor()
    cur.execute("UPDATE users SET balance=balance-? WHERE user_id=?", (amount, uid))
    conn.commit(); conn.close(); return True

def count_products()->int:
    conn = db(); cur = conn.cursor()
    cur.execute("SELECT COUNT(*) c FROM products"); c = cur.fetchone()["c"]
    conn.close(); return c

def is_admin(u: types.User)->bool:
    return (u.username or "").lower()==ADMIN_USERNAME.lower()

def main_menu_kb():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(InlineKeyboardButton("💳 Платежи", callback_data="payments"))
    kb.add(
        InlineKeyboardButton("🆘 Поддержка", url=f"https://t.me/{SUPPORT_USERNAME}"),
        InlineKeyboardButton("👥 Обсуждение", url=DISCUSSION_URL),
    )
    kb.add(InlineKeyboardButton("📢 Канал", url=f"https://t.me/{CHANNEL_USERNAME.lstrip('@')}"))
    return kb

def amounts_kb():
    kb = InlineKeyboardMarkup(row_width=3)
    for a in [50,100,200,500,1000,2000]:
        kb.insert(InlineKeyboardButton(str(a), callback_data=f"topup:{a}"))
    kb.add(InlineKeyboardButton("🏠 Меню", callback_data="menu"))
    return kb

def buy_menu_kb(pid:int, price:int):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(InlineKeyboardButton(f"💸 Оплатить {price} с баланса", callback_data=f"pay:{pid}"))
    kb.add(InlineKeyboardButton("💳 Платежи", callback_data="payments"))
    kb.add(InlineKeyboardButton("❌ Отмена", callback_data="menu"))
    return kb

@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    get_or_create_user(message.from_user)
    args = message.get_args()
    if args.startswith("buy_"):
        try: pid = int(args.split("_",1)[1])
        except: await message.answer("Товар не найден.", reply_markup=ReplyKeyboardRemove()); return
        conn = db(); cur = conn.cursor()
        cur.execute("SELECT * FROM products WHERE id=?", (pid,)); p = cur.fetchone(); conn.close()
        if not p: await message.answer("Товар не найден."); return
        bal = get_balance(message.from_user.id)
        text = (f"<b>{p['title']}</b>\nЦена: <b>{p['price']} KGS</b>\n\n{p['description']}\n\nВаш баланс: <b>{bal} KGS</b>")
        await message.answer_photo(p['photo_file_id'], caption=text, reply_markup=buy_menu_kb(p['id'], p['price']))
        return
    bal = get_balance(message.from_user.id); placed = count_products()
    text = (f"👋 Привет, {message.from_user.first_name}!\n\n⚡ Добро пожаловать в BishShop ⚡\n\n"
            f"📄 Размещено объявлений: <b>{placed}</b>\n💰 Ваш баланс: <b>{bal} KGS</b>")
    await message.answer(text, reply_markup=main_menu_kb())

@dp.callback_query_handler(lambda c: c.data=="menu")
async def cb_menu(c: types.CallbackQuery):
    bal = get_balance(c.from_user.id); placed = count_products()
    await c.message.answer(f"⚡ BishShop\n\n📄 Размещено: <b>{placed}</b>\n💰 Баланс: <b>{bal} KGS</b>", reply_markup=main_menu_kb())
    await c.answer()

@dp.callback_query_handler(lambda c: c.data=="payments")
async def cb_payments(c: types.CallbackQuery):
    await c.message.answer("Введите сумму пополнения или выберите готовую:", reply_markup=amounts_kb())
    await c.answer()

@dp.callback_query_handler(lambda c: c.data.startswith("topup:"))
async def cb_topup(c: types.CallbackQuery):
    amount = int(c.data.split(":")[1])
    conn = db(); cur = conn.cursor()
    cur.execute("SELECT file_id FROM qrcodes WHERE amount=?", (amount,))
    row = cur.fetchone(); conn.close()
    if not row:
        if is_admin(c.from_user):
            await c.message.answer(f"QR для {amount} KGS не настроен. Пришлите картинку и ответьте командой:\n<code>/set_qr {amount}</code>")
        else:
            await c.message.answer("⚠️ Оплата временно недоступна. Попробуйте позже.")
        await c.answer(); return
    file_id = row["file_id"]
    caption = (f"Оплата <b>{amount} KGS</b>.\n1) Откройте банковское приложение.\n2) Отсканируйте QR ниже.\n3) После оплаты отправьте чек в поддержку (@{SUPPORT_USERNAME}).")
    kb = InlineKeyboardMarkup().add(InlineKeyboardButton("Я оплатил", url=f"https://t.me/{SUPPORT_USERNAME}")).add(InlineKeyboardButton("🏠 Меню", callback_data="menu"))
    conn = db(); cur = conn.cursor()
    cur.execute("INSERT INTO topups(user_id,amount,status,created_at) VALUES(?,?,'pending',?)",
                (c.from_user.id, amount, datetime.utcnow().isoformat()))
    conn.commit(); conn.close()
    await c.message.answer_photo(file_id, caption=caption, reply_markup=kb)
    await c.answer("Отправил QR")

@dp.callback_query_handler(lambda c: c.data.startswith("pay:"))
async def cb_pay(c: types.CallbackQuery):
    pid = int(c.data.split(":")[1])
    conn = db(); cur = conn.cursor()
    cur.execute("SELECT * FROM products WHERE id=?", (pid,)); p = cur.fetchone(); conn.close()
    if not p: await c.answer("Товар не найден", show_alert=True); return
    price = int(p["price"])
    if not deduct_balance(c.from_user.id, price):
        await c.message.answer("❌ Недостаточно средств. Пополните баланс в «Платежи».", reply_markup=amounts_kb()); await c.answer(); return
    conn = db(); cur = conn.cursor()
    cur.execute("INSERT INTO purchases(user_id,product_id,amount,created_at) VALUES(?,?,?,?)",
                (c.from_user.id, pid, price, datetime.utcnow().isoformat()))
    conn.commit(); conn.close()
    await c.message.answer(f"✅ Покупка <b>{p['title']}</b> на <b>{price} KGS</b> успешно проведена.")
    await c.answer("Успех")

@dp.message_handler(commands=["set_qr"])
async def cmd_set_qr(message: types.Message):
    if not is_admin(message.from_user): return
    args = message.get_args().strip()
    if not message.reply_to_message or not message.reply_to_message.photo:
        await message.answer("Пришли команду в ответ на фото QR.\nПример: <code>/set_qr 500</code>"); return
    try: amount = int(args)
    except: await message.answer("Укажи сумму числом. Пример: <code>/set_qr 500</code>"); return
    file_id = message.reply_to_message.photo[-1].file_id
    conn = db(); cur = conn.cursor()
    cur.execute("INSERT OR REPLACE INTO qrcodes(amount,file_id) VALUES(?,?)", (amount, file_id))
    conn.commit(); conn.close()
    await message.answer(f"QR на {amount} KGS сохранён ✅")

class PostProduct(StatesGroup):
    waiting_photo = State()
    waiting_title = State()
    waiting_price = State()
    waiting_description = State()

@dp.message_handler(commands=["post"])
async def cmd_post(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user): return
    await state.finish()
    await message.answer("Пришли <b>фото товара</b> сообщением.")
    await PostProduct.waiting_photo.set()

@dp.message_handler(content_types=["photo"], state=PostProduct.waiting_photo)
async def post_photo(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user): return
    await state.update_data(photo_id=message.photo[-1].file_id)
    await message.answer("Название товара?")
    await PostProduct.waiting_title.set()

@dp.message_handler(state=PostProduct.waiting_title)
async def post_title(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user): return
    await state.update_data(title=message.text.strip())
    await message.answer("Цена (KGS)?")
    await PostProduct.waiting_price.set()

@dp.message_handler(state=PostProduct.waiting_price)
async def post_price(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user): return
    try: price = int(message.text.strip())
    except: await message.answer("Введи цену числом."); return
    await state.update_data(price=price)
    await message.answer("Короткое описание?")
    await PostProduct.waiting_description.set()

@dp.message_handler(state=PostProduct.waiting_description)
async def post_desc(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user): return
    await state.update_data(description=message.text.strip())
    data = await state.get_data()
    conn = db(); cur = conn.cursor()
    cur.execute("INSERT INTO products(title,description,price,photo_file_id) VALUES(?,?,?,?)",
                (data["title"], data["description"], data["price"], data["photo_id"]))
    product_id = cur.lastrowid; conn.commit(); conn.close()

    me = await bot.get_me()
    deep_url = f"https://t.me/{me.username}?start=buy_{product_id}"
    caption = f"<b>{data['title']}</b>\nЦена: <b>{data['price']} KGS</b>\n\n{data['description']}"
    kb = InlineKeyboardMarkup().add(InlineKeyboardButton("🛒 Купить", url=deep_url))
    msg = await bot.send_photo(chat_id=CHANNEL_USERNAME, photo=data["photo_id"], caption=caption, reply_markup=kb)

    conn = db(); cur = conn.cursor()
    cur.execute("UPDATE products SET channel_message_id=? WHERE id=?", (msg.message_id, product_id))
    conn.commit(); conn.close()

    await message.answer("✅ Товар опубликован в канале.")
    await state.finish()

@dp.message_handler(commands=["balance"])
async def cmd_balance(message: types.Message):
    get_or_create_user(message.from_user)
    await message.answer(f"Ваш баланс: <b>{get_balance(message.from_user.id)} KGS</b>")

@dp.message_handler(commands=["addbalance"])
async def cmd_addbalance(message: types.Message):
    if not is_admin(message.from_user): return
    parts = message.get_args().split()
    if len(parts)!=2: await message.answer("Формат: <code>/addbalance @username 500</code>"); return
    user_ref, amount_s = parts
    try: amount = int(amount_s)
    except: await message.answer("Сумма должна быть числом."); return
    conn = db(); cur = conn.cursor()
    if user_ref.startswith("@"):
        cur.execute("SELECT user_id FROM users WHERE lower(username)=?", (user_ref[1:].lower(),))
    else:
        try: uid = int(user_ref); cur.execute("SELECT user_id FROM users WHERE user_id=?", (uid,))
        except: await message.answer("Неверный идентификатор."); conn.close(); return
    row = cur.fetchone(); conn.close()
    if not row: await message.answer("Пользователь не найден (он должен написать боту /start)."); return
    add_balance(row["user_id"], amount)
    await message.answer(f"Начислено {amount} KGS.")
    try: await bot.send_message(row["user_id"], f"💰 На баланс начислено {amount} KGS.")
    except: pass

async def on_startup(_):
    global BOT_USERNAME
    init_db()
    me = await bot.get_me()
    BOT_USERNAME = me.username
    logging.info(f"Bot @{BOT_USERNAME} запущен.")

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)
