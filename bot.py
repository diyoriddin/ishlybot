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
import httpx

logging.basicConfig(level=logging.INFO)

# --- CONFIGS ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 6809538599
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# MongoDB Cloud ulanishi (Og'ir yuklamalarsiz global bitta ulanish)
MONGO_URL = "mongodb+srv://ishly_user:ishly777bot@ishlycluster.v6zrk.mongodb.net/?retryWrites=true&w=majority"
client = AsyncIOMotorClient(MONGO_URL)
db = client["ishly_database"]
users_col = db["users"]
settings_col = db["settings"]

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
app = FastAPI()

# --- FSM STATES ---
class ResumeSteps(StatesGroup):
    waiting_for_ai_chat = State()    
    waiting_for_payment = State()    

class AdminStates(StatesGroup):
    waiting_for_ad = State()          
    waiting_for_resume_price = State()   
    waiting_for_hr_price = State()

# Gemini API bilan asinxron va juda yengil bog'lanish funksiyasi
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
            return "Dasturchi"

@app.on_event("startup")
async def on_startup():
    res_price = await settings_col.find_one({"key": "resume_price"})
    if not res_price:
        await settings_col.insert_one({"key": "resume_price", "value": 0})
    hr_price = await settings_col.find_one({"key": "hr_price"})
    if not hr_price:
        await settings_col.insert_one({"key": "hr_price", "value": 50000})

# --- USER: START ---
@dp.message(F.text == "/start")
async def send_welcome(message: types.Message, state: FSMContext):
    await state.clear()
    tg_id = message.from_user.id
    username = message.from_user.username or "NoUsername"
    
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
    
    await message.answer("Ishly platformasiga xush kelibsiz! O'zingizga mos bo'limni tanlang:", reply_markup=builder.as_markup(resize_keyboard=True))

# --- JONLI AI INTERVYU ---
@dp.message(F.text == "💼 Ish qidiryapman")
async def start_ai_interview(message: types.Message, state: FSMContext):
    await users_col.update_one({"tg_id": message.from_user.id}, {"$set": {"role": "Nomzod"}})
    welcome_prompt = "Salom! Men Ishly platformasining HR-AIdoshiman. Keling tanishib olamiz! Ismingiz nima va hozirda qaysi sohada faoliyat yuritasiz?"
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
    
    if q_count < 4:
        ai_prompt = (
            "Siz aqlli HR konsultantsiz. Foydalanuvchi rezyume yaratmoqchi. "
            f"Hozirgacha bo'lgan suhbatlar: {str(history)}. "
            "Agar foydalanuvchi juda qisqa javob bergan bo'lsa (Masalan: 'dasturchi' yoki '3 yil real soft'), "
            "keyingi savolga o'tmasdan, uning gapini tahlil qilib, aniqlashtiruvchi savol bering. "
            "Javobingiz jonli va qisqa bo'lsin."
        )
        ai_reply = await ask_gemini_light(ai_prompt)
        history.append({"role": "assistant", "content": ai_reply})
        await state.update_data(chat_history=history, q_count=q_count+1)
        await message.answer(ai_reply)
    else:
        await message.answer("🤖 Ma'lumotlaringiz tahlil qilinmoqda, iltimos kuting...")
        analysis_prompt = (
            f"Ushbu suhbat tarixidan foydalanib: {str(history)} "
            "Professional Rezyume (CV) matnini shakllantirib ber. "
            "Eng tepasida nomzodning aniqlangan KASBI (bitta so'zda, masalan: Dasturchi, Sotuvchi, Dizayner) "
            "alohida 'KASB: [Soha]' ko'rinishida yozilsin."
        )
        final_cv = await ask_gemini_light(analysis_prompt)

        prof = "Dasturchi"
        if "KASB:" in final_cv:
            try: prof = final_cv.split("KASB:")[1].split("\n")[0].strip()
            except: pass
        await users_col.update_one({"tg_id": message.from_user.id}, {"$set": {"profession": prof}})
        
        res_price_doc = await settings_col.find_one({"key": "resume_price"})
        current_res_price = res_price_doc["value"] if res_price_doc else 0
        await state.update_data(cv_text=final_cv)
        
        if current_res_price == 0:
            inline_builder = InlineKeyboardBuilder()
            inline_builder.button(text="📥 Ha, PDF qilib yuklash (Tekin)", callback_data="generate_pdf_free")
            await message.answer(f"✨ **Sizning ma'lumotlaringiz asosida mukammal CV shakllantirildi!**\n\n{final_cv}", reply_markup=inline_builder.as_markup())
        else:
            await message.answer(
                f"✨ **Ma'lumotlaringiz yig'ildi!**\n\nPDF rezyume yaratish narxi: **{current_res_price} so'm**.\n"
                "To'lov uchun karta: `8600 0000 0000 0000` (Diyoriddin)\nChek rasmini shu yerga yuboring!"
            )
            await state.set_state(ResumeSteps.waiting_for_payment)

@dp.callback_query(F.data == "generate_pdf_free")
async def make_pdf_free(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    cv_text = data.get("cv_text", "Rezyume")
    await callback.message.answer("✅ Rezyumeingiz muvaffaqiyatli yaratildi va HR tizimiga uzatildi!")
    await bot.send_message(chat_id=ADMIN_ID, text=f"🔔 **YANGI ARIZA:**\n\n{cv_text}\n🔗 Profil: @{callback.from_user.username or 'Yashirin'}")
    await state.clear()
    await callback.answer()

@dp.message(ResumeSteps.waiting_for_payment, F.photo)
async def handle_paid_resume(message: types.Message, state: FSMContext):
    data = await state.get_data()
    cv_text = data.get("cv_text", "Rezyume")
    res_price_doc = await settings_col.find_one({"key": "resume_price"})
    price = res_price_doc["value"] if res_price_doc else 0
    
    await message.answer("✅ To'lov tasdiqlandi! Rezyumeingiz HR bazasiga uzatildi.")
    await users_col.update_one({"tg_id": message.from_user.id}, {"$set": {"paid": price}})
    await bot.send_message(chat_id=ADMIN_ID, text=f"💰 **PULLIK NOMZOD:**\n\n{cv_text}")
    await bot.send_photo(chat_id=ADMIN_ID, photo=message.photo[-1].file_id, caption="To'lov cheki.")
    await state.clear()

@dp.message(F.text == "📢 Ish beruvchiman")
async def recruiter_start(message: types.Message):
    await users_col.update_one({"tg_id": message.from_user.id}, {"$set": {"role": "HR (Ish beruvchi)"}})
    await message.answer("Xush kelibsiz! Kompaniyangiz nomini kiriting:")

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
    await message.answer("⚙️ **Ishly Bot — Asosiy Admin Dashboard**", reply_markup=inline_builder.as_markup())

@dp.callback_query(F.data == "admin_analitika")
async def admin_gemini_analytics(callback: types.CallbackQuery):
    await callback.message.answer("⏳ Gemini AI ma'lumotlarni tahlil qilmoqda...")
    
    total_users = await users_col.count_documents({})
    nomzodlar = await users_col.count_documents({"role": "Nomzod"})
    hr_count = await users_col.count_documents({"role": "HR (Ish beruvchi)"})
    
    pipeline = [{"$group": {"_id": "$profession", "count": {"$sum": 1}}}]
    prof_cursor = users_col.aggregate(pipeline)
    prof_stats = {}
    async_docs = []
    async for doc in prof_cursor:
        if doc["_id"] != "Noma'lum": prof_stats[doc["_id"]] = doc["count"]
            
    money_pipeline = [{"$group": {"_id": None, "total": {"$sum": "$paid"}}}]
    money_cursor = users_col.aggregate(money_pipeline)
    total_money = 0
    async for doc in money_cursor: total_money = doc["total"]

    ai_analytics_prompt = (
        f"Sen biznes tahlilchisan. Loyihamiz 'Ishly Bot'. Statistika:\n"
        f"- Jami userlar: {total_users} ta\n- Nomzodlar: {nomzodlar} ta\n- HRlar: {hr_count} ta\n"
        f"- Kasblar: {str(prof_stats)}\n- Jami daromad: {total_money} UZS.\n"
        "Ushbu raqamlarni tahlil qilib, qisqa biznes hisoboti va strategik tavsiya yozib ber."
    )
    report = await ask_gemini_light(ai_analytics_prompt)
    
    inline_builder = InlineKeyboardBuilder()
    inline_builder.button(text="🔙 Orqaga", callback_data="admin_back_to_main")
    await callback.message.answer(f"📊 **Gemini AI Analitika Xulosasi:**\n\n{report}", reply_markup=inline_builder.as_markup())
    await callback.answer()

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
    await callback.message.edit_text("💰 **Narxlarni Sozlash Katalogi**", reply_markup=inline_builder.as_markup())
    await callback.answer()

@dp.callback_query(F.data == "set_resume_price_btn")
async def ask_resume_price(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("📥 **Rezyume yaratish uchun yangi narxni kiriting (UZS):**")
    await state.set_state(AdminStates.waiting_for_resume_price)
    await callback.answer()

@dp.message(AdminStates.waiting_for_resume_price)
async def save_resume_price(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): return
    new_p = int(message.text)
    await settings_col.update_one({"key": "resume_price"}, {"$set": {"value": new_p}}, upsert=True)
    await message.answer(f"✅ Rezyume narxi {new_p} so'mga o'zgartirildi!")
    await state.clear()
    await admin_main_menu(message)

@dp.callback_query(F.data == "set_hr_price_btn")
async def ask_hr_price(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("📥 **HR Vakansiya haqini kiriting (UZS):**")
    await state.set_state(AdminStates.waiting_for_hr_price)
    await callback.answer()

@dp.message(AdminStates.waiting_for_hr_price)
async def save_hr_price(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): return
    new_p = int(message.text)
    await settings_col.update_one({"key": "hr_price"}, {"$set": {"value": new_p}}, upsert=True)
    await message.answer(f"✅ HR Vakansiya narxi {new_p} so'mga o'zgartirildi!")
    await state.clear()
    await admin_main_menu(message)

@dp.callback_query(F.data == "admin_back_to_main")
async def back_to_main_callback(callback: types.CallbackQuery):
    inline_builder = InlineKeyboardBuilder()
    inline_builder.button(text="📊 Gemini Biznes Analitika", callback_data="admin_analitika")
    inline_builder.button(text="💰 Narxlarni Sozlash (Katalog)", callback_data="admin_prices_katalog")
    inline_builder.button(text="📢 Reklama Tarqatish", callback_data="admin_send_reklama")
    inline_builder.adjust(1)
    await callback.message.edit_text("⚙️ **Ishly Bot — Asosiy Admin Dashboard**", reply_markup=inline_builder.as_markup())
    await callback.answer()

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
    await message.answer(f"✅ Reklama {success} ta userga yetkazildi.")
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