import os
import asyncio
import logging
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# Logging sozlamalari
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
# Vercel-dagi loyihang linki (Buni deploydan keyin settingsga ham kiritamiz)
VERCEL_URL = os.getenv("VERCEL_URL") 
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"https://{VERCEL_URL}{WEBHOOK_PATH}" if VERCEL_URL else ""

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
app = FastAPI()

class BotStates(StatesGroup):
    choosing_role = State()
    writing_resume = State()

@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [
            types.InlineKeyboardButton(text="🙋‍♂️ Ish qidiryapman", callback_data="role_candidate"),
            types.InlineKeyboardButton(text="💼 Ish beruvchiman (HR)", callback_data="role_hr")
        ]
    ])
    await message.answer(
        f"Salom {message.from_user.full_name}!\n"
        f"**Ishly** platformasiga xush kelibsiz. Tizim Webhook rejimida ishlamoqda.\n\n"
        f"Davom etish uchun variantlardan birini tanlang:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    await state.set_state(BotStates.choosing_role)

@dp.callback_query(BotStates.choosing_role, F.data.startswith("role_"))
async def process_role(callback: types.CallbackQuery, state: FSMContext):
    role = callback.data.split("_")[1]
    if role == "candidate":
        await callback.message.edit_text(
            "Ajoyib! O'zingiz haqingizda erkin matn ko'rinishida yozing.\n"
            "Masalan: *'Ismim Diyorbek, Python-dasturchiman, aiogram va fastapi bilaman'*.\n\n"
            "AI tizimimiz ma'lumotlarni qayta ishlab, sizga tekin CV tayyorlab beradi!"
        )
        await state.set_state(BotStates.writing_resume)
    elif role == "hr":
        await callback.message.edit_text("Xush kelibsiz! HR tizimi tez orada ishga tushadi.")
    await callback.answer()

# Vercel uyg'onganda Telegram-ga Webhook manzilini ulab qo'yadi
@app.on_event("startup")
async def on_startup():
    if WEBHOOK_URL:
        logging.info(f"Webhook o'rnatilmoqda: {WEBHOOK_URL}")
        await bot.set_webhook(url=WEBHOOK_URL, drop_pending_updates=True)

# Telegram-dan keladigan xabarlarni qabul qiluvchi API nuqtasi
@app.post(WEBHOOK_PATH)
async def bot_webhook(request: Request):
    update = types.Update.parse_obj(await request.json())
    await dp.feed_update(bot, update)
    return {"status": "ok"}

@app.get("/")
async def root():
    return {"status": "Ishly Bot is working via Webhook!"}