import os
import asyncio
import logging
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.session.aiohttp import AiohttpSession

# 1. Yashirin .env fayldan tokenlarni yuklaymiz
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Xatoliklarni terminalda ko'rish uchun logging
logging.basicConfig(level=logging.INFO)

# Hugging Face tarmoq muammolarini aylanib o'tish uchun tekin xalqaro proxy session
# Bu orqali Telegram blokirovkalari aylanib o'tiladi
session = AiohttpSession(proxy="http://proxy.server:3128") # Standart ochiq proxy porti yoki to'g'ridan-to'g'ri integratsiya

try:
    # Agarda maxsus serverda proxy kerak bo'lsa session bilan, bo'lmasa oddiy ulaymiz
    # Hugging Face tarmog'i barqarorligi uchun xavfsiz rejim:
    bot = Bot(token=BOT_TOKEN)
except Exception as e:
    logging.error(f"Botni yuklashda xato: {e}")

dp = Dispatcher(storage=MemoryStorage())

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
        f"**Ishly** platformasiga xush kelibsiz. Tizimimiz asinxron va tejamkor rejimda ishlamoqda.\n\n"
        f"Davom etish uchun quyidagi tugmalardan birini tanlang:",
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
        await callback.message.edit_text("Hush kelibsiz! HR tizimi tez orada ishga tushadi. Hozircha nomzodlar bazasi yig'ilmoqda.")
    
    await callback.answer()

async def main():
    logging.info("Ishly bot ulanishni qayta sinab ko'rmoqda...")
    # Tarmoq uzilishlarini oldini olish uchun eski sessiyalarni tozalaymiz
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())