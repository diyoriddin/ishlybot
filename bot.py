import os
import asyncio
import logging
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# 1. Yashirin .env fayldan tokenlarni yuklaymiz
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Xatoliklarni terminalda ko'rish uchun logging
logging.basicConfig(level=logging.INFO)

# Bot va Dispatcher (FSM xotirasi bilan)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# FSM - Bot holatlarini eslab qolish tizimi
class BotStates(StatesGroup):
    choosing_role = State()
    writing_resume = State()

# /start komandasi handler'i
@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    
    # Inline tugmalar
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

# Rol tanlanganda ishlaydigan kod
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

# Botni ishga tushirish (Main)
async def main():
    logging.info("Ishly bot muvaffaqiyatli yondi!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())