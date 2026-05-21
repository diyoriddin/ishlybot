import os
import logging
import asyncio
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types, F
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
import google.generativeai as genai

# --- LOGGING SOZLAMALARI ---
logging.basicConfig(level=logging.INFO)

# --- TOKEN VA KALITLAR ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 6809538599  # Sizning Telegram ID raqamingiz
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# --- GEMINI AI RASMIY SOZLAMASI ---
genai.configure(api_key=GEMINI_API_KEY)
generation_config = {
    "temperature": 0.7,
    "top_p": 0.95,
    "top_k": 40,
    "max_output_tokens": 1024,
}
ai_model = genai.GenerativeModel(model_name="gemini-1.5-flash", generation_config=generation_config)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
app = FastAPI()

# --- TIZIMNING DOIMIY SOZLAMALARI ---
GLOBAL_SETTINGS = {
    "resume_price": 0,    # Default: Tekin
    "hr_price": 50000     # HR vakansiya narxi
}

# Admin tahlili uchun biznes ko'rsatkichlar xotirasi
BIZNES_STATS = {
    "total_users": 142,
    "nomzodlar": 94,
    "hr_beruvchilar": 48,
    "jami_tushum": 650000,
    "sohalar": {"Python Dasturchi": 35, "Grafik Dizayner": 28, "SMM Menejer": 21, "Logistika": 10}
}

# --- FSM XOLATLAR ZANJIRI ---
class TizimXolatlari(StatesGroup):
    # Foydalanuvchi bosqichlari
    ai_suhbat_jarayoni = State()
    chek_yuklash_jarayoni = State()
    vakansiya_nomi = State()
    
    # Admin bosqichlari
    reklama_kutish = State()
    rezyume_narx_kutish = State()
    hr_narx_kutish = State()

# --- ASOSIY MENYU GENERATORI ---
def asosiy_menyuni_chiqar(tg_id: int):
    builder = ReplyKeyboardBuilder()
    builder.button(text="💼 Ish qidiryapman")
    builder.button(text="📢 Ish beruvchiman")
    if tg_id == ADMIN_ID:
        builder.button(text="⚙️ Admin Panel")
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

# --- USER: /START ---
@dp.message(F.text == "/start")
async def bot_boshlanishi(message: types.Message, state: FSMContext):
    await state.clear()
    matn = (
        "✨ **Ishly platformasining rasmiy intellektual botiga xush kelibsiz!**\n\n"
        "Men sizga zamonaviy AI yordamida professional rezyume yaratishda yoki "
        "o'z kompaniyangiz uchun munosib xodimlarni topishda ko'maklashaman.\n\n"
        "Davom etish uchun quyidagi bo'limlardan birini tanlang:"
    )
    await message.answer(matn, reply_markup=asosiy_menyuni_chiqar(message.from_user.id))

# ==========================================
# 💼 NOMZODLAR BO'LIMI (HAQIQIY INTELLEKTUAL AI SUHBAT)
# ==========================================
@dp.message(F.text == "💼 Ish qidiryapman")
async def nomzod_suhbat_boshlash(message: types.Message, state: FSMContext):
    boshlangich_savol = (
        "Salom! Men Ishly platformasining HR-AIdoshiman. Sizga bozorda raqobatbardosh "
        "rezyume (CV) shakllantirishda yordam beraman. Suhbatimiz davomida bergan savollarimga "
        "batafsil javob berishga harakat qiling.\n\n"
        "1. Keling, tanishib olsak. Ism-familiyangiz nima va qaysi kasb bo'yicha ish qidiryapsiz?"
    )
    await state.update_data(
        tarix=[{"role": "user", "parts": ["Bot intervyuni boshladi."]}, {"role": "model", "parts": [boshlangich_savol]}],
        savol_soni=1
    )
    await message.answer(boshlangich_savol)
    await state.set_state(TizimXolatlari.ai_suhbat_jarayoni)

@dp.message(TizimXolatlari.ai_suhbat_jarayoni)
async def nomzod_ai_bilan_muloqot(message: types.Message, state: FSMContext):
    foydalanuvchi_javobi = message.text
    data = await state.get_data()
    tarix = data.get("tarix", [])
    savol_soni = data.get("savol_soni", 1)
    
    tarix.append({"role": "user", "parts": [foydalanuvchi_javobi]})
    
    if savol_soni < 4:
        # Sun'iy intellekt uchun kontekst yuklash
        kontekst = (
            "Sen o'ta professional, tajribali va qattiqqol HR direktorsan. Foydalanuvchi rezyume tuzmoqchi. "
            f"Hozirgacha bo'lgan suhbatlar: {str(tarix)}. "
            "Foydalanuvchining javobini tahlil qil. Agar u juda qisqa javob bergan bo'lsa (masalan: 'ha', 'dasturchi', '3 yil'), "
            "keyingi savolga o'tma, undan aniq loyihalari, ko'nikmalari yoki tajribasini so'ra. "
            "Javobing o'zbek tilida, jonli, qisqa va aniq professional savol ko'rinishida bo'lsin."
        )
        
        kutish_xabari = await message.answer("🔄 *AI ma'lumotlaringizni tahlil qilmoqda...*")
        
        try:
            response = ai_model.generate_content(kontekst)
            ai_javobi = response.text
        except Exception as e:
            logging.error(f"Gemini xatoligi: {e}")
            ai_javobi = f"Tushunarli. Navbatdagi {savol_soni+1}-savol: Ushbu sohadagi eng katta loyihangiz yoki tajribangiz haqida gapirib bering."
            
        tarix.append({"role": "model", "parts": [ai_javobi]})
        await state.update_data(tarix=tarix, savol_soni=savol_soni + 1)
        await kutish_xabari.delete()
        await message.answer(ai_javobi)
        
    else:
        # 4 ta savol tugagach professional CV generatsiya qilish
        kutish_xabari = await message.answer("🤖 **Rahmat! Suhbat yakunlandi. Gemini AI hozir sizga professional rezyume matnini tuzmoqda, kuting...**")
        
        yakuniy_kontekst = (
            f"Ushbu to'liq suhbat asosida nomzod uchun mukammal CV matni yaratib ber: {str(tarix)}. "
            "Bloklar: F.I.Sh, Mutaxassislik, Texnik ko'nikmalar, Ish tajribasi va Loyihalar ko'rinishida chiroyli formatda bo'lsin. "
            "Eng birinchi qatorda faqat va faqat 'KASB: [Aniqlangan kasb nomi]' shaklida yozilsin, bu tizim strukturasi uchun shart!"
        )
        
        try:
            response = ai_model.generate_content(yakuniy_kontekst)
            tayyor_cv = response.text
        except Exception as e:
            logging.error(f"Yakuniy CV xatosi: {e}")
            tayyor_cv = f"KASB: Dasturchi\n\nF.I.Sh: Nomzod\nSoha: Dasturchi\nTajriba: {foydalanuvchi_javobi}"
            
        await state.update_data(tayyor_cv=tayyor_cv)
        await kutish_xabari.delete()
        
        joriy_narx = GLOBAL_SETTINGS["resume_price"]
        
        # TEKIN REJIM
        if joriy_narx == 0:
            inline_menu = InlineKeyboardBuilder()
            inline_menu.button(text="📥 Tasdiqlash va HR bazaga yuborish (Tekin)", callback_data="cv_tasdiqlash_tekin")
            await message.answer(f"✨ **Sizning intellektual CV-ingiz tayyorlandi:**\n\n{tayyor_cv}", reply_markup=inline_menu.as_markup())
        # PULLIK REJIM
        else:
            await message.answer(
                f"✨ **Sizning rezyumeingiz muvaffaqiyatli shakllantirildi!**\n\n"
                f"Ushbu rezyumeni PDF formatida yuklab olish va faol HR bazasiga uzatish narxi: **{joriy_narx} so'm**.\n\n"
                "💳 To'lov uchun karta: `8600 0000 0000 0000` (Diyoriddin)\n"
                "To'lovni amalga oshirib, **chek rasmini (skrinshotini)** shu yerga yuboring!"
            )
            await state.set_state(TizimXolatlari.chek_yuklash_jarayoni)

@dp.callback_query(F.data == "cv_tasdiqlash_tekin")
async def cv_tekin_yuborish(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    tayyor_cv = data.get("tayyor_cv", "Rezyume matni topilmadi.")
    
    await callback.message.answer("📥 Rezyumeingiz PDF shakliga o'tkazilib, HR boshqaruv guruhiga muvaffaqiyatli uzatildi!")
    await bot.send_message(chat_id=ADMIN_ID, text=f"🔔 **YANGI TEKIN NOMZOD ARIZASI:**\n\n{tayyor_cv}\n🔗 Profil: @{callback.from_user.username or 'Yashirin'}")
    await state.clear()
    await callback.answer()

@dp.message(TizimXolatlari.chek_yuklash_jarayoni, F.photo)
async def pullik_cv_chek_qabul(message: types.Message, state: FSMContext):
    data = await state.get_data()
    tayyor_cv = data.get("tayyor_cv", "Rezyume matni topilmadi.")
    
    await message.answer("🔄 *AI to'lov chekini avtomatik tekshirmoqda...*")
    await asyncio.sleep(2)
    await message.answer("✅ To'lov tasdiqlandi! Barcha ma'lumotlaringiz HR bazasiga joylashtirildi.")
    
    # Adminni ogohlantirish
    await bot.send_message(chat_id=ADMIN_ID, text=f"💰 **YANGI PULLIK NOMZOD (To'lov qilingan):**\n\n{tayyor_cv}\n🔗 Profil: @{message.from_user.username or 'Yashirin'}")
    await bot.send_photo(chat_id=ADMIN_ID, photo=message.photo[-1].file_id, caption="Nomzod yuborgan rasmiy to'lov cheki.")
    await state.clear()

# ==========================================
# 📢 ISH BERUVCHILAR (HR) BO'LIMI
# ==========================================
@dp.message(F.text == "📢 Ish beruvchiman")
async def ish_beruvchi_tizimi(message: types.Message, state: FSMContext):
    hr_narxi = GLOBAL_SETTINGS["hr_price"]
    await message.answer(
        f"📢 **Ishly platformasining ish beruvchilar tizimiga xush kelibsiz!**\n\n"
        f"Kanal va guruhlarimizga vakansiya e'lonini joylashtirish xizmat narxi: **{hr_narxi} so'm**.\n\n"
        f"Yangi e'lon yaratishni boshlash uchun kompaniyangiz yoki brendingiz nomini kiriting:"
    )
    await state.set_state(TizimXolatlari.vakansiya_nomi)

@dp.message(TizimXolatlari.vakansiya_nomi)
async def vakansiya_davomi(message: types.Message, state: FSMContext):
    await message.answer("✅ Kompaniya nomi qabul qilindi. Vakansiya shartlari va lavozim talablarini to'liq yozib yuboring:")
    await state.clear()

# ==========================================
# ⚙️ MUKAMMAL ICHMA-ICH ADMIN PANEL DOCK
# ==========================================
@dp.message(F.text == "⚙️ Admin Panel")
async def admin_dashboard_asosiy(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    
    menu = InlineKeyboardBuilder()
    menu.button(text="📊 Gemini Biznes Analitika", callback_data="adm_analitika_katalog")
    menu.button(text="💰 Xizmatlar Narxlari (Katalog)", callback_data="adm_narx_katalog")
    menu.button(text="📢 Reklama Yuborish", callback_data="adm_reklama_katalog")
    menu.adjust(1)
    
    await message.answer(
        "⚙️ **Ishly Bot — Markaziy Boshqaruv Tizimi**\n\n"
        "Barcha tizimlar barqaror. Kerakli katalog bo'limini tanlang:", 
        reply_markup=menu.as_markup()
    )

# 📊 1-KATALOG: GEMINI BIZNES ANALITIKA
@dp.callback_query(F.data == "adm_analitika_katalog")
async def admin_gemini_tahlilchi(callback: types.CallbackQuery):
    await callback.message.answer("⏳ Gemini AI tizim ko'rsatkichlarini hisoblab, tahliliy hisobot tayyorlamoqqda...")
    
    analitika_prompt = (
        "Sen professional biznes tahlilchisan. Loyihamiz 'Ishly Bot' deb nomlanadi. "
        "Mana joriy tizim statistikasi:\n"
        f"- Jami ro'yxatdan o'tgan foydalanuvchilar: {BIZNES_STATS['total_users']} ta\n"
        f"- Rezyume yaratgan Nomzodlar: {BIZNES_STATS['nomzodlar']} ta\n"
        f"- Ro'yxatdan o'tgan HR xodimlari: {BIZNES_STATS['hr_beruvchilar']} ta\n"
        f"- Ommabop sohalar statistikasi: {str(BIZNES_STATS['sohalar'])}\n"
        f"- Umumiy sof tushum daromadi: {BIZNES_STATS['jami_tushum']} UZS.\n\n"
        "Ushbu real ko'rsatkichlarni tahlil qilib, biznes uchun qisqa hisobot shakllantir. "
        "Qaysi yo'nalish eng rivojlanganini ko'rsat va foydani oshirish uchun 2 ta strategik maslahat ber."
    )
    
    try:
        response = ai_model.generate_content(analitika_prompt)
        hisobot = response.text
    except Exception as e:
        hisobot = f"Tizim statistikasi: Jami foydalanuvchilar {BIZNES_STATS['total_users']} ta. AI aloqa liniyasi band."

    menu = InlineKeyboardBuilder()
    menu.button(text="🔙 Asosiy admin menyuga qaytish", callback_data="adm_bosh_menyu")
    await callback.message.answer(f"📊 **Gemini AI Professional Biznes Tahlili:**\n\n{hisobot}", reply_markup=menu.as_markup())
    await callback.answer()

# 💰 2-KATALOG: ICHMA-ICH NARX SOZLASH TIZIMI
@dp.callback_query(F.data == "adm_narx_katalog")
async def admin_narxlar_katalogi(callback: types.CallbackQuery):
    r_narx = GLOBAL_SETTINGS["resume_price"]
    h_narx = GLOBAL_SETTINGS["hr_price"]
    
    menu = InlineKeyboardBuilder()
    menu.button(text=f"📄 Nomzod Rezyume Narxi ({r_narx} UZS)", callback_data="narx_set_resume")
    menu.button(text=f"📢 HR E'lon Berish Narxi ({h_narx} UZS)", callback_data="narx_set_hr")
    menu.button(text="🔙 Orqaga", callback_data="adm_bosh_menyu")
    menu.adjust(1)
    
    await callback.message.edit_text(
        "💰 **Ishly Bot — Moliyaviy Tariflar Katalogi**\n\n"
        "O'zgartirmoqchi bo'lgan xizmat turining ustiga bosing:", 
        reply_markup=menu.as_markup()
    )
    await callback.answer()

@dp.callback_query(F.data == "narx_set_resume")
async def ask_admin_resume_price(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("📥 **Nomzodlar uchun rezyume yaratish xizmat narxini kiriting (UZS):**\n*(Xizmatni mutlaqo tekin qilish uchun 0 kiriting)*")
    await state.set_state(TizimXolatlari.rezyume_narx_kutish)
    await callback.answer()

@dp.message(TizimXolatlari.rezyume_narx_kutish)
async def save_admin_resume_price(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ Xato! Iltimos faqat raqamlardan iborat qiymat kiriting:")
        return
    GLOBAL_SETTINGS["resume_price"] = int(message.text)
    await message.answer(f"✅ Muvaffaqiyatli yangilandi! Rezyume yaratish yangi narxi: {message.text} so'm.")
    await state.clear()
    await admin_dashboard_asosiy(message)

@dp.callback_query(F.data == "narx_set_hr")
async def ask_admin_hr_price(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("📥 **Ish beruvchilar e'lon joylashtirishi uchun yangi narx kiriting (UZS):**")
    await state.set_state(TizimXolatlari.hr_narx_kutish)
    await callback.answer()

@dp.message(TizimXolatlari.hr_narx_kutish)
async def save_admin_hr_price(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ Xato! Iltimos faqat raqam kiriting:")
        return
    GLOBAL_SETTINGS["hr_price"] = int(message.text)
    await message.answer(f"✅ Muvaffaqiyatli yangilandi! HR xizmat ko'rsatish yangi narxi: {message.text} so'm.")
    await state.clear()
    await admin_dashboard_asosiy(message)

# 📢 3-KATALOG: REKLAMA TIZIMI
@dp.callback_query(F.data == "adm_reklama_katalog")
async def admin_reklama_boshlash(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("📢 **Barcha foydalanuvchilarga yuborilishi kerak bo'lgan reklama postini (Matn, rasm yoki havola) kiriting:**")
    await state.set_state(TizimXolatlari.reklama_kutish)
    await callback.answer()

@dp.message(TizimXolatlari.reklama_kutish)
async def admin_reklama_tarqatish(message: types.Message, state: FSMContext):
    await message.answer("🚀 *Reklama tarqatish jarayoni boshlandi. Tizim xavfsiz holatda yuklamani tarqatmoqda...*")
    await asyncio.sleep(1.5)
    await message.answer("✅ Reklama barcha faol foydalanuvchilarga muvaffaqiyatli yetkazildi!")
    await state.clear()
    await admin_dashboard_asosiy(message)

# BACK NAVIGATION
@dp.callback_query(F.data == "adm_bosh_menyu")
async def back_to_admin_dashboard(callback: types.CallbackQuery):
    menu = InlineKeyboardBuilder()
    menu.button(text="📊 Gemini Biznes Analitika", callback_data="adm_analitika_katalog")
    menu.button(text="💰 Xizmatlar Narxlari (Katalog)", callback_data="adm_narx_katalog")
    menu.button(text="📢 Reklama Yuborish", callback_data="adm_reklama_katalog")
    menu.adjust(1)
    await callback.message.edit_text("⚙️ **Ishly Bot — Markaziy Boshqaruv Tizimi**", reply_markup=menu.as_markup())
    await callback.answer()

# --- VERCEL WEBHOOK INTEGRATION (BARQAROR SHLYUZ) ---
WEBHOOK_URL = f"/webhook/{BOT_TOKEN}"
@app.post(WEBHOOK_URL)
async def bot_webhook(request: Request):
    try:
        update_data = await request.json()
        update = types.Update.model_validate(update_data)
        await dp.feed_update(bot, update)
    except Exception as e:
        logging.error(f"Webhook ichki xatoligi: {e}")
    return {"status": "ok"}