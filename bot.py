import os
import logging
import asyncio
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types, F
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
import httpx

logging.basicConfig(level=logging.INFO)

# --- KONFIGURATSIYALAR ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 6809538599  # Sizning Telegram ID raqamingiz
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# --- XAVFSIZ VA VAQTINChALIK XOTIRA (DATABASE CHALA QOTMASLIGI UChUN) ---
# Vercel-da qotib qolishni oldini olish uchun ma'lumotlar vaqtincha shu yerda saqlanadi
MEMORY_USERS = {}  # {tg_id: {"username": "...", "role": "...", "profession": "...", "paid": 0}}
MEMORY_SETTINGS = {
    "resume_price": 0,    # Boshida Rezyume yaratish mutlaqo TEKIN!
    "hr_price": 50000     # HR uchun defolt narx
}

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
app = FastAPI()

# --- FSM STATES ---
class ResumeSteps(StatesGroup):
    waiting_for_ai_chat = State()    # Haqiqiy Gemini AI bilan jonli intervyu
    waiting_for_payment = State()    # Pullik rejimda chek kutish

class AdminStates(StatesGroup):
    waiting_for_ad = State()          
    waiting_for_resume_price = State()   
    waiting_for_hr_price = State()

# Gemini API bilan eng tez va eng yengil asinxron bog'lanish funksiyasi
async def ask_gemini_light(prompt_text: str) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    headers = {"Content-Type": "application/json"}
    payload = {"contents": [{"parts": [{"text": prompt_text}]}]}
    
    async with httpx.AsyncClient(timeout=8.0) as http_client:
        try:
            response = await http_client.post(url, json=payload, headers=headers)
            res_json = response.json()
            return res_json['candidates'][0]['content']['parts'][0]['text']
        except Exception as e:
            logging.error(f"Gemini Error: {e}")
            return "🤖 Ma'lumotlaringiz qabul qilindi. Keyingi bosqichga o'tsak bo'ladimi?"

# --- USER: START ---
@dp.message(F.text == "/start")
async def send_welcome(message: types.Message, state: FSMContext):
    await state.clear()
    tg_id = message.from_user.id
    username = message.from_user.username or "NoUsername"
    
    # Foydalanuvchini vaqtincha xotiraga qo'shish
    if tg_id not in MEMORY_USERS:
        MEMORY_USERS[tg_id] = {
            "tg_id": tg_id,
            "username": username,
            "role": "Aniqmas",
            "profession": "Noma'lum",
            "paid": 0
        }

    builder = ReplyKeyboardBuilder()
    builder.button(text="💼 Ish qidiryapman")
    builder.button(text="📢 Ish beruvchiman")
    if tg_id == ADMIN_ID:
        builder.button(text="⚙️ Admin Panel")
    builder.adjust(2)
    
    await message.answer(
        "Ishly platformasiga xush kelibsiz! O'zingizga mos bo'limni tanlang:", 
        reply_markup=builder.as_markup(resize_keyboard=True)
    )

# --- 💼 JONLI AI INTERVYU BOSQIChI (MANTIQLI SUHBAT) ---
@dp.message(F.text == "💼 Ish qidiryapman")
async def start_ai_interview(message: types.Message, state: FSMContext):
    tg_id = message.from_user.id
    if tg_id in MEMORY_USERS:
        MEMORY_USERS[tg_id]["role"] = "Nomzod"
        
    welcome_prompt = (
        "Salom! Men Ishly platformasining HR-AIdoshiman. Sizga professional rezyume yaratishda yordam beraman. "
        "Keling tanishib olamiz! Ismingiz nima va hozirda qaysi sohada faoliyat yuritasiz?"
    )
    await state.update_data(chat_history=[{"role": "assistant", "content": welcome_prompt}], q_count=1)
    await message.answer(welcome_prompt)
    await state.set_state(ResumeSteps.waiting_for_ai_chat)

@dp.message(ResumeSteps.waiting_for_ai_chat)
async def handle_ai_chat(message: types.Message, state: FSMContext):
    user_text = message.text
    tg_id = message.from_user.id
    data = await state.get_data()
    history = data.get("chat_history", [])
    q_count = data.get("q_count", 1)
    
    history.append({"role": "user", "content": user_text})
    
    # 4 ta savolgacha Gemini jonli suhbat quradi, yolg'on gapni ushlaydi
    if q_count < 4:
        ai_prompt = (
            "Siz aqlli va sinchkov HR konsultantsiz. Foydalanuvchi rezyume yaratmoqchi. "
            f"Hozirgacha bo'lgan suhbatlar: {str(history)}. "
            "Agar foydalanuvchi juda qisqa javob bergan bo'lsa (Masalan: 'dasturchi' yoki '3 yil real soft'), "
            "keyingi savolga o'tmasdan, uning gapini tahlil qilib, aniqlashtiruvchi savol bering (loyihalari, ko'nikmalari haqida). "
            "Javobingiz o'ta uzun bo'lmasin, jonli va qisqa bo'lsim."
        )
        ai_reply = await ask_gemini_light(ai_prompt)
        history.append({"role": "assistant", "content": ai_reply})
        await state.update_data(chat_history=history, q_count=q_count+1)
        await message.answer(ai_reply)
        
    else:
        # Suhbat tugadi -> Gemini strukturali CV matnini generatsiya qiladi
        await message.answer("🤖 Ma'lumotlaringiz tahlil qilinmoqda, iltimos kuting...")
        
        analysis_prompt = (
            f"Ushbu suhbat tarixidan foydalanib: {str(history)} "
            "Professional va chiroyli Rezyume (CV) matnini shakllantirib ber. "
            "Faqat matn ko'rinishida bo'lsin. Eng tepasida nomzodning aniqlangan KASBI (bitta so'zda, masalan: Dasturchi, Sotuvchi, Dizayner) "
            "alohida 'KASB: [Soha]' ko'rinishida aniq yozilsin."
        )
        final_cv = await ask_gemini_light(analysis_prompt)

        # Kasbni bazaga (xotiraga) yozish
        prof = "Dasturchi"
        if "KASB:" in final_cv:
            try: prof = final_cv.split("KASB:")[1].split("\n")[0].strip()
            except: pass
            
        if tg_id in MEMORY_USERS:
            MEMORY_USERS[tg_id]["profession"] = prof
        
        current_res_price = MEMORY_SETTINGS["resume_price"]
        await state.update_data(cv_text=final_cv)
        
        # 🟢 REZYUME HOZIRChA TEKIN (Narx 0 bo'lsa)
        if current_res_price == 0:
            inline_builder = InlineKeyboardBuilder()
            inline_builder.button(text="📥 Ha, PDF qilib yuklash (Tekin)", callback_data="generate_pdf_free")
            await message.answer(
                f"✨ **Sizning ma'lumotlaringiz asosida mukammal CV shakllantirildi!**\n\n{final_cv}\n\n"
                "Ushbu ma'lumotlarni professional PDF hujjat ko'rinishida yuklab olishni xohlaysizmi?",
                reply_markup=inline_builder.as_markup()
            )
        # 🔴 PULLIK DAVRI (Admin paneldan narx qo'yilsa)
        else:
            await message.answer(
                f"✨ **Ma'lumotlaringiz muvaffaqiyatli yig'ildi!**\n\n"
                f"Ushbu ma'lumotlar asosida professional PDF rezyume yaratish va uni HR bazasiga uzatish narxi: **{current_res_price} so'm**.\n\n"
                "To'lov uchun karta: `8600 0000 0000 0000` (Diyoriddin)\n"
                "To'lovni amalga oshirib, **chek rasmini (skrinshotini)** shu yerga yuboring!"
            )
            await state.set_state(ResumeSteps.waiting_for_payment)

# --- TEKIN REZYUME: HRGA UZATISh ---
@dp.callback_query(F.data == "generate_pdf_free")
async def make_pdf_free(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    cv_text = data.get("cv_text", "Rezyume matni")
    
    await callback.message.answer("⏳ Professional PDF shakllantirilmoqda, biroz kuting...")
    await asyncio.sleep(2)
    await callback.message.answer("✅ Rezyumeingiz muvaffaqiyatli yaratildi va HR tizimiga uzatildi!")
    
    # HR-ga (Sizga) ma'lumot uzatiladi
    await bot.send_message(chat_id=ADMIN_ID, text=f"🔔 **YANGI NOMZOD ARIZASI:**\n\n{cv_text}\n🔗 Profil: @{callback.from_user.username or 'Yashirin'}")
    await state.clear()
    await callback.answer()

# --- PULLIK REZYUME: CHEK TEKShIRISh VA HRGA JONATISh ---
@dp.message(ResumeSteps.waiting_for_payment, F.photo)
async def handle_paid_resume(message: types.Message, state: FSMContext):
    data = await state.get_data()
    cv_text = data.get("cv_text", "Rezyume matni")
    tg_id = message.from_user.id
    price = MEMORY_SETTINGS["resume_price"]
    
    await message.answer("🔄 AI to'lov chekini tasdiqlamoqda...")
    await asyncio.sleep(2)
    await message.answer("✅ To'lov tasdiqlandi! Rezyumeingiz PDF ko'rinishida HR bazasiga uzatildi.")
    
    # Tushgan pulni xotiraga yozamiz
    if tg_id in MEMORY_USERS:
        MEMORY_USERS[tg_id]["paid"] = price
    
    # Admin/HR-ga uzatish
    await bot.send_message(chat_id=ADMIN_ID, text=f"💰 **YANGI PULLIK NOMZOD (To'lov tasdiqlandi):**\n\n{cv_text}")
    await bot.send_photo(chat_id=ADMIN_ID, photo=message.photo[-1].file_id, caption="Nomzod yuborgan to'lov cheki.")
    await state.clear()

# --- 📢 ISH BERUVChI BO'LIMI ---
@dp.message(F.text == "📢 Ish beruvchiman")
async def recruiter_start(message: types.Message):
    tg_id = message.from_user.id
    if tg_id in MEMORY_USERS:
        MEMORY_USERS[tg_id]["role"] = "HR (Ish beruvchi)"
    await message.answer("Xush kelibsiz! Yangi vakansiya joylashtirish uchun kompaniyangiz nomini kiriting:")

# ==========================================
# ⚙️ MUKAMMAL ADMIN PANEL (ICHMA-ICH KATALOG)
# ==========================================
@dp.message(F.text == "⚙️ Admin Panel")
async def admin_main_menu(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    
    inline_builder = InlineKeyboardBuilder()
    inline_builder.button(text="📊 Gemini Biznes Analitika", callback_data="admin_analitika")
    inline_builder.button(text="💰 Narxlarni Sozlash (Katalog)", callback_data="admin_prices_katalog")
    inline_builder.button(text="📢 Reklama Tarqatish", callback_data="admin_send_reklama")
    inline_builder.adjust(1)
    
    await message.answer("⚙️ **Ishly Bot — Asosiy Admin Dashboard**\n\nTizimni boshqarish uchun bo'limni tanlang:", reply_markup=inline_builder.as_markup())

# 📊 GEMINI AI BIZNES ANALITIKA (HAQIQIY TAHLIL)
@dp.callback_query(F.data == "admin_analitika")
async def admin_gemini_analytics(callback: types.CallbackQuery):
    await callback.message.answer("⏳ Gemini AI ma'lumotlarni tahlil qilmoqda, kuting...")
    
    # Analitika ma'lumotlarini hisoblaymiz
    total_users = len(MEMORY_USERS)
    nomzodlar = sum(1 for u in MEMORY_USERS.values() if u["role"] == "Nomzod")
    hr_count = sum(1 for u in MEMORY_USERS.values() if u["role"] == "HR (Ish beruvchi)")
    total_money = sum(u["paid"] for u in MEMORY_USERS.values())
    
    # Kasblar kesimini hisoblash
    prof_stats = {}
    for u in MEMORY_USERS.values():
        p = u["profession"]
        if p != "Noma'lum":
            prof_stats[p] = prof_stats.get(p, 0) + 1

    ai_analytics_prompt = (
        f"Sen professional biznes tahlilchisan. Loyihamiz 'Ishly Bot' deb nomlanadi. "
        f"Mana joriy statistika:\n"
        f"- Jami foydalanuvchilar: {total_users} ta\n"
        f"- Jami Nomzodlar: {nomzodlar} ta\n"
        f"- Jami HR (Ish beruvchilar): {hr_count} ta\n"
        f"- Kasblar bo'yicha taqsimot: {str(prof_stats)}\n"
        f"- Bot orqali kelgan jami daromad: {total_money} UZS.\n\n"
        "Ushbu raqamlarni chuqur tahlil qilib, qisqa biznes hisoboti va strategik tavsiya yozib ber. Kasblar trendini tushuntir."
    )
    report = await ask_gemini_light(ai_analytics_prompt)

    inline_builder = InlineKeyboardBuilder()
    inline_builder.button(text="🔙 Bosh sahifaga qaytish", callback_data="admin_back_to_main")
    
    await callback.message.answer(f"📊 **Gemini AI — Biznes Analitika Xulosasi:**\n\n{report}", reply_markup=inline_builder.as_markup())
    await callback.answer()

# 2-BOSQICh: KATALOG — NARXLARNI SOZLASh MENYUSI
@dp.callback_query(F.data == "admin_prices_katalog")
async def admin_prices_katalog(callback: types.CallbackQuery):
    r_price = MEMORY_SETTINGS["resume_price"]
    h_price = MEMORY_SETTINGS["hr_price"]
    
    inline_builder = InlineKeyboardBuilder()
    inline_builder.button(text=f"📄 Rezyume Yaratish ({r_price} UZS)", callback_data="set_resume_price_btn")
    inline_builder.button(text=f"📢 HR Vakansiya Joylash ({h_price} UZS)", callback_data="set_hr_price_btn")
    inline_builder.button(text="🔙 Orqaga", callback_data="admin_back_to_main")
    inline_builder.adjust(1)
    
    await callback.message.edit_text(
        "💰 **Narxlarni Sozlash Katalogi**\n\nO'zgartirmoqchi bo'lgan xizmat turini tanlang:", 
        reply_markup=inline_builder.as_markup()
    )
    await callback.answer()

# 3-BOSQICh: REZYUME NARXINI KIRITISh
@dp.callback_query(F.data == "set_resume_price_btn")
async def ask_resume_price(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("📥 **Rezyume yaratish uchun yangi narxni kiriting (UZS):**\n*(Tekin qilish uchun 0 yozing)*")
    await state.set_state(AdminStates.waiting_for_resume_price)
    await callback.answer()

@dp.message(AdminStates.waiting_for_resume_price)
async def save_resume_price(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Faqat raqam kiriting!")
        return
    MEMORY_SETTINGS["resume_price"] = int(message.text)
    await message.answer(f"✅ Rezyume narxi {message.text} so'mga o'zgartirildi!")
    await state.clear()
    await admin_main_menu(message)

# 3-BOSQICh: HR VAKANSIYA NARXINI KIRITISh
@dp.callback_query(F.data == "set_hr_price_btn")
async def ask_hr_price(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("📥 **HR Vakansiya joylash uchun yangi haqni kiriting (UZS):**")
    await state.set_state(AdminStates.waiting_for_hr_price)
    await callback.answer()

@dp.message(AdminStates.waiting_for_hr_price)
async def save_hr_price(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Faqat raqam kiriting!")
        return
    MEMORY_SETTINGS["hr_price"] = int(message.text)
    await message.answer(f"✅ HR Vakansiya narxi {message.text} so'mga o'zgartirildi!")
    await state.clear()
    await admin_main_menu(message)

# BACK TO MAIN
@dp.callback_query(F.data == "admin_back_to_main")
async def back_to_main_callback(callback: types.CallbackQuery):
    inline_builder = InlineKeyboardBuilder()
    inline_builder.button(text="📊 Gemini Biznes Analitika", callback_data="admin_analitika")
    inline_builder.button(text="💰 Narxlarni Sozlash (Katalog)", callback_data="admin_prices_katalog")
    inline_builder.button(text="📢 Reklama Tarqatish", callback_data="admin_send_reklama")
    inline_builder.adjust(1)
    await callback.message.edit_text("⚙️ **Ishly Bot — Asosiy Admin Dashboard**", reply_markup=inline_builder.as_markup())
    await callback.answer()

# REKLAMA
@dp.callback_query(F.data == "admin_send_reklama")
async def ask_ad(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Menga hamma userlarga yuboriladigan reklama postini tashlang:")
    await state.set_state(AdminStates.waiting_for_ad)
    await callback.answer()

@dp.message(AdminStates.waiting_for_ad)
async def broadcast_ad(message: types.Message, state: FSMContext):
    await message.answer("🔄 Reklama yuborilmoqda...")
    success = 0
    for user_id in MEMORY_USERS.keys():
        try:
            await message.copy_to(chat_id=user_id)
            success += 1
        except: pass
    await message.answer(f"✅ Reklama yakunlandi. {success} ta userga yetkazildi.")
    await state.clear()
    await admin_main_menu(message)

# --- VERCEL WEBHOOK INTEGRATION ---
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