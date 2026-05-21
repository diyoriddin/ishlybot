import os
import logging
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types
from aiogram.fsm.storage.memory import MemoryStorage

# Logging sozlamalari
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")

# Vercel har safar har xil link berganda adashib ketmasligi uchun
# request kelgan paytda domenni avtomatik aniqlaydigan qilamiz!
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
app = FastAPI()

# Asosiy sahifa (Vercel ishlab turganini tekshirish uchun)
@app.get("/")
async def root():
    return {"status": "Ishly Bot is working via Webhook!"}

# Telegram-dan keladigan xabarlarni qabul qiluvchi API nuqtasi
@app.post(WEBHOOK_PATH)
async def bot_webhook(request: Request):
    # Xabar kelgan paytda Vercel-ning joriy linkini avtomatik aniqlaymiz
    host = request.headers.get("host")
    if host:
        current_webhook_url = f"https://{host}{WEBHOOK_PATH}"
        try:
            webhook_info = await bot.get_webhook_info()
            if webhook_info.url != current_webhook_url:
                logging.info(f"Webhook yangilanmoqda: {current_webhook_url}")
                await bot.set_webhook(url=current_webhook_url, drop_pending_updates=True)
        except Exception as e:
            logging.error(f"Webhook o'rnatishda xatolik: {e}")

    # Kelgan xabarni aiogram handlerlariga yetkazish
    try:
        update_data = await request.json()
        update = types.Update.model_validate(update_data)
        await dp.feed_update(bot, update)
    except Exception as e:
        logging.error(f"Xabarni qayta ishlashda xatolik: {e}")
        
    return {"status": "ok"}

# --- BOT HANDLERLARI (Sening boting mantiqiy qismi) ---

@dp.message(lambda message: message.text == "/start")
async def send_welcome(message: types.Message):
    # Bu yerga o'zingning eski start handleringni va tugmalaringni joylashtirishing mumkin
    await message.reply("Salom! Ishly platformasiga xush kelibsiz!")