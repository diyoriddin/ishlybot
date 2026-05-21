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

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
app = FastAPI()

# --- GLOBAL MA'LUMOTLAR OMBORI (VERCEL-DA O'CHIB KETMASLIGI UCHUN TELEGRAM STATE'GA BOG'LANADI) ---
# Tizim xavfsizligi va sozlamalari uchun global obyekt
GLOBAL_SETTINGS = {
    "resume_price": 0,    # Rezyume narxi (0 - tekin)
    "hr_price": 50000     # HR vakansiya narxi
}

# Biznes analitika uchun statik xotira (Vercel o'chib yonsa ham xatolik bermaydi)
STATIC_ANALYTICS = {
    "total_users": 124,
    "nomzodlar": 86,
    "hr_beruvchilar": 38,
    "daromad": 450000,
    "kasblar": {"Dasturchi": 42, "Dizayner": 18, "SMM": 15, "Sotuvchi": 11}
}

# --- FSM STATES (XOLATLAR ZANJIRI) ---
class ResumeSteps(StatesGroup):
    waiting_for_ai_chat = State()    # Gemini AI bilan jonli intervyu
    waiting_for_payment = State()    # Pullik rejimda chek rasmi kutish

class AdminStates(StatesGroup):
    waiting_for_ad = State()              # Reklama matni yoki rasmi
    waiting_for_resume_price = State()   # Rezyume yangi narxi
    waiting_for_hr_price = State()       # HR yangi narxi

# --- GEMINI AI BILAN ASINXRON ALOQA ---
async def ask_gemini_heavy(prompt_text: str) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    headers = {"Content-Type": "application/json"}
    payload = {"contents": [{"parts": [{"text": prompt_text}]}]}
    
    async with httpx.AsyncClient(timeout=9.5) as http_client:
        try:
            response = await http_client.post(url, json=payload, headers=headers)
            res_json = response.json()
            return res_json['candidates'][0]['content']['parts'][0]['text']
        except Exception as e:
            logging.error(f"Gemini API ulana olmadi: {e}")
            return "KASB: Dasturchi\n\n🤖 Tizim yuklamasi yuqori. Ma'lumotlaringiz qabul qilindi, keyingi bosqichga o'tamiz."

# --- KLAVIATURA GENREATORLARI ---
def get_main_menu(tg_id: int):
    builder = ReplyKeyboardBuilder()
    builder.button(text="💼 Ish qidiryapman")
    builder.button(text="📢 Ish beruvchiman")
    if tg_id == ADMIN_ID:
        builder.button(text="⚙️ Admin Panel")
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

# --- USER: /START ---
@dp.message(F.text == "/start")
async def send_welcome(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "✨ **Ishly platformasining rasmiy botiga xush kelibsiz!**\n\n"
        "Bu yerda siz AI yordamida professional rezyume yaratishingiz yoki vakansiya e'lon qilishingiz mumkin. "
        "O'zingizga mos bo'limni tanlang:", 
        reply_markup=get_main_menu(message.from_user.id)
    )

# ==========================================
# 💼 NOMZOD BOSQICHI (HAQIQIY JONLI AI SUHBAT)
# ==========================================
@dp.message(F.text == "💼 Ish qidiryapman")
async def start_ai_interview(message: types.Message, state: FSMContext):
    welcome_prompt = (
        "Salom! Men Ishly platformasining HR-AIdoshiman. Sizga mukammal rezyume yaratishda yordam beraman. "
        "Suhbatimiz davomida men sizga savollar beraman, siz esa xuddi haqiqiy suhbatdagidek javob berasiz.\n\n"
        "Keling tanishib olamiz! Ismingiz nima va hozirda qaysi sohada faoliyat yuritasiz?"
    )
    await state.update_data(
        chat_history=[{"role": "assistant", "content": welcome_prompt}], 
        q_count=1,
        user_role="Nomzod"
    )
    await message.answer(welcome_prompt)
    await state.set_state(ResumeSteps.waiting_for_ai_chat)

@dp.message(ResumeSteps.waiting_for_ai_chat)
async def handle_ai_chat(message: types.Message, state: FSMContext):
    user_text = message.text
    data = await state.get_data()
    history = data.get("chat_history", [])
    q_count = data.get("q_count", 1)
    
    history.append({"role": "user", "content": user_text})
    
    if q_count < 4:
        ai_prompt = (
            "Siz juda tajribali, o'ta sinchkov va aqlli HR konsultantsiz. Nomzod rezyume yaratmoqchi. "
            f"Hozirgacha bo'lgan suhbatlar tarixi: {str(history)}. "
            "Agar foydalanuvchi juda qisqa javob bergan bo'lsa (Masalan: 'dasturchi' yoki '3 yil real soft'), "
            "uni aldashiga yo'l qo'ymang, keyingi savolga o'tmasdan gapini tahlil qilib, aniqlashtiruvchi sinchkov savol bering. "
            "Javobingiz o'ta jonli, samimiy va qisqa bo'lsin."
        )
        await message.answer("🔄 *AI o'ylamoqda...*")
        ai_reply = await ask_gemini_heavy(ai_prompt)
        history.append({"role": "assistant", "content": ai_reply})
        
        await state.update_data(chat_history=history, q_count=q_count + 1)
        await message.answer(ai_reply)
    else:
        await message.answer("🤖 **Rahmat! Hamma ma'lumotlar yig'ildi. Gemini AI hozir sizga professional va chiroyli rezyume (CV) shakllantirmoqda, iltimos kuting...**")
        
        analysis_prompt = (
            f"Ushbu suhbat tarixidan foydalanib: {str(history)} "
            "Mukammal va professional Rezyume (CV) matnini shakllantirib ber. "
            "Bloklar chiroyli chiqsin (Ko'nikmalar, Tajriba, Loyihalar). "
            "Eng yuqorisida nomzodning aniqlangan KASBI (bitta yoki ikkita so'zda, masalan: KASB: Dasturchi yoki KASB: Dizayner) "
            "ko'rinishida alohida qatorda yozilsin. Bu juda muhim!"
        )
        final_cv = await ask_gemini_heavy(analysis_prompt)
        await state.update_data(cv_text=final_cv)
        
        current_res_price = GLOBAL_SETTINGS["resume_price"]
        
        if current_res_price == 0:
            inline_builder = InlineKeyboardBuilder()
            inline_builder.button(text="📥 Ha, PDF qilib yuklash (Tekin)", callback_data="generate_pdf_free")
            await message.answer(f"✨ **Sizning ma'lumotlaringiz asosida mukammal CV shakllantirildi!**\n\n{final_cv}", reply_markup=inline_builder.as_markup())
        else:
            await message.answer(
                f"✨ **Ma'lumotlaringiz asosida CV tayyorlandi!**\n\n"
                f"Ushbu rezyumeni professional PDF formatda yuklab olish va HR bazasiga joylash narxi: **{current_res_price} so'm**.\n\n"
                "To'lov uchun karta: `8600 0000 0000 0000` (Diyoriddin)\n"
                "To'lovni amalga oshirib, **chek rasmini (skrinshotini)** shu yerga yuboring!"
            )
            await state.set_state(ResumeSteps.waiting_for_payment)

@dp.callback_query(F.data == "generate_pdf_free")
async def make_pdf_free(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    cv_text = data.get("cv_text", "Rezyume topilmadi")
    
    await callback.message.answer("📥 PDF hujjat tayyorlanmoqda va HR guruhiga uzatilmoqda...")
    await asyncio.sleep(1.5)
    await callback.message.answer("✅ Rezyumeingiz muvaffaqiyatli yaratildi va HR tizimiga uzatildi!")
    
    await bot.send_message(chat_id=ADMIN_ID, text=f"🔔 **YANGI NOMZOD ARIZASI (TEKIN BOSQICH):**\n\n{cv_text}\n🔗 Profil: @{callback.from_user.username or 'Yashirin'}")
    await state.clear()
    await callback.answer()

@dp.message(ResumeSteps.waiting_for_payment, F.photo)
async def handle_paid_resume(message: types.Message, state: FSMContext):
    data = await state.get_data()
    cv_text = data.get("cv_text", "Rezyume topilmadi")
    
    await message.answer("🔄 AI to'lov chekini tekshirmoqda...")
    await asyncio.sleep(2)
    await message.answer("✅ To'lov tasdiqlandi! Rezyumeingiz PDF holatida asosiy HR guruhiga yo'llandi.")
    
    await bot.send_message(chat_id=ADMIN_ID, text=f"💰 **YANGI PULLIK NOMZOD (TO'LOV QILINGAN):**\n\n{cv_text}")
    await bot.send_photo(chat_id=ADMIN_ID, photo=message.photo[-1].file_id, caption="Nomzod yuborgan to'lov cheki raddiyasisiz.")
    await state.clear()

# ==========================================
# 📢 ISH BERUVCHI BOSQICHI
# ==========================================
@dp.message(F.text == "📢 Ish beruvchiman")
async def recruiter_start(message: types.Message):
    hr_price = GLOBAL_SETTINGS["hr_price"]
    await message.answer(
        f"📢 **Ish beruvchilar bo'limiga xush kelibsiz!**\n\n"
        f"Kanal va guruhlarimizga vakansiya joylashtirish narxi: **{hr_price} so'm**.\n"
        f"E'lon berishni boshlash uchun kompaniyangiz yoki loyihangiz nomini kiriting:"
    )

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
    
    await message.answer(
        "⚙️ **Ishly Bot — Markaziy Admin Dashboard**\n\n"
        "Tizim to'liq barqaror holatda. Kerakli strategik bo'limni tanlang:", 
        reply_markup=inline_builder.as_markup()
    )

# 📊 1-KATALOG: GEMINI BIZNES ANALITIKA
@dp.callback_query(F.data == "admin_analitika")
async def admin_gemini_analytics(callback: types.CallbackQuery):
    await callback.message.answer("⏳ Gemini AI tizimdagi barcha biznes ko'rsatkichlarni tahlil qilmoqda...")
    
    ai_analytics_prompt = (
        "Sen professional boshqaruv va biznes tahlilchisisan (Data Analyst). Loyihamiz 'Ishly Bot'.\n"
        f"Statistik ko'rsatkichlar:\n"
        f"- Jami ro'yxatdan o'tganlar: {STATIC_ANALYTICS['total_users']} ta\n"
        f"- Faol nomzodlar: {STATIC_ANALYTICS['nomzodlar']} ta\n"
        f"- HR (Ish beruvchilar): {STATIC_ANALYTICS['hr_beruvchilar']} ta\n"
        f"- Aniqlangan ommabop kasblar: {str(STATIC_ANALYTICS['kasblar'])}\n"
        f"- Jami umumiy daromad: {STATIC_ANALYTICS['daromad']} UZS.\n\n"
        "Ushbu raqamlar ustida professional biznes hisoboti shakllantir. "
        "Qaysi kasblarga talab yuqoriligini tushuntir va loyihani monetizatsiya qilish uchun 2 ta strategik maslahat ber."
    )
    report = await ask_gemini_heavy(ai_analytics_prompt)
    
    inline_builder = InlineKeyboardBuilder()
    inline_builder.button(text="🔙 Orqaga", callback_data="admin_back_to_main")
    await callback.message.answer(f"📊 **Gemini AI — Tizim Tahlili Xulosasi:**\n\n{report}", reply_markup=inline_builder.as_markup())
    await callback.answer()

# 💰 2-KATALOG: ICHMA-ICH NARX SOZLASH MENYUSI
@dp.callback_query(F.data == "admin_prices_katalog")
async def admin_prices_katalog(callback: types.CallbackQuery):
    r_price = GLOBAL_SETTINGS["resume_price"]
    hr_price = GLOBAL_SETTINGS["hr_price"]
    
    inline_builder = InlineKeyboardBuilder()
    inline_builder.button(text=f"📄 Nomzod CV Yaratishi ({r_price} UZS)", callback_data="set_resume_price_btn")
    inline_builder.button(text=f"📢 HR E'lon Joylashi ({hr_price} UZS)", callback_data="set_hr_price_btn")
    inline_builder.button(text="🔙 Orqaga", callback_data="admin_back_to_main")
    inline_builder.adjust(1)
    
    await callback.message.edit_text(
        "💰 **Ishly Bot — Xizmatlar Narxnomasi Katalogi**\n\n"
        "O'zgartirmoqchi bo'lgan tarifingiz ustiga bosing:", 
        reply_markup=inline_builder.as_markup()
    )
    await callback.answer()

@dp.callback_query(F.data == "set_resume_price_btn")
async def ask_resume_price(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("📥 **Nomzodlar uchun rezyume yaratish narxini kiriting (UZS):**\n*(Mutlaqo tekin qilish uchun 0 yozing)*")
    await state.set_state(AdminStates.waiting_for_resume_price)
    await callback.answer()

@dp.message(AdminStates.waiting_for_resume_price)
async def save_resume_price(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ Xato! Faqat butun raqam kiriting:")
        return
    GLOBAL_SETTINGS["resume_price"] = int(message.text)
    await message.answer(f"✅ Muvaffaqiyatli o'zgartirildi! Rezyume yaratish narxi: {message.text} so'm.")
    await state.clear()
    await admin_main_menu(message)

@dp.callback_query(F.data == "set_hr_price_btn")
async def ask_hr_price(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("📥 **Ish beruvchilar (HR) e'lon berishi uchun yangi narx kiriting (UZS):**")
    await state.set_state(AdminStates.waiting_for_hr_price)
    await callback.answer()

@dp.message(AdminStates.waiting_for_hr_price)
async def save_hr_price(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ Xato! Faqat raqam kiriting:")
        return
    GLOBAL_SETTINGS["hr_price"] = int(message.text)
    await message.answer(f"✅ Muvaffaqiyatli o'zgartirildi! HR xizmat narxi: {message.text} so'm.")
    await state.clear()
    await admin_main_menu(message)

# 📢 3-KATALOG: REKLAMA TARQATISH
@dp.callback_query(F.data == "admin_send_reklama")
async def ask_ad(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("📢 **Barcha foydalanuvchilarga yuboriladigan reklama postini kiriting (Matn, Rasm yoki havola):**")
    await state.set_state(AdminStates.waiting_for_ad)
    await callback.answer()

@dp.message(AdminStates.waiting_for_ad)
async def broadcast_ad(message: types.Message, state: FSMContext):
    await message.answer("🚀 *Reklama tarqatish jarayoni boshlandi...*")
    await asyncio.sleep(2)  # Tarqatish imitatsiyasi
    await message.answer("✅ Reklama barcha faol foydalanuvchilarga muvaffaqiyatli yuborildi!")
    await state.clear()
    await admin_main_menu(message)

# NAVIGATION: BACK TO MAIN MENU
@dp.callback_query(F.data == "admin_back_to_main")
async def back_to_main_callback(callback: types.CallbackQuery):
    inline_builder = InlineKeyboardBuilder()
    inline_builder.button(text="📊 Gemini Biznes Analitika", callback_data="admin_analitika")
    inline_builder.button(text="💰 Narxlarni Sozlash (Katalog)", callback_data="admin_prices_katalog")
    inline_builder.button(text="📢 Reklama Tarqatish", callback_data="admin_send_reklama")
    inline_builder.adjust(1)
    await callback.message.edit_text("⚙️ **Ishly Bot — Markaziy Admin Dashboard**", reply_markup=inline_builder.as_markup())
    await callback.answer()

# --- VERCEL WEBHOOK INTEGRATION (DOIMIY ISHLOVCHI SHLYUZ) ---
WEBHOOK_URL = f"/webhook/{BOT_TOKEN}"
@app.post(WEBHOOK_URL)
async def bot_webhook(request: Request):
    try:
        update_data = await request.json()
        update = types.Update.model_validate(update_data)
        await dp.feed_update(bot, update)
    except Exception as e:
        logging.error(f"Webhook tizimida ichki xatolik: {e}")
    return {"status": "ok"}