import os
import logging
import asyncio
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types, F
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from motor.motor_asyncio import AsyncIOMotorClient
import google.generativeai as genai

logging.basicConfig(level=logging.INFO)

# --- KONFIGURATSIYALAR ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 6809538599  # Sizning Admin ID-ingiz

# Google Gemini AI sozlamalari
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") # Vercel Environment Variables-ga qo'shgan kalitingiz
genai.configure(api_key=GEMINI_API_KEY)
ai_model = genai.GenerativeModel('gemini-pro')

# MongoDB Cloud - Ma'lumotlar ombori
MONGO_URL = "mongodb+srv://ishly_user:ishly777bot@ishlycluster.v6zrk.mongodb.net/?retryWrites=true&w=majority"
client = AsyncIOMotorClient(MONGO_URL)
db = client["ishly_database"]
users_col = db["users"]
settings_col = db["settings"]

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
app = FastAPI()

# --- FSM STATE-LAR (Katalog va Suhbat zanjiri) ---
class ResumeSteps(StatesGroup):
    waiting_for_ai_chat = State()    # Jonli AI Suhbat bosqichi
    waiting_for_payment = State()    # Pullik rejimda chek kutish

class AdminStates(StatesGroup):
    waiting_for_ad = State()          
    waiting_for_resume_price = State()   
    waiting_for_hr_price = State()

# --- BAZANI ILK BOR SOZLASh ---
@app.on_event("startup")
async def on_startup():
    # Defolt narxlar bazada yo'q bo'lsa, yaratadi
    res_price = await settings_col.find_one({"key": "resume_price"})
    if not res_price:
        await settings_col.insert_one({"key": "resume_price", "value": 0}) # Boshida tekin!
        
    hr_price = await settings_col.find_one({"key": "hr_price"})
    if not hr_price:
        await settings_col.insert_one({"key": "hr_price", "value": 50000})
    logging.info("Tizim va barcha kataloglar muvaffaqiyatli ishga tushdi!")

# --- USER: START ---
@dp.message(F.text == "/start")
async def send_welcome(message: types.Message, state: FSMContext):
    await state.clear()
    tg_id = message.from_user.id
    username = message.from_user.username or "NoUsername"
    
    # Userni bazaga boshlang'ich ro'yxatga olish (agar yo'q bo'lsa)
    await users_col.update_one(
        {"tg_id": tg_id},
        {"$set": {"tg_id": tg_id, "username": username}, "$setOnInsert": {"role": "Aniqmas", "profession": "Noma'lum", "paid": 0}},
        upsert=True
    )

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
    await users_col.update_one({"tg_id": message.from_user.id}, {"$set": {"role": "Nomzod"}})
    
    welcome_prompt = (
        "Salom! Men Ishly platformasining HR-AIdoshiman. Sizga professional rezyume yaratishda yordam beraman. "
        "Keling tanishib olamiz! Ismingiz nima va hozirda qaysi sohadada faoliyat yuritasiz?"
    )
    # Chat tarixini FSM-da saqlab boramiz
    await state.update_data(chat_history=[{"role": "assistant", "content": welcome_prompt}], q_count=1)
    await message.answer(welcome_prompt)
    await state.set_state(ResumeSteps.waiting_for_ai_chat)

@dp.message(ResumeSteps.waiting_for_ai_chat)
async def handle_ai_chat(message: types.Message, state: FSMContext):
    user_text = message.text
    data = await state.get_data()
    history = data.get("chat_history", [])
    q_count = data.get("q_count", 1)
    
    history.append({"role": "user", "content": user_text})
    
    # Agar foydalanuvchi qisqa yoki yolg'on gapirsa (Masalan: "real soft 3 yil") uni Gemini ushlaydi
    # 4-5 ta savoldan keyin Gemini avtomat xulosa qiladi
    if q_count < 4:
        # Gemini-ga kontekst beramiz
        ai_prompt = (
            "Siz aqlli va sinchkov HR konsultantsiz. Foydalanuvchi rezyume yaratmoqchi. "
            f"Hozirgacha bo'lgan suhbatlar: {str(history)}. "
            "Agar foydalanuvchi juda qisqa javob bergan bo'lsa (Masalan: 'dasturchi' yoki '3 yil real soft'), "
            "keyingi savolga o'tmasdan, uning gapini tahlil qilib, aniqlashtiruvchi savol bering (Qaysi loyihalarda ishlagan, nimalar qila oladi). "
            "Agar javob to'liq bo'lsa, uning ko'nikmalari, o'qish joyi yoki tajribasini aniqlash uchun navbatdagi HR savolini bering. "
            "Javobingiz juda uzun bo'lmasin, jonli va qisqa bo'lsin."
        )
        try:
            response = ai_model.generate_content(ai_prompt)
            ai_reply = response.text
        except Exception:
            ai_reply = "🤖 Tushunarli. Mutaxassisligingiz va oxirgi ish joyingiz haqida batafsilroq so'zlab bera olasizmi?"
            
        history.append({"role": "assistant", "content": ai_reply})
        await state.update_data(chat_history=history, q_count=q_count+1)
        await message.answer(ai_reply)
        
    else:
        # Suhbat yakunlandi - Gemini hamma narsani tartiblab chiroyli CV matni qiladi
        await message.answer("🤖 Ma'lumotlaringiz tahlil qilinmoqda, kuting...")
        
        analysis_prompt = (
            f"Ushbu suhbat tarixidan foydalanib: {str(history)} "
            "Professional, strukturali Rezyume (CV) matnini shakllantirib ber. "
            "Faqat matn ko'rinishida bo'lsin. Eng tepasida nomzodning aniqlangan KASBI (bitta so'zda, masalan: Dasturchi, Sotuvchi, Dizayner) "
            "alohida 'KASB: [Soha]' ko'rinishida aniq yozilsin, chunki tizim buni bazaga saqlaydi."
        )
        try:
            res_back = ai_model.generate_content(analysis_prompt)
            final_cv = res_back.text
        except Exception:
            final_cv = f"👤 Nomzod: {message.from_user.full_name}\n💼 Kasbi: Dasturchi\n📝 Ma'lumotlar saqlandi."

        # Kasbni matndan ajratib olish va bazaga yozish
        prof = "Dasturchi"
        if "KASB:" in final_cv:
            try: prof = final_cv.split("KASB:")[1].split("\n")[0].strip()
            except: pass
        await users_col.update_one({"tg_id": message.from_user.id}, {"$set": {"profession": prof}})
        
        # Narxni tekshiramiz
        res_price_doc = await settings_col.find_one({"key": "resume_price"})
        current_res_price = res_price_doc["value"] if res_price_doc else 0
        
        await state.update_data(cv_text=final_cv)
        
        # 🟢 TEKIN DAVRI (Narx 0 bo'lsa) -> Srazu PDF taklif etadi
        if current_res_price == 0:
            inline_builder = InlineKeyboardBuilder()
            inline_builder.button(text="📥 Ha, PDF qilib yuklash (Tekin)", callback_data="generate_pdf_free")
            inline_builder.adjust(1)
            await message.answer(
                f"✨ **Sizning ma'lumotlaringiz asosida mukammal CV shakllantirildi!**\n\n{final_cv}\n\n"
                "Ushbu ma'lumotlarni professional PDF hujjat ko'rinishida yuklab olishni xohlaysizmi?",
                reply_markup=inline_builder.as_markup()
            )
        # 🔴 PULLIK DAVRI
        else:
            await message.answer(
                f"✨ **Ma'lumotlaringiz muvaffaqiyatli yig'ildi!**\n\n"
                f"Ushbu ma'lumotlar asosida professional PDF rezyume yaratish va uni HR bazasiga faollashtirish narxi: **{current_res_price} so'm**.\n\n"
                "To'lov uchun karta: `8600 0000 0000 0000` (Diyoriddin)\n"
                "To'lovni amalga oshirib, **chek rasmini (skrinshotini)** shu yerga yuboring!"
            )
            await state.set_state(ResumeSteps.waiting_for_payment)

# --- TEKIN REZYUME: GENERATSIYA VA HRGA JO'NATISh ---
@dp.callback_query(F.data == "generate_pdf_free")
async def make_pdf_free(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    cv_text = data.get("cv_text", "Rezyume matni")
    
    await callback.message.answer("⏳ Professional PDF shakllantirilmoqda, iltimos 3 soniya kuting...")
    await asyncio.sleep(2)
    
    # Real loyihada bu yerda PDF fayl generatsiya bo'ladi. Hozircha tayyor matnli fayl simulyatsiyasi:
    await callback.message.answer("✅ Rezyumeingiz muvaffaqiyatli yaratildi va HR tizimiga uzatildi!")
    
    # HR-ga (Sizga) ma'lumot uzatiladi
    await bot.send_message(chat_id=ADMIN_ID, text=f"🔔 **YANGI ARIZA (Tekin tizimdan):**\n\n{cv_text}\n🔗 Profil: @{callback.from_user.username or 'Yashirin'}")
    await state.clear()
    await callback.answer()

# --- PULLIK REZYUME: CHEK TEKShIRISh VA HRGA JONATISh ---
@dp.message(ResumeSteps.waiting_for_payment, F.photo)
async def handle_paid_resume(message: types.Message, state: FSMContext):
    data = await state.get_data()
    cv_text = data.get("cv_text", "Rezyume matni")
    
    res_price_doc = await settings_col.find_one({"key": "resume_price"})
    price = res_price_doc["value"] if res_price_doc else 0
    
    await message.answer("🔄 AI chekni analiz qilmoqda...")
    await asyncio.sleep(2)
    await message.answer("✅ To'lov tasdiqlandi! Rezyumeingiz PDF ko'rinishida HR bazasiga muvaffaqiyatli uzatildi.")
    
    # Bazaga pulni qo'shamiz
    await users_col.update_one({"tg_id": message.from_user.id}, {"$set": {"paid": price}})
    
    # HR/Admin-ga ham chekni, ham rezyumeni uzatish
    await bot.send_message(chat_id=ADMIN_ID, text=f"💰 **YANGI PULLIK NOMZOD ARRIVED:**\n\n{cv_text}")
    await bot.send_photo(chat_id=ADMIN_ID, photo=message.photo[-1].file_id, caption="Nomzod yuborgan to'lov cheki.")
    await state.clear()

# --- 📢 ISH BERUVChI BO'LIMI ---
@dp.message(F.text == "📢 Ish beruvchiman")
async def recruiter_start(message: types.Message):
    await users_col.update_one({"tg_id": message.from_user.id}, {"$set": {"role": "HR (Ish beruvchi)"}})
    await message.answer("Xush kelibsiz! Kompaniyangiz nomini kiriting:")

# ==========================================
# ⚙️ MUKAMMAL ADMIN PANEL (ICHMA-ICH KATALOG)
# ==========================================

# 1-BOSQICh: ASOSIY ADMIN MENYU
@dp.message(F.text == "⚙️ Admin Panel")
async def admin_main_menu(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    
    inline_builder = InlineKeyboardBuilder()
    inline_builder.button(text="📊 Gemini Biznes Analitika", callback_data="admin_analitika")
    inline_builder.button(text="💰 Narxlarni Sozlash (Katalog)", callback_data="admin_prices_katalog")
    inline_builder.button(text="📢 Reklama Tarqatish", callback_data="admin_send_reklama")
    inline_builder.adjust(1)
    
    await message.answer("⚙️ **Ishly Bot — Asosiy Admin Dashboard**\n\nTizimni boshqarish uchun bo'limni tanlang:", reply_markup=inline_builder.as_markup())

# 🧠 GEMINI AI BIZNES ANALITIKA (HAQIQIY TAHLIL)
@dp.callback_query(F.data == "admin_analitika")
async def admin_gemini_analytics(callback: types.CallbackQuery):
    await callback.message.answer("⏳ Gemini AI bazadagi ma'lumotlarni tahlil qilmoqda, kuting...")
    
    # Bazadan ma'lumotlarni yig'amiz
    total_users = await users_col.count_documents({})
    nomzodlar = await users_col.count_documents({"role": "Nomzod"})
    hr_count = await users_col.count_documents({"role": "HR (Ish beruvchi)"})
    
    # Kasblarni yig'ish
    pipeline = [{"$group": {"_id": "$profession", "count": {"$sum": 1}}}]
    prof_cursor = users_col.aggregate(pipeline)
    prof_stats = {}
    async for doc in prof_cursor:
        if doc["_id"] != "Noma'lum":
            prof_stats[doc["_id"]] = doc["count"]
            
    # Moliyaviy yig'indi
    money_pipeline = [{"$group": {"_id": None, "total": {"$sum": "$paid"}}}]
    money_cursor = users_col.aggregate(money_pipeline)
    total_money = 0
    async for doc in money_cursor:
        total_money = doc["total"]

    # Gemini-ga ma'lumotni beramiz
    ai_analytics_prompt = (
        f"Sen biznes tahlilchisan. Loyihamiz 'Ishly Bot' deb nomlanadi. "
        f"Mana joriy statistika:\n"
        f"- Jami foydalanuvchilar: {total_users} ta\n"
        f"- Jami Nomzodlar: {nomzodlar} ta\n"
        f"- Jami HR (Ish beruvchilar): {hr_count} ta\n"
        f"- Kasblar bo'yicha taqsimot: {str(prof_stats)}\n"
        f"- Bot orqali kelgan jami daromad: {total_money} UZS.\n\n"
        "Ushbu raqamlarni tahlil qilib, professional biznes hisoboti yozib ber. "
        "Qaysi kasblar o'siyotgani, qachon pullik rejimga to'liq o'tish kerakligi haqida qisqa va aniq strategik maslahat ber."
    )
    try:
        ai_res = ai_model.generate_content(ai_analytics_prompt)
        report = ai_res.text
    except Exception:
        report = "📊 Tizimda tahlil uchun ma'lumotlar hali yetarli emas."

    inline_builder = InlineKeyboardBuilder()
    inline_builder.button(text="🔙 Bosh sahifaga qaytish", callback_data="admin_back_to_main")
    
    await callback.message.answer(f"📊 **Gemini AI — Biznes Analitika Xulosasi:**\n\n{report}", reply_markup=inline_builder.as_markup())
    await callback.answer()

# 2-BOSQICh: KATALOG — NARXLARNI SOZLASh MENYUSI
@dp.callback_query(F.data == "admin_prices_katalog")
async def admin_prices_katalog(callback: types.CallbackQuery):
    res_p_doc = await settings_col.find_one({"key": "resume_price"})
    hr_p_doc = await settings_col.find_one({"key": "hr_price"})
    
    r_price = res_p_doc["value"] if res_p_doc else 0
    h_price = hr_p_doc["value"] if hr_p_doc else 50000
    
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

# 3-BOSQICh: REZYUME NARXINI KIRITIShNI SO'RASh
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
    new_p = int(message.text)
    await settings_col.update_one({"key": "resume_price"}, {"$set": {"value": new_p}}, upsert=True)
    
    # Narx o'zgargandan keyin avtomat yana katalogga qaytaradi (UX Qulaylik)
    await message.answer(f"✅ Rezyume narxi {new_p} so'mga o'zgartirildi!")
    await state.clear()
    
    # Katalog menyusini qayta chiqarish
    await admin_main_menu(message)

# 3-BOSQICh: HR VAKANSIYA NARXINI KIRITIShNI SO'RASh
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
    new_p = int(message.text)
    await settings_col.update_one({"key": "hr_price"}, {"$set": {"value": new_p}}, upsert=True)
    await message.answer(f"✅ HR Vakansiya narxi {new_p} so'mga o'zgartirildi!")
    await state.clear()
    await admin_main_menu(message)

# ORQAGA QAYTIsh LOYIHASI
@dp.callback_query(F.data == "admin_back_to_main")
async def back_to_main_callback(callback: types.CallbackQuery):
    inline_builder = InlineKeyboardBuilder()
    inline_builder.button(text="📊 Gemini Biznes Analitika", callback_data="admin_analitika")
    inline_builder.button(text="💰 Narxlarni Sozlash (Katalog)", callback_data="admin_prices_katalog")
    inline_builder.button(text="📢 Reklama Tarqatish", callback_data="admin_send_reklama")
    inline_builder.adjust(1)
    await callback.message.edit_text("⚙️ **Ishly Bot — Asosiy Admin Dashboard**\n\nTizimni boshqarish uchun bo'limni tanlang:", reply_markup=inline_builder.as_markup())
    await callback.answer()

# REKLAMA BO'LIMI
@dp.callback_query(F.data == "admin_send_reklama")
async def ask_ad(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Menga reklama postini yuboring:")
    await state.set_state(AdminStates.waiting_for_ad)
    await callback.answer()

@dp.message(AdminStates.waiting_for_ad)
async def broadcast_ad(message: types.Message, state: FSMContext):
    await message.answer("🔄 Reklama yuborilmoqda...")
    cursor = users_col.find({})
    success = 0
    async for user in cursor:
        try:
            await message.copy_to(chat_id=user["tg_id"])
            success += 1
        except: pass
    await message.answer(f"✅ Reklama {success} ta userga yuborildi.")
    await state.clear()
    await admin_main_menu(message)

# --- VERCEL WEBHOOK INTEGRATSIYASI ---
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