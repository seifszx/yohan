import logging
import asyncio
import random
import time
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# --- الإعدادات ---
API_TOKEN = '8779896667:AAG2cKf_clrlmiOnsgiIaaANIbu_d8D04jo'
BOT_NAME = "𝗬𝗢𝗛𝗔𝗡"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN, parse_mode=types.ParseMode.HTML)
dp = Dispatcher(bot)

# --- إدارة البيانات ---
class GameData:
    def __init__(self):
        self.active_games = {}  # {group_chat_id: game_instance}
        self.seeker_to_group = {} # {seeker_user_id: group_chat_id} (لتوجيه البحث للخاص)

db = GameData()

LOCATIONS = ["📦 خلف الصناديق", "🌳 تحت الشجرة", "🛋 خلف الأريكة", "🚪 وراء الباب", "🚗 داخل السيارة", "🧺 في سلة الغسيل"]

class HideAndSeek:
    def __init__(self, chat_id, chat_title):
        self.chat_id = chat_id
        self.chat_title = chat_title
        self.is_join_phase = True
        self.players = {} 
        self.seeker_id = None
        self.attempts = 3
        self.start_time = time.time()
        self.join_duration = 180 

# --- الأوامر ---
@dp.message_handler(commands=['start_hide'])
async def start_game(message: types.Message):
    if message.chat.type == "private":
        return await message.reply("❌ عذراً، ابدأ اللعبة داخل مجموعة.")
    
    chat_id = message.chat.id
    if chat_id in db.active_games:
        return await message.reply(f"⚠️ <b>{BOT_NAME}:</b> هناك مطاردة جارية بالفعل هنا!")

    db.active_games[chat_id] = HideAndSeek(chat_id, message.chat.title)
    
    kb = InlineKeyboardMarkup().add(InlineKeyboardButton("🙋‍♂️ انضمام للاختباء", callback_data=f"join_{chat_id}"))
    
    await message.answer(
        f"👤 <b>{BOT_NAME} يستعد للمطاردة..</b>\n"
        f"المكان: <b>{message.chat.title}</b>\n"
        "أمامكم 3 دقائق للاختباء. سأقوم بإرسال رسائل تذكيرية كل 40 ثانية.",
        reply_markup=kb
    )

    # حلقة التذكير (نفس المنطق السابق)
    for _ in range(4):
        await asyncio.sleep(40)
        if chat_id not in db.active_games or not db.active_games[chat_id].is_join_phase:
            break
        await bot.send_message(chat_id, f"⏳ <b>{BOT_NAME}:</b> لا يزال هناك متسع للاختباء.. اضغط الزر!", reply_markup=kb)

    await finalize_phase(chat_id)

async def finalize_phase(chat_id):
    game = db.active_games.get(chat_id)
    if not game or not game.is_join_phase: return

    game.is_join_phase = False
    if len(game.players) < 2:
        await bot.send_message(chat_id, f"❌ <b>{BOT_NAME}:</b> الغمضية تحتاج لشخصين على الأقل. تم الإلغاء.")
        del db.active_games[chat_id]
        return

    # اختيار الباحث
    player_ids = list(game.players.keys())
    game.seeker_id = random.choice(player_ids)
    seeker_info = game.players.pop(game.seeker_id)
    
    # ربط الباحث بالمجموعة في الخاص
    db.seeker_to_group[game.seeker_id] = chat_id

    await bot.send_message(chat_id, 
        f"🏁 <b>انتهى وقت الاختباء!</b>\n\n"
        f"👤 الباحث المختار: <a href='tg://user?id={game.seeker_id}'>{seeker_info['name']}</a>\n"
        f"🎯 الأهداف: <b>{len(game.players)}</b> لاعبين.\n\n"
        f"📩 <b>يا باحث.. تفقد الخاص الآن، بدأت المهمة!</b>")

    # بدء البحث في الخاص
    await send_seeker_menu_private(game.seeker_id, chat_id)

# --- التفاعل في الخاص والمجموعة ---
@dp.callback_query_handler(lambda c: c.data.startswith("join_"))
async def handle_join(callback: types.CallbackQuery):
    chat_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id
    game = db.active_games.get(chat_id)

    if not game or not game.is_join_phase:
        return await callback.answer("انتهى وقت الانضمام!")

    if user_id in game.players:
        return await callback.answer("أنت مختبئ بالفعل!")

    kb = InlineKeyboardMarkup(row_width=2)
    for loc in LOCATIONS:
        kb.insert(InlineKeyboardButton(loc, callback_data=f"h_loc_{chat_id}_{loc}"))

    try:
        await bot.send_message(user_id, f"👤 <b>{BOT_NAME}:</b> أنت الآن في مجموعة {game.chat_title}.\nاختر مكانك:", reply_markup=kb)
        game.players[user_id] = {"name": callback.from_user.full_name, "loc": None}
        await callback.answer("تم! اختر مكانك في الخاص.")
    except:
        await callback.answer("❌ فشل! أرسل /start للبوت في الخاص أولاً.", show_alert=True)

@dp.callback_query_handler(lambda c: c.data.startswith("h_loc_"))
async def set_loc(callback: types.CallbackQuery):
    _, _, chat_id, loc = callback.data.split("_")
    game = db.active_games.get(int(chat_id))
    if game and callback.from_user.id in game.players:
        game.players[callback.from_user.id]["loc"] = loc
        await callback.message.edit_text(f"✅ تم الاختباء {loc}. لا تتحرك!")

# --- واجهة البحث (في الخاص فقط) ---
async def send_seeker_menu_private(seeker_id, chat_id):
    game = db.active_games.get(chat_id)
    if not game: return

    kb = InlineKeyboardMarkup(row_width=1)
    for uid, info in game.players.items():
        kb.add(InlineKeyboardButton(f"🔍 البحث عن {info['name']}", callback_data=f"s_target_{chat_id}_{uid}"))
    
    await bot.send_message(seeker_id, f"🕵️‍♂️ <b>قائمة الأهداف في {game.chat_title}:</b>\nلديك {game.attempts} محاولات.", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data.startswith("s_target_"))
async def seeker_pick_loc(callback: types.CallbackQuery):
    _, _, chat_id, target_id = callback.data.split("_")
    game = db.active_games.get(int(chat_id))
    if not game: return

    target_name = game.players[int(target_id)]['name']
    kb = InlineKeyboardMarkup(row_width=2)
    for loc in LOCATIONS:
        kb.insert(InlineKeyboardButton(loc, callback_data=f"s_guess_{chat_id}_{target_id}_{loc}"))
    
    await callback.message.edit_text(f"❓ أين يختبئ <b>{target_name}</b>؟", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data.startswith("s_guess_"))
async def process_seeker_guess(callback: types.CallbackQuery):
    _, _, chat_id, target_id, guessed_loc = callback.data.split("_")
    chat_id, target_id = int(chat_id), int(target_id)
    game = db.active_games.get(chat_id)
    if not game: return

    correct_loc = game.players[target_id]["loc"]
    target_name = game.players[target_id]["name"]

    if guessed_loc == correct_loc:
        # إعلان في المجموعة
        await bot.send_message(chat_id, f"📢 <b>{BOT_NAME} يعلن:</b>\nأمسك الباحث بـ 【 {target_name} 】 مختبئاً {correct_loc}!")
        del game.players[target_id]
        
        if not game.players:
            await bot.send_message(chat_id, f"🏆 <b>انتهت اللعبة!</b>\nعثر الباحث على الجميع. <b>{BOT_NAME}</b> يحييكم!")
            await callback.message.edit_text("🎊 فزت! أمسكت بالجميع.")
            del db.active_games[chat_id]
        else:
            await callback.message.answer(f"✅ أحسنت! وجدت {target_name}. استمر..")
            await send_seeker_menu_private(callback.from_user.id, chat_id)
    else:
        game.attempts -= 1
        if game.attempts <= 0:
            await bot.send_message(chat_id, f"💀 <b>خسر الباحث!</b>\nفشل في العثور على الجميع. المختبئون فازوا بمكرهم!")
            await callback.message.edit_text("❌ انتهت محاولاتك.. لقد خسرت المطاردة.")
            del db.active_games[chat_id]
        else:
            await callback.answer(f"مكان خاطئ! بقي {game.attempts} محاولات.", show_alert=True)
            await send_seeker_menu_private(callback.from_user.id, chat_id)

if __name__ == '__main__':
    print(f"--- {BOT_NAME} IS WATCHING ---")
    executor.start_polling(dp, skip_updates=True)
