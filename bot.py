import os
import logging
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types, F
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 6809538599  # Sizning Telegram ID raqamingiz

# Vaqtincha ma'lumotlar ombori (Xatolik bermasligi uchun eng xavfsiz yo'l)
ACTIVE_USERS = {6809538599}  # Avtomat sizni qo'shib qo'yadi
CURRENT_PRICE = 30000

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
app = FastAPI()

class AdminStates(StatesGroup):
    waiting_for_ad = State()          
    waiting_for_new_price = State()   

# --- USER: START ---
@dp.message(F.text == "/start")
async def send_welcome(message: types.Message):
    tg_id = message.from_user.id
    ACTIVE_USERS.add(tg_id)  # Foydalanuvchini ro'yxatga qo'shish

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
    global CURRENT_PRICE
    inline_builder = InlineKeyboardBuilder()
    inline_builder.button(text="📤 Tayyor rezyume yuklash (AI analiz)", callback_data="upload_resume")
    inline_builder.button(text=f"📄 Yangi rezyume yaratish ({CURRENT_PRICE} so'm)", callback_data="create_resume")
    inline_builder.adjust(1)
    
    await message.answer(
        "Ajoyib! Tizim sizga mos ish topishi uchun rezyumeingiz bo'lishi kerak. Tanlang:",
        reply_markup=inline_builder.as_markup()
    )

# --- USER: ISH BERUVChI ---
@dp.message(F.text == "📢 Ish beruvchiman")
async def recruiter_start(message: types.Message):
    await message.answer("Xush kelibsiz! Yangi vakansiya joylashtirish uchun kompaniyangiz nomini kiriting:")

# --- ⚙️ ADMIN PANEL ---
@dp.message(F.text == "⚙️ Admin Panel")
async def admin_panel(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
        
    global CURRENT_PRICE
    user_count = len(ACTIVE_USERS)

    inline_builder = InlineKeyboardBuilder()
    inline_builder.button(text=f"💰 Narxni o'zgartirish ({CURRENT_PRICE} UZS)", callback_data="admin_change_price")
    inline_builder.button(text="📢 Reklama yuborish (Post)", callback_data="admin_send_ad")
    inline_builder.adjust(1)

    await message.answer(
        f"📊 **Ishly Bot Rasmiy Admin Paneli**\n\n"
        f"👥 Jami faol foydalanuvchilar: {user_count} ta\n"
        f"💵 Amaldagi rezyume narxi: {CURRENT_PRICE} so'm",
        reply_markup=inline_builder.as_markup()
    )

# --- ADMIN: REKLAMA TARQATISH ---
@dp.callback_query(F.data == "admin_send_ad")
async def admin_ad_prompt(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Menga reklama postini yuboring (Matn, rasm yoki video bo'lishi mumkin):")
    await state.set_state(AdminStates.waiting_for_ad)
    await callback.answer()

@dp.message(AdminStates.waiting_for_ad)
async def admin_broadcast_ad(message: types.Message, state: FSMContext):
    await message.answer("🔄 Reklama faol foydalanuvchilarga tarqatilmoqda...")
    
    success = 0
    for user_id in list(ACTIVE_USERS):
        try:
            await message.copy_to(chat_id=user_id)
            success += 1
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
        
    global CURRENT_PRICE
    CURRENT_PRICE = int(message.text)
    await message.answer(f"✅ Rezyume yaratish narxi muvaffaqiyatli yangilandi: {CURRENT_PRICE} so'm!")
    await state.clear()

# --- VERCEL WEBHOOK INTEGRATSIYASI ---
WEBHOOK_URL = f"/webhook/{BOT_TOKEN}"
@app.post(WEBHOOK_URL)
async def bot_webhook(request: Request):
    try:
        update_data = await request.json()
        update = types.Update.model_validate(update_data)
        await dp.feed_update(bot, update)
    except Exception as e:
        logging.error(f"Webhook error: {e}")
    return {"status": "ok"}