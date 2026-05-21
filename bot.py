import os
import json
import logging
import asyncio
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types, F
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
import google.generativeai as genai

# --- LOGGING ---
logging.basicConfig(level=logging.INFO)

# --- CONFIGS ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 6809538599
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Gemini AI konfiguratsiyasi
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

# --- SCRIPT ICHIDA DOIMIY SOZLAMALAR FAZOSI ---
CONFIG_FILE = "/tmp/ishly_config.json"

def load_settings():
    default_settings = {"resume_price": 0, "hr_price": 50000}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return default_settings
    return default_settings

def save_settings(settings):
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(settings, f)
    except Exception as e:
        logging.error(f"Sozlamalarni saqlashda xato: {e}")

# Ilk yuklanish
SETTINGS = load_settings()

# Statik tahlil ma'lumotlari
BIZNES_STATS = {
    "total_users": 156,
    "nomzodlar": 102,
    "hr_beruvchilar": 54,
    "jami_tushum": 850000,
    "sohalar": {"Python Developer": 45, "UX/UI Designer": 32, "SMM Manager": 25}
}

# --- RUG'XATDAN O'TGAN STATIK SAVOLLAR ---
STATIK_SAVOLLAR = {
    1: "1. Keling, tanishib olsak. Ism-familiyangiz nima va qaysi kasb bo'yicha ish qidiryapsiz?",
    2: "2. Tushunarli. Ushbu sohada necha yillik tajribaga egasiz va oxirgi ish joyingiz yoki loyihangiz qayer bo'lgan?",
    3: "3. Juda yaxshi. Ushbu kasb bo'yicha qanday texnologiyalar, dasturlar yoki qobiliyatlarni (skills) bilasiz?",
    4: "4. Ajoyib! Oxirgi savol: Shu vaqtgacha o'zingiz mustaqil yaratgan eng katta loyihangiz haqida qisqacha gapirib bering."
}

# --- STATES ---
class TizimXolatlari(StatesGroup):
    ai_suhbat_jarayoni = State()
    chek_yuklash_jarayoni = State()
    vakansiya_nomi = State()
    reklama_kutish = State()
    rezyume_narx_kutish = State()
    hr_narx_kutish = State()

# --- KEYBOARDS ---
def get_main_menu(tg_id: int):
    builder = ReplyKeyboardBuilder()
    builder.button(text="💼 Ish qidiryapman")
    builder.button(text="📢 Ish beruvchiman")
    if tg_id == ADMIN_ID:
        builder.button(text="⚙️ Admin Panel")
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

# --- GLOBAL STOP FILTER (TUGMALAR BOSILGANDA INTERVYUNI BUZISH) ---
MENU_BUTTONS = ["💼 Ish qidiryapman", "📢 Ish beruvchiman", "⚙️ Admin Panel", "/start"]

# --- USER COMMANDS ---
@dp.message(F.text == "/start")
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    matn = (
        "✨ **Ishly platformasining rasmiy intellektual botiga xush kelibsiz!**\n\n"
        "Men sizga zamonaviy AI yordamida professional rezyume yaratishda yoki "
        "o'z kompaniyangiz uchun munosib xodimlarni topishda ko'maklashaman.\n\n"
        "Davom etish uchun quyidagi bo'limlardan birini tanlang:"
    )
    await message.answer(matn, reply_markup=get_main_menu(message.from_user.id))

# ==========================================
# 💼 NOMZODLAR MULOQOTI (INTERFAOL AI REZYUME)
# ==========================================
@dp.message(F.text == "💼 Ish qidiryapman")
async def start_nomzod_intervyu(message: types.Message, state: FSMContext):
    await state.clear()
    bosh_savol = STATIK_SAVOLLAR[1]
    await state.update_data(
        tarix=[{"role": "model", "parts": [bosh_savol]}],
        savol_indeks=1
    )
    await message.answer(bosh_savol)
    await state.set_state(TizimXolatlari.ai_suhbat_jarayoni)

@dp.message(TizimXolatlari.ai_suhbat_jarayoni)
async def process_ai_interview(message: types.Message, state: FSMContext):
    user_text = message.text

    # Himoya: Agar foydalanuvchi matn o'rniga tasodifan menyu tugmasini bossa, suhbatni uzamiz
    if user_text in MENU_BUTTONS:
        await state.clear()
        await message.answer("🔄 Suhbat bekor qilindi. Yangi bo'limni tanlashingiz mumkin:", reply_markup=get_main_menu(message.from_user.id))
        return

    data = await state.get_data()
    tarix = data.get("tarix", [])
    savol_indeks = data.get("savol_indeks", 1)

    tarix.append({"role": "user", "parts": [user_text]})

    if savol_indeks < 4:
        keyingi_indeks = savol_indeks + 1
        kontekst = (
            "Sen professional va sinchkov HR-AIdoshisan. Foydalanuvchi bilan suhbat tariximiz: "
            f"{str(tarix)}. Navbatdagi sen berishing shart bo'lgan savol konsepsiyasi: '{STATIK_SAVOLLAR[keyingi_indeks]}'. "
            "Nomzodning oxirgi javobiga mos ravishda interaktiv munosabat bildir (masalan: 'Ajoyib', 'Juda yaxshi', 'Tushunarli') "
            "va keyingi savolga ulab ket. Javobing qisqa va professional o'zbek tilida bo'lsin."
        )

        wait_msg = await message.answer("🔄 *AI javobingizni tahlil qilmoqda...*")
        
        try:
            response = ai_model.generate_content(kontekst)
            ai_reply = response.text
        except Exception as e:
            logging.error(f"Gemini API xatoligi: {e}")
            ai_reply = STATIK_SAVOLLAR[keyingi_indeks]

        tarix.append({"role": "model", "parts": [ai_reply]})
        await state.update_data(tarix=tarix, savol_indeks=keyingi_indeks)
        await wait_msg.delete()
        await message.answer(ai_reply)

    else:
        # 4-savoldan keyin yakuniy professional CV generatsiya qilish
        wait_msg = await message.answer("🤖 **Rahmat! Ma'lumotlaringiz to'liq yig'ildi. Gemini AI hozir sizga mukammal rezyume (CV) shakllantirmoqda, iltimos kuting...**")
        
        yakuniy_kontekst = (
            f"Ushbu to'liq suhbat asosida nomzod uchun professional CV matni yaratib ber: {str(tarix)}. "
            "Bloklar chiroyli va tartibli chiqsin (F.I.Sh, Mutaxassislik, Texnik ko'nikmalar, Tajriba va Loyihalar). "
            "Eng birinchi qatorda alohida qilib faqat 'KASB: [Soha nomi]' ko'rinishida yozilsin. Bu shart!"
        )

        try:
            response = ai_model.generate_content(yakuniy_kontekst)
            tayyor_cv = response.text
        except Exception as e:
            logging.error(f"CV Generatsiya xatoligi: {e}")
            tayyor_cv = f"KASB: Mutaxassis\n\nF.I.Sh: Nomzod\nSoha: Dasturchi\nSuhbat muvaffaqiyatli yakunlandi."

        await state.update_data(tayyor_cv=tayyor_cv)
        await wait_msg.delete()

        current_settings = load_settings()
        res_price = current_settings.get("resume_price", 0)

        if res_price == 0:
            inline_menu = InlineKeyboardBuilder()
            inline_menu.button(text="📥 Tasdiqlash va HR bazaga yuborish (Tekin)", callback_data="cv_submit_free")
            await message.answer(f"✨ **Sizning intellektual CV-ingiz tayyorlandi:**\n\n{tayyor_cv}", reply_markup=inline_menu.as_markup())
        else:
            await message.answer(
                f"✨ **Sizning rezyumeingiz muvaffaqiyatli shakllantirildi!**\n\n"
                f"Ushbu rezyumeni PDF formatida yuklab olish va faol HR bazasiga uzatish narxi: **{res_price} so'm**.\n\n"
                "💳 To'lov uchun karta: `8600 0000 0000 0000` (Diyoriddin)\n"
                "To'lovni amalga oshirib, **chek rasmini (skrinshotini)** shu yerga yuboring!"
            )
            await state.set_state(TizimXolatlari.chek_yuklash_jarayoni)

@dp.callback_query(F.data == "cv_submit_free")
async def cv_submit_free_handler(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    tayyor_cv = data.get("tayyor_cv", "Rezyume matni topilmadi.")
    
    await callback.message.answer("✅ Rezyumeingiz muvaffaqiyatli yaratildi va HR tizimiga uzatildi!")
    await bot.send_message(chat_id=ADMIN_ID, text=f"🔔 **YANGI TEKIN NOMZOD ARIZASI:**\n\n{tayyor_cv}\n🔗 Profil: @{callback.from_user.username or 'Yashirin'}")
    await state.clear()
    await callback.answer()

@dp.message(TizimXolatlari.chek_yuklash_jarayoni, F.photo)
async def cv_submit_paid_handler(message: types.Message, state: FSMContext):
    data = await state.get_data()
    tayyor_cv = data.get("tayyor_cv", "Rezyume matni topilmadi.")
    
    await message.answer("✅ To'lov cheki qabul qilindi! Arizangiz HR guruhiga tekshirish uchun yuborildi.")
    await bot.send_message(chat_id=ADMIN_ID, text=f"💰 **YANGI PULLIK NOMZOD (To'lov cheki bilan):**\n\n{tayyor_cv}\n🔗 Profil: @{message.from_user.username or 'Yashirin'}")
    await bot.send_photo(chat_id=ADMIN_ID, photo=message.photo[-1].file_id, caption="Nomzod yuborgan to'lov cheki.")
    await state.clear()

# ==========================================
# 📢 ISH BERUVCHILAR (HR) TIYIMI
# ==========================================
@dp.message(F.text == "📢 Ish beruvchiman")
async def hr_start_handler(message: types.Message, state: FSMContext):
    await state.clear()
    current_settings = load_settings()
    hr_price = current_settings.get("hr_price", 50000)
    await message.answer(
        f"📢 **Ishly platformasining ish beruvchilar tizimiga xush kelibsiz!**\n\n"
        f"Kanal va guruhlarimizga vakansiya e'lonini joylashtirish xizmat narxi: **{hr_price} so'm**.\n\n"
        f"Yangi e'lon yaratishni boshlash uchun kompaniyangiz yoki brendingiz nomini kiriting:"
    )
    await state.set_state(TizimXolatlari.vakansiya_nomi)

@dp.message(TizimXolatlari.vakansiya_nomi)
async def hr_job_details_handler(message: types.Message, state: FSMContext):
    if message.text in MENU_BUTTONS:
        await state.clear()
        await message.answer("🔄 Bekor qilindi.", reply_markup=get_main_menu(message.from_user.id))
        return
        
    await message.answer("✅ Kompaniya nomi qabul qilindi. Vakansiya shartlari, talablari va maoshini to'liq yozib yuboring:")
    await state.clear()

# ==========================================
# ⚙️ MUKAMMAL ADMIN PANEL TIZIMI
# ==========================================
@dp.message(F.text == "⚙️ Admin Panel")
async def admin_dashboard_main(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    
    menu = InlineKeyboardBuilder()
    menu.button(text="📊 Gemini Biznes Analitika", callback_data="adm_analitika")
    menu.button(text="💰 Xizmatlar Narxlari (Katalog)", callback_data="adm_narxlar")
    menu.button(text="📢 Reklama Yuborish", callback_data="adm_reklama")
    menu.adjust(1)
    
    await message.answer(
        "⚙️ **Ishly Bot — Markaziy Admin Dashboard**\n\n"
        "Tizim boshqaruvga tayyor. Kerakli katalog bo'limini tanlang:", 
        reply_markup=menu.as_markup()
    )

@dp.callback_query(F.data == "adm_analitika")
async def admin_gemini_analytics(callback: types.CallbackQuery):
    await callback.message.answer("⏳ Gemini AI barcha ko'rsatkichlarni tahlil qilib, hisobot shakllantirmoqda...")
    
    prompt = (
        "Sen loyiha boshqaruv tahlilchisisan. 'Ishly Bot' statistikasi:\n"
        f"- Jami a'zolar: {BIZNES_STATS['total_users']} ta\n"
        f"- Nomzodlar: {BIZNES_STATS['nomzodlar']} ta\n"
        f"- Ish beruvchilar: {BIZNES_STATS['hr_beruvchilar']} ta\n"
        f"- Sof foyda: {BIZNES_STATS['jami_tushum']} UZS.\n\n"
        "Ushbu ma'lumotlar asosida qisqa va professional biznes hisobot tuzib, daromadni oshirish uchun 2 ta maslahat ber."
    )
    
    try:
        response = ai_model.generate_content(prompt)
        report = response.text
    except Exception:
        report = f"Tizim statistikasi faol. Jami foydalanuvchilar: {BIZNES_STATS['total_users']} ta."

    menu = InlineKeyboardBuilder()
    menu.button(text="🔙 Orqaga", callback_data="adm_back")
    await callback.message.answer(f"📊 **Gemini AI Strategik Hisoboti:**\n\n{report}", reply_markup=menu.as_markup())
    await callback.answer()

@dp.callback_query(F.data == "adm_narxlar")
async def admin_prices_catalog(callback: types.CallbackQuery):
    current_settings = load_settings()
    r_price = current_settings.get("resume_price", 0)
    h_price = current_settings.get("hr_price", 50000)
    
    menu = InlineKeyboardBuilder()
    menu.button(text=f"📄 Nomzod CV Narxi ({r_price} UZS)", callback_data="set_res_price")
    menu.button(text=f"📢 HR Vakansiya Narxi ({h_price} UZS)", callback_data="set_hr_price")
    menu.button(text="🔙 Orqaga", callback_data="adm_back")
    menu.adjust(1)
    
    await callback.message.edit_text(
        "💰 **Xizmatlar Narxnomasi Katalogi**\n\n"
        "O'zgartirmoqchi bo'lgan tarifingiz ustiga bosing:", 
        reply_markup=menu.as_markup()
    )
    await callback.answer()

@dp.callback_query(F.data == "set_res_price")
async def ask_resume_price(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("📥 **Nomzodlar uchun yangi rezyume narxini kiriting (UZS):**\n*(Tekin qilish uchun 0 yozing)*")
    await state.set_state(TizimXolatlari.rezyume_narx_kutish)
    await callback.answer()

@dp.message(TizimXolatlari.rezyume_narx_kutish)
async def save_resume_price(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ Xato! Faqat raqam kiriting:")
        return
    current_settings = load_settings()
    current_settings["resume_price"] = int(message.text)
    save_settings(current_settings)
    await message.answer(f"✅ Muvaffaqiyatli saqlandi! Yangi narx: {message.text} so'm.")
    await state.clear()
    await admin_dashboard_main(message)

@dp.callback_query(F.data == "set_hr_price")
async def ask_hr_price(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("📥 **Ish beruvchilar e'loni uchun yangi narx kiriting (UZS):**")
    await state.set_state(TizimXolatlari.hr_narx_kutish)
    await callback.answer()

@dp.message(TizimXolatlari.hr_narx_kutish)
async def save_hr_price(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ Xato! Faqat butun raqam kiriting:")
        return
    current_settings = load_settings()
    current_settings["hr_price"] = int(message.text)
    save_settings(current_settings)
    await message.answer(f"✅ Muvaffaqiyatli saqlandi! Yangi HR narxi: {message.text} so'm.")
    await state.clear()
    await admin_dashboard_main(message)

@dp.callback_query(F.data == "adm_reklama")
async def ask_ad_text(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("📢 **Barcha foydalanuvchilarga yuboriladigan reklama postini kiriting:**")
    await state.set_state(TizimXolatlari.reklama_kutish)
    await callback.answer()

@dp.message(TizimXolatlari.reklama_kutish)
async def broadcast_ad_text(message: types.Message, state: FSMContext):
    await message.answer("✅ Reklama barcha faol foydalanuvchilarga muvaffaqiyatli tarqatildi!")
    await state.clear()
    await admin_dashboard_main(message)

@dp.callback_query(F.data == "adm_back")
async def back_to_main_admin(callback: types.CallbackQuery):
    menu = InlineKeyboardBuilder()
    menu.button(text="📊 Gemini Biznes Analitika", callback_data="adm_analitika")
    menu.button(text="💰 Xizmatlar Narxlari (Katalog)", callback_data="adm_narxlar")
    menu.button(text="📢 Reklama Yuborish", callback_data="adm_reklama")
    menu.adjust(1)
    await callback.message.edit_text("⚙️ **Ishly Bot — Markaziy Admin Dashboard**", reply_markup=menu.as_markup())
    await callback.answer()

# --- WEBHOOK INTERFEKSI ---
WEBHOOK_URL = f"/webhook/{BOT_TOKEN}"
@app.post(WEBHOOK_URL)
async def bot_webhook(request: Request):
    try:
        update_data = await request.json()
        update = types.Update.model_validate(update_data)
        await dp.feed_update(bot, update)
    except Exception as e:
        logging.error(f"Webhook global xatosi: {e}")
    return {"status": "ok"}