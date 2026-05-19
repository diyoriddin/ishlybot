import os
import asyncio
import logging
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.telegram import TelegramAPIServer
from aiogram.client.session.aiohttp import AiohttpSession

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

logging.basicConfig(level=logging.INFO)

# TelegramAPIServer.from_base ishlatamiz. 
# Hugging Face blokidan o'tish uchun xalqaro tekin muqobil xavfsiz proxy manzili:
CUSTOM_API_SERVER = TelegramAPIServer.from_base("https://teleapi.tech/bot")

session = AiohttpSession(api=CUSTOM_API_SERVER)
bot = Bot(token=BOT_TOKEN, session=session)
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
        f"**Ishly** platformasiga xush kelibsiz. Tizimimiz hozirda Hugging Face bulutida asinxron rejimda ishlamoqda.\n\n"
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
    logging.info("Ishly bot xavfsiz tarmoq liniyasi orqali ulanmoqda...")
    
    while True:
        try:
            await bot.delete_webhook(drop_pending_updates=True)
            logging.info("Aylama yo'l muvaffaqiyatli o'rnatildi! Telegram bot kutish rejimida...")
            await dp.start_polling(bot)
        except Exception as e:
            logging.error(f"Ulanishda xato: {e}. 5 soniyadan keyin qayta ulanadi...")
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())