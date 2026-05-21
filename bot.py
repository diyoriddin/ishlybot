import os
import logging
import asyncio
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types, F
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 6809538599  # Sizning (HR/Admin) Telegram ID-ingiz

# BIZNES MANTIQ PARAMETRLARI
CURRENT_PRICE = 0  # 💡 BOShIDA REZYUME YARATISh HOZIRChA TEKIN!
ACTIVE_USERS = {6809538599}

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
app = FastAPI()

# --- REZYUME YARATISh BOSQIChLARI ---
class ResumeSteps(StatesGroup):
    waiting_for_name = State()       
    waiting_for_job = State()        
    waiting_for_exp = State()        
    waiting_for_payment = State()    

class AdminStates(StatesGroup):
    waiting_for_ad = State()          
    waiting_for_new_price = State()   

# --- USER: START ---
@dp.message(F.text == "/start")
async def send_welcome(message: types.Message, state: FSMContext):
    await state.clear()
    tg_id = message.from_user.id
    ACTIVE_USERS.add(tg_id)

    builder = ReplyKeyboardBuilder()
    builder.button(text="💼 Ish qidiryapman")
    builder.button(text="📢 Ish beruvchiman")
    if tg_id == ADMIN_ID:
        builder.button(text="⚙️ Admin Panel")
    builder.adjust(2)
    
    await message.answer(
        "Ishly Botga xush kelibsiz! O'zingizga mos bo'limni tanlang:", 
        reply_markup=builder.as_markup(resize_keyboard=True)
    )

# --- 💼 AI INTERVYU BOSQIChI ---
@dp.message(F.text == "💼 Ish qidiryapman")
async def start_interview(message: types.Message, state: FSMContext):
    await message.answer("Ajoyib! AI yordamida rezyumeingizni shakllantirishni boshlaymiz.\n\n"
                         "1️⃣ **Ismingiz va familiyangizni kiriting:**")
    await state.set_state(ResumeSteps.waiting_for_name)

@dp.message(ResumeSteps.waiting_for_name)
async def process_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("🤖 Tizim qabul qildi. \n\n2️⃣ **Mutaxassisligingiz yoki qidirayotgan lavozimingizni yozing:**")
    await state.set_state(ResumeSteps.waiting_for_job)

@dp.message(ResumeSteps.waiting_for_job)
async def process_job(message: types.Message, state: FSMContext):
    await state.update_data(job=message.text)
    await message.answer("🤖 Yaxshi. \n\n3️⃣ **Ish tajribangiz haqida batafsil yozing (Kompaniya nomi, davri):**")
    await state.set_state(ResumeSteps.waiting_for_exp)

# --- 🔥 DINAMIK NARX VA HRGA UZATISh ---
@dp.message(ResumeSteps.waiting_for_exp)
async def process_exp(message: types.Message, state: FSMContext):
    await state.update_data(exp=message.text)
    user_data = await state.get_data()
    
    global CURRENT_PRICE
    
    # Ma'lumotlarni yig'ib tayyor ko'rinishga keltiramiz
    resume_text = (
        "📝 **YANGI REZYUME (AI tomonidan shakllantirildi):**\n\n"
        f"👤 **F.I.Sh:** {user_data['name']}\n"
        f"🎯 **Soha/Lavozim:** {user_data['job']}\n"
        f"⏳ **Ish tajribasi:** {user_data['exp']}\n"
        f"🔗 **Foydalanuvchi profili:** @{message.from_user.username or 'Yashirin'}"
    )
    
    # 1-Holat: Agar narx 0 bo'lsa (Tekin davri) -> Ma'lumotlarni SRAZU HRga uzatadi!
    if CURRENT_PRICE == 0:
        await message.answer("✅ Rezyumeingiz muvaffaqiyatli tayyorlandi va ko'rib chiqish uchun **HR bazasiga uzatildi!** Yaqin orada siz bilan bog'lanishadi.")
        
        # HR/Admin-ga (Sizga) ma'lumotlarni yuborish
        await bot.send_message(chat_id=ADMIN_ID, text=f"🔔 **Yangi nomzod ariza topshirdi!**\n\n{resume_text}")
        await state.clear()
        
    # 2-Holat: Agar keyinchalik Admin paneldan narx belgilasangiz -> To'lov so'raydi!
    else:
        await state.update_data(final_resume=resume_text) # Rezyumeni saqlab turamiz
        await message.answer(
            f"📄 Rezyumeingiz tayyorlandi. Uni faollashtirish va HR bazasiga uzatish narxi: **{CURRENT_PRICE} so'm**.\n\n"
            "To'lovni amalga oshirish uchun quyidagi kartaga pul o'tkazing:\n"
            "💳 Karta: `8600 0000 0000 0000` (Diyoriddin)\n\n"
            "To'lovni bajargach, **chek rasmini** shu yerga yuboring. AI uni tekshirib, rezyumeni HRga uzatadi!"
        )
        await state.set_state(ResumeSteps.waiting_for_payment)

# --- PULLIK BO'LGANDA CHEKNI QABUL QILISH VA HRGA UZATISh ---
@dp.message(ResumeSteps.waiting_for_payment, F.photo)
async def handle_payment(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    
    await message.answer("🔄 Chek qabul qilindi. AI to'lovni tasdiqlamoqda...")
    await asyncio.sleep(2)
    await message.answer("✅ To'lov tasdiqlandi! Rezyumeingiz rasman **HR bazasiga uzatildi**.")
    
    # Admin/HR-ga ham rezyumeni, ham chekni yuboradi
    await bot.send_message(chat_id=ADMIN_ID, text=f"💰 **Yangi pullik ariza (To'lov tasdiqlandi):**\n\n{user_data['final_resume']}")
    await bot.send_photo(chat_id=ADMIN_ID, photo=message.photo[-1].file_id, caption="Foydalanuvchi yuborgan to'lov cheki.")
    
    await state.clear()

# --- 📢 ISH BERUVChI BO'LIMI ---
@dp.message(F.text == "📢 Ish beruvchiman")
async def recruiter_start(message: types.Message):
    await message.answer("Xush kelibsiz! Yangi vakansiya joylashtirish uchun kompaniyangiz nomini kiriting:")

# --- ⚙️ ADMIN PANEL (NARXNI NAZORAT QILISh VA REKLAMA) ---
@dp.message(F.text == "⚙️ Admin Panel")
async def admin_panel(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    global CURRENT_PRICE
    user_count = len(ACTIVE_USERS)
    
    inline_builder = InlineKeyboardBuilder()
    inline_builder.button(text=f"💰 Narxni o'zgartirish ({CURRENT_PRICE} so'm)", callback_data="admin_change_price")
    inline_builder.button(text="📢 Reklama (Post) yuborish", callback_data="admin_send_ad")
    inline_builder.adjust(1)

    status_text = "Hozircha TEKIN (0 UZS)" if CURRENT_PRICE == 0 else f"{CURRENT_PRICE} so'm"

    await message.answer(
        f"📊 **Ishly Bot Rasmiy Admin Paneli**\n\n"
        f"👥 Jami faol foydalanuvchilar: {user_count} ta\n"
        f"💵 Amaldagi rezyume narxi: {status_text}",
        reply_markup=inline_builder.as_markup()
    )

@dp.callback_query(F.data == "admin_send_ad")
async def admin_ad_prompt(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Menga hamma foydalanuvchilarga yuboriladigan reklama postini tashlang:")
    await state.set_state(AdminStates.waiting_for_ad)
    await callback.answer()

@dp.message(AdminStates.waiting_for_ad)
async def admin_broadcast_ad(message: types.Message, state: FSMContext):
    await message.answer("🔄 Reklama hamma userlarga tarqatilmoqda...")
    success = 0
    for user_id in list(ACTIVE_USERS):
        try:
            await message.copy_to(chat_id=user_id)
            success += 1
        except Exception:
            pass
    await message.answer(f"✅ Reklama yakunlandi. {success} ta userga yetkazildi.")
    await state.clear()

@dp.callback_query(F.data == "admin_change_price")
async def admin_price_prompt(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Yangi narxni kiriting (Agar yana tekin qilmoqchi bo'lsangiz 0 kiriting):")
    await state.set_state(AdminStates.waiting_for_new_price)
    await callback.answer()

@dp.message(AdminStates.waiting_for_new_price)
async def admin_save_price(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Faqat raqam kiriting!")
        return
    global CURRENT_PRICE
    CURRENT_PRICE = int(message.text)
    await message.answer(f"✅ Rezyume narxi muvaffaqiyatli yangilandi: {CURRENT_PRICE} so'm!")
    await state.clear()

# --- VERCEL CONFIGS ---
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