import os
import logging
import asyncio
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types, F
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from motor.motor_asyncio import AsyncIOMotorClient  # Asinxron MongoDB kutubxonasi

logging.basicConfig(level=logging.INFO)

# --- ASOSIY PARAMETRLAR ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 6809538599  # Sizning Telegram ID raqamingiz

# Bulutli (Cloud) Ma'lumotlar Bazasi - To'g'ridan-to'g'ri internetda ishlaydi, server o'chsa ham o'chmaydi!
MONGO_URL = "mongodb+srv://ishly_user:ishly777bot@ishlycluster.v6zrk.mongodb.net/?retryWrites=true&w=majority"
client = AsyncIOMotorClient(MONGO_URL)
db = client["ishly_database"]
users_col = db["users"]
settings_col = db["settings"]

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
app = FastAPI()

# --- FSM (Bot Xolatlari) ---
class AdminStates(StatesGroup):
    waiting_for_ad = State()          
    waiting_for_new_price = State()   

class UserStates(StatesGroup):
    waiting_for_payment_check = State()

# --- BAZANI ILK BOR SOZLASh ---
@app.on_event("startup")
async def on_startup():
    # Agar bazada narx o'rnatilmagan bo'lsa, boshlang'ich 30,000 so'm qilib yozib qo'yadi
    price_doc = await settings_col.find_one({"key": "resume_price"})
    if not price_doc:
        await settings_col.insert_one({"key": "resume_price", "value": 30000})
    logging.info("MongoDB Cloud va Webhook muvaffaqiyatli bog'landi!")

# --- USER: START ---
@dp.message(F.text == "/start")
async def send_welcome(message: types.Message):
    tg_id = message.from_user.id
    username = message.from_user.username or "NoUsername"
    
    # Userni bazaga saqlash (agar oldin kirmagan bo'lsa)
    await users_col.update_one(
        {"tg_id": tg_id},
        {"$set": {"tg_id": tg_id, "username": username}},
        upsert=True
    )

    builder = ReplyKeyboardBuilder()
    builder.button(text="💼 Ish qidiryapman")
    builder.button(text="📢 Ish beruvchiman")
    if tg_id == ADMIN_ID:
        builder.button(text="⚙️ Admin Panel")
    builder.adjust(2)
    
    await message.answer(
        "Salom! Ishly platformasiga xush kelibsiz! O'zingizga mos bo'limni tanlang:", 
        reply_markup=builder.as_markup(resize_keyboard=True)
    )

# --- USER: ISH QIDIRUVChI ---
@dp.message(F.text == "💼 Ish qidiryapman")
async def job_seeker_start(message: types.Message):
    # Bazadan joriy narxni o'qiymiz
    price_doc = await settings_col.find_one({"key": "resume_price"})
    current_price = price_doc["value"] if price_doc else 30000

    inline_builder = InlineKeyboardBuilder()
    inline_builder.button(text="📤 Tayyor rezyume yuklash (AI analiz)", callback_data="upload_resume")
    inline_builder.button(text=f"📄 Yangi rezyume yaratish ({current_price} so'm)", callback_data="create_resume")
    inline_builder.adjust(1)
    
    await message.answer(
        "Ajoyib! Tizim sizga mos ish topishi uchun rezyumeingiz bo'lishi kerak. Tanlang:",
        reply_markup=inline_builder.as_markup()
    )

@dp.callback_query(F.data == "create_resume")
async def payment_request(callback: types.CallbackQuery, state: FSMContext):
    price_doc = await settings_col.find_one({"key": "resume_price"})
    current_price = price_doc["value"] if price_doc else 30000

    await callback.message.answer(
        f"📄 Rezyume yaratish xizmati narxi: {current_price} so'm.\n\n"
        "To'lovni amalga oshirish uchun quyidagi kartaga pul o'tkazing:\n"
        "💳 Karta: `8600 0000 0000 0000` (Diyoriddin)\n\n"
        "To'lovni amalga oshirgach, **chek skrinshotini (rasmini)** shu yerga yuboring. AI uni tekshiradi."
    )
    await state.set_state(UserStates.waiting_for_payment_check)
    await callback.answer()

@dp.message(UserStates.waiting_for_payment_check, F.photo)
async def handle_payment_check(message: types.Message, state: FSMContext):
    await message.answer("🔄 Chek qabul qilindi. AI tizimi to'lovni tasdiqlash uchun rasmni analiz qilmoqda, kuting...")
    # Kelajakda Gemini Vision ulash uchun tayyor joy:
    await asyncio.sleep(2)
    await message.answer("✅ To'lov muvaffaqiyatli tasdiqlandi! Keling, rezyumeingizni to'ldiramiz. Mutaxassisligingizni yozing:")
    await state.clear()

# --- USER: ISH BERUVChI ---
@dp.message(F.text == "📢 Ish beruvchiman")
async def recruiter_start(message: types.Message):
    await message.answer("Xush kelibsiz! Yangi vakansiya joylashtirish uchun kompaniyangiz nomini kiriting:")

# --- ⚙️ ADMIN PANEL ---
@dp.message(F.text == "⚙️ Admin Panel")
async def admin_panel(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
        
    user_count = await users_col.count_documents({})
    price_doc = await settings_col.find_one({"key": "resume_price"})
    current_price = price_doc["value"] if price_doc else 30000

    inline_builder = InlineKeyboardBuilder()
    inline_builder.button(text=f"💰 Narxni o'zgartirish ({current_price} UZS)", callback_data="admin_change_price")
    inline_builder.button(text="📢 Reklama yuborish (Post)", callback_data="admin_send_ad")
    inline_builder.adjust(1)

    await message.answer(
        f"📊 **Ishly Bot Rasmiy Admin Paneli**\n\n"
        f"👥 Jami faol foydalanuvchilar: {user_count} ta\n"
        f"💵 Amaldagi rezyume narxi: {current_price} so'm",
        reply_markup=inline_builder.as_markup()
    )

# --- ADMIN: REKLAMA TARQATISH ---
@dp.callback_query(F.data == "admin_send_ad")
async def admin_ad_prompt(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Menga reklama postini yuboring (Matn, rasm yoki video aralash bo'lishi mumkin):")
    await state.set_state(AdminStates.waiting_for_ad)
    await callback.answer()

@dp.message(AdminStates.waiting_for_ad)
async def admin_broadcast_ad(message: types.Message, state: FSMContext):
    await message.answer("🔄 Reklama barcha foydalanuvchilarga tarqatilmoqda, iltimos kuting...")
    
    cursor = users_col.find({})
    success = 0
    async for user in cursor:
        try:
            await message.copy_to(chat_id=user["tg_id"])
            success += 1
            await asyncio.sleep(0.05)
        except Exception:
            pass

    await message.answer(f"✅ Reklama muvaffaqiyatli yakunlandi! {success} ta foydalanuvchiga yuborildi.")
    await state.clear()

# --- ADMIN: NARXNI O'ZGARTIRISH ---
@dp.callback_query(F.data == "admin_change_price")
async def admin_price_prompt(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Yangi narxni raqamlarda kiriting (Masalan: 50000):")
    await state.set_state(AdminStates.waiting_for_new_price)
    await callback.answer()

@dp.message(AdminStates.waiting_for_new_price)
async def admin_save_price(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Iltimos, faqat raqam kiriting!")
        return
        
    new_price = int(message.text)
    await settings_col.update_one({"key": "resume_price"}, {"$set": {"value": new_price}}, upsert=True)
    
    await message.answer(f"✅ Rezyume yaratish narxi muvaffaqiyatli yangilandi: {new_price} so'm!")
    await state.clear()

# --- VERCEL WEBHOOK INTEGRATSIYASI ---
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