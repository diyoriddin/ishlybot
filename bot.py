import os
import logging
import asyncio
import pymysql  # MySQL bilan ishlash uchun
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types, F
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 6809538599 # 👈 BU YERGA O'ZINGIZNING TELEGRAM ID-INGIZNI YOZING!

# Masofaviy MySQL ulanish parametrlari (Vercel Environment Variables-dan oladi)
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "ishly_db")

def get_db_connection():
    return pymysql.connect(
        host=DB_HOST, user=DB_USER, password=DB_PASSWORD, database=DB_NAME,
        cursorclass=pymysql.cursors.DictCursor
    )

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
app = FastAPI()

# --- FSM (Xolatlar) ---
class AdminStates(StatesGroup):
    waiting_for_ad = State()          # Reklama posti uchun
    waiting_for_new_price = State()   # Narxni o'zgartirish uchun

# --- BAZANI INICIALIZATSIYA QILISH ---
@app.on_event("startup")
async def on_startup():
    # Baza jadvallarini avtomatik yaratish
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # Foydalanuvchilar jadvali
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    tg_id BIGINT PRIMARY KEY,
                    role VARCHAR(20) DEFAULT 'seeker',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # Tizim sozlamalari (Narxlar uchun)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    `key` VARCHAR(50) PRIMARY KEY,
                    `value` INT NOT NULL
                )
            """)
            # Boshlang'ich narxni kiritish (agar mavjud bo'lmasa)
            cursor.execute("INSERT IGNORE INTO settings (`key`, `value`) VALUES ('resume_price', 30000)")
        conn.commit()
        conn.close()
    except Exception as e:
        logging.error(f"Baza bilan bog'lanishda xatolik: {e}")

# --- FOYDALANUVCHINI BAZAGA QO'ShISh ---
@dp.message(F.text == "/start")
async def send_welcome(message: types.Message):
    tg_id = message.from_user.id
    
    # Foydalanuvchini bazaga yozamiz
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("INSERT IGNORE INTO users (tg_id) VALUES (%s)", (tg_id))
        conn.commit()
        conn.close()
    except Exception as e:
        logging.error(f"Userni bazaga yozishda xato: {e}")

    builder = ReplyKeyboardBuilder()
    builder.button(text="💼 Ish qidiryapman")
    builder.button(text="📢 Ish beruvchiman")
    if tg_id == ADMIN_ID:
        builder.button(text="⚙️ Admin Panel")
    builder.adjust(2)
    
    await message.answer("Ishly Botga xush kelibsiz! Bo'limni tanlang:", reply_markup=builder.as_markup(resize_keyboard=True))
# --- ⚙️ ADMIN PANEL ASOSIY MENYUSI ---
@dp.message(F.text == "⚙️ Admin Panel")
async def admin_panel(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
        
    # Bazadan joriy narxni va foydalanuvchilar sonini olamiz
    conn = get_db_connection()
    with conn.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) as count FROM users")
        user_count = cursor.fetchone()['count']
        cursor.execute("SELECT `value` FROM settings WHERE `key`='resume_price'")
        current_price = cursor.fetchone()['value']
    conn.close()

    inline_builder = InlineKeyboardBuilder()
    inline_builder.button(text=f"💰 Narxni o'zgartirish ({current_price} so'm)", callback_data="admin_change_price")
    inline_builder.button(text="📢 Reklama yuborish (Post)", callback_data="admin_send_ad")
    inline_builder.adjust(1)

    await message.answer(
        f"📊 **Ishly Bot Admin Paneli**\n\n"
        f"👥 Jami foydalanuvchilar: {user_count} ta\n"
        f"💵 Rezyume yaratish narxi: {current_price} so'm",
        reply_markup=inline_builder.as_markup()
    )
        

# --- 📢 REKLAMA TARQATISH MANTIQLARI ---
@dp.callback_query(F.data == "admin_send_ad")
async def admin_ad_prompt(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Menga reklama postini yuboring (Bu matn, rasm, video yoki rasm+matn bo'lishi mumkin):")
    await state.set_state(AdminStates.waiting_for_ad)
    await callback.answer()

@dp.message(AdminStates.waiting_for_ad)
async def admin_broadcast_ad(message: types.Message, state: FSMContext):
    await message.answer("🔄 Reklama barcha foydalanuvchilarga tarqatilmoqda, kuting...")
    
    # Bazadan barcha userlarni olamiz
    conn = get_db_connection()
    with conn.cursor() as cursor:
        cursor.execute("SELECT tg_id FROM users")
        users = cursor.fetchall()
    conn.close()

    success = 0
    failed = 0
    for user in users:
        try:
            # Foydalanuvchiga kelgan xabarni shundoq nusxalab (copy) otib yuboramiz
            await message.copy_to(chat_id=user['tg_id'])
            success += 1
            await asyncio.sleep(0.05) # Telegram limitlariga urilmaslik uchun kichik pauza
        except Exception:
            failed += 1

    await message.answer(f"✅ Reklama tarqatish yakunlandi!\n\n🚀 Muvaffaqiyatli: {success} ta\n❌ Bloklaganlar: {failed} ta")
    await state.clear()

# --- 💰 NARXNI O'ZGARTIRISH MANTIQLARI ---
@dp.callback_query(F.data == "admin_change_price")
async def admin_price_prompt(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Yangi narxni raqamlarda kiriting (Masalan: 40000):")
    await state.set_state(AdminStates.waiting_for_new_price)
    await callback.answer()

@dp.message(AdminStates.waiting_for_new_price)
async def admin_save_price(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Iltimos, faqat raqam kiriting!")
        return
        
    new_price = int(message.text)
    conn = get_db_connection()
    with conn.cursor() as cursor:
        cursor.execute("UPDATE settings SET `value`=%s WHERE `key`='resume_price'", (new_price))
    conn.commit()
    conn.close()

    await message.answer(f"✅ Rezyume yaratish narxi muvaffaqiyatli o'zgartirildi: {new_price} so'm!")
    await state.clear()

# --- VERCEL WEBHOOK INTEGRATION ---
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
@app.post(WEBHOOK_PATH)
async def bot_webhook(request: Request):
    try:
        update_data = await request.json()
        update = types.Update.model_validate(update_data)
        await dp.feed_update(bot, update)
    except Exception as e:
        logging.error(f"Webhook error: {e}")
    return {"status": "ok"}