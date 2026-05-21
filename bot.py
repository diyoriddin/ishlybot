import os
import logging
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import ReplyKeyboardBuilder

# Logging sozlamalari
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
# Vercel har xil havolalar berganda adashmaslik uchun asosiy ishlab turgan domeningiz:
WEBHOOK_HOST = "ishlybot-bi6r.vercel.app"
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"https://{WEBHOOK_HOST}{WEBHOOK_PATH}"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
app = FastAPI()

# 1. Loyiha Vercel serverida ilk bor uyg'onganda Webhook-ni Telegram-ga avtomatik o'rnatish
@app.on_event("startup")
async def on_startup():
    logging.info(f"Webhook o'rnatilmoqda: {WEBHOOK_URL}")
    await bot.set_webhook(
        url=WEBHOOK_URL,
        drop_pending_updates=True
    )

# 2. Asosiy sahifa (Brauzerda tekshirish uchun)
@app.get("/")
async def root():
    return {"status": "Ishly Bot is working via Webhook!"}

# 3. Telegram-dan keladigan so'rovlarni aiogram dispatcher-iga uzatish (Eng muhim joyi!)
@app.post(WEBHOOK_PATH)
async def bot_webhook(request: Request):
    try:
        update_data = await request.json()
        update = types.Update.model_validate(update_data)
        # Kelgan xabarni aiogram kutubxonasining o'ziga feed qilamiz (topshiramiz)
        await dp.feed_update(bot, update)
    except Exception as e:
        logging.error(f"Xabarni qayta ishlashda xatolik: {e}")
    return {"status": "ok"}


# --- BOT HANDLERLARI (Mantiq qismi) ---

@dp.message(lambda message: message.text == "/start")
async def send_welcome(message: types.Message):
    # Oldingi kodingizdagi chiroyli tugmalarni va matnlarni aynan mana shu erga qaytarasiz!
    builder = ReplyKeyboardBuilder()
    builder.button(text="💼 Ish qidiryapman")
    builder.button(text="📢 Ish beruvchiman")
    builder.adjust(2)
    
    await message.answer(
        "Salom! Ishly platformasiga xush kelibsiz! Uzingizga mos bo'limni tanlang:",
        reply_markup=builder.as_markup(resize_keyboard=True)
    )