import logging
import asyncio
import random
import time
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.exceptions import MessageNotModified, Throttled

# --- الإعدادات الأساسية ---
API_TOKEN = '8779896667:AAEqI5DgktCCf9RMYyEQNQp54CngWDSPH34'
BOT_NAME = "𝗬𝗢𝗛𝗔𝗡"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN, parse_mode=types.ParseMode.HTML)
dp = Dispatcher(bot)

# --- قاعدة بيانات مؤقتة (يمكن استبدالها بـ SQLite لاحقاً) ---
class GameData:
    def __init__(self):
        self.active_games = {} # {chat_id: game_instance}
        self.scores = {} # {user_id: points}

db = GameData()

# --- خيارات الأماكن ---
LOCATIONS = [
    "📦 خلف الصناديق", 
    "🌳 تحت الشجرة", 
    "🛋 خلف الأريكة", 
    "🚪 وراء الباب", 
    "🚗 داخل السيارة", 
    "🧺 في سلة الغسيل"
]

# --- منطق اللعبة الرئيسي ---
class HideAndSeek:
    def __init__(self, chat_id):
        self.chat_id = chat_id
        self.is_join_phase = True
        self.players = {} # {user_id: {"name": str, "loc": str}}
        self.seeker_id = None
        self.attempts = 3
        self.start_time = time.time()
        self.join_duration = 180 # 3 دقائق

# --- الدوال المساعدة ---
def get_main_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(InlineKeyboardButton("🙋‍♂️ انضمام للغمضية", callback_data="yohan_join"))
    return keyboard

# --- الأوامر ---
@dp.message_handler(commands=['start', 'help'])
async def send_welcome(message: types.Message):
    welcome_text = (
        f"👤 <b>أنا {BOT_NAME}.. سيد اللعبة.</b>\n\n"
        "مهمتي هي إدارة لعبة الغميضة بينكم بكل عدل وصرامة.\n\n"
        "<b>التعليمات:</b>\n"
        "1️⃣ أرسل /start_hide لبدء التسجيل.\n"
        "2️⃣ لديكم 3 دقائق للانضمام والاختباء في الخاص.\n"
        "3️⃣ سأختار باحثاً عشوائياً لديه 3 محاولات فقط.\n\n"
        "<i>هل أنتم مستعدون؟</i>"
    )
    await message.reply(welcome_text)

@dp.message_handler(commands=['start_hide'])
async def start_game_process(message: types.Message):
    chat_id = message.chat.id
    
    if chat_id in db.active_games:
        return await message.reply(f"❌ <b>{BOT_NAME}:</b> هناك لعبة جارية بالفعل في هذه المجموعة!")

    # إنشاء جلسة لعبة جديدة
    db.active_games[chat_id] = HideAndSeek(chat_id)
    game = db.active_games[chat_id]

    await message.answer(
        f"🎮 <b>تبدأ الآن لعبة جديدة بإشراف {BOT_NAME}!</b>\n"
        "⏳ فترة الانضمام: <b>3 دقائق</b>\n"
        "📢 سأقوم بتذكيركم كل 40 ثانية.",
        reply_markup=get_main_keyboard()
    )

    # حلقة التذكير (3 دقائق = 180 ثانية)
    intervals = [40, 40, 40, 40, 20] 
    for sleep_time in intervals:
        await asyncio.sleep(sleep_time)
        if chat_id not in db.active_games or not game.is_join_phase:
            break
        
        remaining = int(game.join_duration - (time.time() - game.start_time))
        if remaining > 0:
            await bot.send_message(
                chat_id,
                f"⚠️ <b>تذكير من {BOT_NAME}:</b>\n"
                f"المتبقي <b>{remaining} ثانية</b> للانضمام!\n"
                f"عدد اللاعبين الحالي: {len(game.players)}",
                reply_markup=get_main_keyboard()
            )

    await finalize_join_phase(chat_id)

async def finalize_join_phase(chat_id):
    game = db.active_games.get(chat_id)
    if not game or not game.is_join_phase: return

    game.is_join_phase = False
    
    if len(game.players) < 2:
        del db.active_games[chat_id]
        return await bot.send_message(chat_id, f"❌ <b>{BOT_NAME}:</b> تم إلغاء اللعبة بسبب نقص العدد (مطلوب لاعبين على الأقل).")

    # اختيار الباحث
    player_ids = list(game.players.keys())
    game.seeker_id = random.choice(player_ids)
    seeker_info = game.players.pop(game.seeker_id)

    await bot.send_message(
        chat_id,
        f"🏁 <b>انتهى وقت الاختباء!</b>\n\n"
        f"👤 الباحث هو: <a href='tg://user?id={game.seeker_id}'>{seeker_info['name']}</a>\n"
        f"🎯 عدد الأهداف المختبئة: <b>{len(game.players)}</b>\n"
        f"📉 المحاولات المتاحة: <b>3</b>\n\n"
        f"<i>{BOT_NAME} يتمنى للباحث حظاً سعيداً.. ستحتاجه!</i>"
    )
    
    await send_seeker_menu(chat_id)

# --- معالجة التفاعلات (Callbacks) ---
@dp.callback_query_handler(lambda c: c.data == "yohan_join")
async def player_join(callback: types.CallbackQuery):
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id
    
    game = db.active_games.get(chat_id)
    if not game or not game.is_join_phase:
        return await callback.answer("لا توجد فترة انضمام حالياً!", show_alert=True)

    if user_id in game.players:
        return await callback.answer("أنت مسجل بالفعل يا ذكي!", show_alert=True)

    # إرسال خيارات الاختباء في الخاص
    kb = InlineKeyboardMarkup(row_width=2)
    for loc in LOCATIONS:
        kb.insert(InlineKeyboardButton(loc, callback_data=f"hiding_{chat_id}_{loc}"))
    
    try:
        await bot.send_message(user_id, f"👤 <b>{BOT_NAME} يراقبك..</b>\nاختر مكان اختبائك بحذر:", reply_markup=kb)
        game.players[user_id] = {"name": callback.from_user.full_name, "loc": None}
        await callback.answer("تم تسجيلك! تفقد رسائلي في الخاص.")
    except:
        await callback.answer("❌ فشل التواصل! تأكد من تشغيل البوت في الخاص أولاً.", show_alert=True)

@dp.callback_query_handler(lambda c: c.data.startswith("hiding_"))
async def set_player_location(callback: types.CallbackQuery):
    _, chat_id, loc = callback.data.split("_")
    chat_id = int(chat_id)
    user_id = callback.from_user.id

    if chat_id in db.active_games:
        game = db.active_games[chat_id]
        if user_id in game.players:
            game.players[user_id]["loc"] = loc
            await callback.message.edit_text(f"✅ <b>{BOT_NAME}:</b> تم حجبك عن الأنظار {loc}. ابقَ هادئاً!")

async def send_seeker_menu(chat_id):
    game = db.active_games.get(chat_id)
    kb = InlineKeyboardMarkup(row_width=1)
    
    for uid, info in game.players.items():
        kb.add(InlineKeyboardButton(f"البحث عن {info['name']}", callback_data=f"seekuser_{chat_id}_{uid}"))
    
    await bot.send_message(chat_id, f"🔍 <b>{BOT_NAME}:</b> يا باحث، من تظن أنك ستجد أولاً؟", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data.startswith("seekuser_"))
async def seeker_choose_loc(callback: types.CallbackQuery):
    _, chat_id, target_id = callback.data.split("_")
    chat_id, target_id = int(chat_id), int(target_id)
    game = db.active_games.get(chat_id)

    if not game or callback.from_user.id != game.seeker_id:
        return await callback.answer("لست الباحث المختار!")

    kb = InlineKeyboardMarkup(row_width=2)
    for loc in LOCATIONS:
        kb.insert(InlineKeyboardButton(loc, callback_data=f"check_{chat_id}_{target_id}_{loc}"))
    
    await callback.message.edit_text(f"❓ أين يختبئ <b>{game.players[target_id]['name']}</b>؟", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data.startswith("check_"))
async def final_check(callback: types.CallbackQuery):
    _, chat_id, target_id, guessed_loc = callback.data.split("_")
    chat_id, target_id = int(chat_id), int(target_id)
    game = db.active_games.get(chat_id)

    if not game or callback.from_user.id != game.seeker_id: return

    correct_loc = game.players[target_id]["loc"]
    target_name = game.players[target_id]["name"]

    if guessed_loc == correct_loc:
        # نجاح العثور
        del game.players[target_id]
        await bot.send_message(chat_id, f"🎯 <b>{BOT_NAME} يصرخ:</b>\nلقد وجدنا 【 {target_name} 】! كان يرتجف {correct_loc}!")
        
        if not game.players:
            await bot.send_message(chat_id, f"🏆 <b>انتهت اللعبة!</b>\nلقد انتصر الباحث على الجميع. {BOT_NAME} معجب بأدائك.")
            del db.active_games[chat_id]
        else:
            await send_seeker_menu(chat_id)
    else:
        # فشل العثور
        game.attempts -= 1
        if game.attempts <= 0:
            await callback.message.edit_text(f"💀 <b>خسارة مذلة!</b>\nلقد فشلت في العثور عليه. المختبئون فازوا و {BOT_NAME} يسخر منك!")
            del db.active_games[chat_id]
        else:
            await callback.answer(f"خطأ! ❌ بقي لك {game.attempts} محاولات.", show_alert=True)
            await send_seeker_menu(chat_id)

# --- تشغيل البوت ---
if __name__ == '__main__':
    print(f"--- {BOT_NAME} IS ONLINE ---")
    executor.start_polling(dp, skip_updates=True)
