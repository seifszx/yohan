# -*- coding: utf-8 -*-
import logging
import asyncio
import random
import time
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# --- الإعدادات ---
API_TOKEN = '8779896667:AAG4HlM1SZ5ZKaLV8cBYXaZb6uyeUpfb44Q'  # ضع التوكن الخاص بك هنا
BOT_NAME = "𝗬𝗢𝗛𝗔𝗡"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN, parse_mode=types.ParseMode.HTML)
dp = Dispatcher(bot)

# --- إدارة البيانات ---
class GameData:
    def __init__(self):
        self.active_games = {}
        self.seeker_to_group = {}

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

# --- أمر /start ---
@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    if message.chat.type == "private":
        welcome_text = f"👋 <b>مرحباً بك في {BOT_NAME}!</b>\n\n"
        welcome_text += "🎮 <b>لعبة الغمّيضة:</b>\n"
        welcome_text += "يمكنك بدء اللعبة في المجموعات باستخدام الأمر:\n"
        welcome_text += "<code>/start_hide</code>\n\n"
        welcome_text += "📌 <b>ملاحظة:</b> يجب أن تكون في مجموعة لبدء اللعبة.\n\n"
        welcome_text += f"🎲 <b>استعد للمتعة مع {BOT_NAME}!</b>"
        await message.reply(welcome_text)
    else:
        await message.reply(f"👋 مرحباً! لبدء لعبة الغمّيضة استخدم:\n<code>/start_hide</code>")

# --- أمر بدء اللعبة (يجب وضعه قبل أي معالج آخر للكولباك) ---
@dp.message_handler(commands=['start_hide'])
async def start_game(message: types.Message):
    print(f"Received /start_hide from {message.chat.id}")  # للتصحيح
    
    if message.chat.type == "private":
        return await message.reply("❌ عذراً، ابدأ اللعبة داخل مجموعة.")
    
    chat_id = message.chat.id
    print(f"Chat ID: {chat_id}")  # للتصحيح
    
    if chat_id in db.active_games:
        return await message.reply(f"⚠️ <b>{BOT_NAME}:</b> هناك مطاردة جارية بالفعل هنا!")
    
    # التحقق من صلاحيات البوت
    try:
        bot_member = await bot.get_chat_member(chat_id, bot.id)
        if not bot_member.can_send_messages:
            return await message.reply("❌ يرجى منح البوت صلاحية إرسال الرسائل أولاً!")
    except:
        return await message.reply("❌ تأكد من إضافة البوت إلى المجموعة أولاً!")

    db.active_games[chat_id] = HideAndSeek(chat_id, message.chat.title)
    
    kb = InlineKeyboardMarkup().add(InlineKeyboardButton("🙋‍♂️ انضمام للاختباء", callback_data=f"join_{chat_id}"))
    
    await message.answer(
        f"🎮 <b>{BOT_NAME} يستعد للمطاردة..</b>\n"
        f"📍 المكان: <b>{message.chat.title}</b>\n"
        f"⏱️ أمامكم 3 دقائق للاختباء.\n"
        f"📢 اضغط الزر للانضمام!",
        reply_markup=kb
    )
    
    print(f"Game started in {chat_id}")  # للتصحيح

    # حلقة التذكير
    for _ in range(4):
        await asyncio.sleep(40)
        if chat_id not in db.active_games or not db.active_games[chat_id].is_join_phase:
            break
        try:
            await bot.send_message(
                chat_id, 
                f"⏳ <b>{BOT_NAME}:</b> لا يزال هناك متسع للاختباء.. اضغط الزر!\n"
                f"👥 عدد المختبئين حالياً: {len(db.active_games[chat_id].players)}",
                reply_markup=kb
            )
        except:
            pass

    await finalize_phase(chat_id)

# --- معالج للرسائل النصية في الخاص (للتأكد من أن البوت يرد) ---
@dp.message_handler(content_types=['text'])
async def handle_text(message: types.Message):
    if message.chat.type == "private":
        if message.text.startswith('/'):
            # إذا كان الأمر غير معروف
            if message.text not in ['/start', '/start_hide', '/help']:
                await message.reply(
                    f"❓ الأمر <code>{message.text}</code> غير معروف.\n\n"
                    f"🎮 الأوامر المتاحة:\n"
                    f"/start - الترحيب\n"
                    f"/start_hide - بدء اللعبة (في المجموعات)\n"
                    f"/help - المساعدة"
                )

# --- أمر المساعدة ---
@dp.message_handler(commands=['help'])
async def help_command(message: types.Message):
    help_text = f"🎮 <b>مساعدة {BOT_NAME}</b>\n\n"
    help_text += "<b>الأوامر المتاحة:</b>\n"
    help_text += "🔹 <code>/start</code> - عرض معلومات البوت\n"
    help_text += "🔹 <code>/start_hide</code> - بدء لعبة جديدة (في المجموعات)\n"
    help_text += "🔹 <code>/help</code> - عرض هذه المساعدة\n\n"
    help_text += "<b>طريقة اللعب:</b>\n"
    help_text += "1️⃣ أضف البوت إلى مجموعة\n"
    help_text += "2️⃣ ابدأ اللعبة بـ /start_hide في المجموعة\n"
    help_text += "3️⃣ اضغط زر الانضمام واختر مكان اختبائك\n"
    help_text += "4️⃣ انتظر اختيار الباحث\n"
    help_text += "5️⃣ الباحث يحاول اكتشاف الأماكن\n\n"
    help_text += f"✨ <b>استعد للمتعة مع {BOT_NAME}!</b>"
    
    await message.reply(help_text)

# --- باقي الوظائف (كما هي بدون تغيير) ---
async def finalize_phase(chat_id):
    game = db.active_games.get(chat_id)
    if not game or not game.is_join_phase: 
        return

    game.is_join_phase = False
    
    if len(game.players) < 2:
        await bot.send_message(chat_id, f"❌ <b>{BOT_NAME}:</b> الغمّيضة تحتاج لشخصين على الأقل. تم الإلغاء.")
        del db.active_games[chat_id]
        return

    player_ids = list(game.players.keys())
    game.seeker_id = random.choice(player_ids)
    seeker_info = game.players.pop(game.seeker_id)
    
    db.seeker_to_group[game.seeker_id] = chat_id

    await bot.send_message(chat_id, 
        f"🏁 <b>انتهى وقت الاختباء!</b>\n\n"
        f"🔍 الباحث المختار: <a href='tg://user?id={game.seeker_id}'>{seeker_info['name']}</a>\n"
        f"🎯 الأهداف المختبئة: <b>{len(game.players)}</b>\n\n"
        f"📩 <b>يا باحث.. تفقد الخاص الآن، بدأت المهمة!</b>")

    await send_seeker_menu_private(game.seeker_id, chat_id)

@dp.callback_query_handler(lambda c: c.data.startswith("join_"))
async def handle_join(callback: types.CallbackQuery):
    chat_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id
    game = db.active_games.get(chat_id)

    if not game or not game.is_join_phase:
        return await callback.answer("❌ انتهى وقت الانضمام!", show_alert=True)

    if user_id in game.players:
        return await callback.answer("✅ أنت مختبئ بالفعل!", show_alert=True)

    kb = InlineKeyboardMarkup(row_width=2)
    for loc in LOCATIONS:
        kb.insert(InlineKeyboardButton(loc, callback_data=f"h_loc_{chat_id}_{loc}"))

    try:
        await bot.send_message(
            user_id, 
            f"👤 <b>{BOT_NAME}:</b>\n"
            f"📍 أنت الآن في مجموعة <b>{game.chat_title}</b>\n"
            f"🏃 اختر مكان اختبائك:", 
            reply_markup=kb
        )
        game.players[user_id] = {"name": callback.from_user.full_name, "loc": None}
        await callback.answer("✅ تم! اختر مكانك في الخاص.", show_alert=False)
    except Exception as e:
        logging.error(f"Error in handle_join: {e}")
        await callback.answer("❌ فشل! أرسل /start للبوت في الخاص أولاً.", show_alert=True)

@dp.callback_query_handler(lambda c: c.data.startswith("h_loc_"))
async def set_loc(callback: types.CallbackQuery):
    try:
        _, _, chat_id, loc = callback.data.split("_")
        game = db.active_games.get(int(chat_id))
        
        if game and callback.from_user.id in game.players:
            if game.players[callback.from_user.id]["loc"] is None:
                game.players[callback.from_user.id]["loc"] = loc
                await callback.message.edit_text(
                    f"✅ <b>تم الاختباء بنجاح!</b>\n\n"
                    f"📍 مكانك: {loc}\n"
                    f"🤫 لا تتحرك وانتظر بدء المطاردة!"
                )
                await callback.answer("🎯 تم اختيار مكانك!")
            else:
                await callback.answer("⚠️ لقد اخترت مكاناً بالفعل!", show_alert=True)
        else:
            await callback.answer("❌ حدث خطأ!", show_alert=True)
    except Exception as e:
        logging.error(f"Error in set_loc: {e}")
        await callback.answer("❌ حدث خطأ!", show_alert=True)

async def send_seeker_menu_private(seeker_id, chat_id):
    game = db.active_games.get(chat_id)
    if not game: 
        return

    if not game.players:
        await bot.send_message(chat_id, f"🏆 <b>انتهت اللعبة!</b>")
        if chat_id in db.active_games:
            del db.active_games[chat_id]
        return

    kb = InlineKeyboardMarkup(row_width=1)
    for uid, info in game.players.items():
        kb.add(InlineKeyboardButton(
            f"🔍 البحث عن {info['name']}", 
            callback_data=f"s_target_{chat_id}_{uid}"
        ))
    
    await bot.send_message(
        seeker_id, 
        f"🕵️‍♂️ <b>قائمة الأهداف:</b>\n"
        f"🎯 المتبقي: {len(game.players)} لاعب\n"
        f"💪 المحاولات المتبقية: {game.attempts}\n\n"
        f"اختر الهدف:",
        reply_markup=kb
    )

@dp.callback_query_handler(lambda c: c.data.startswith("s_target_"))
async def seeker_pick_loc(callback: types.CallbackQuery):
    try:
        _, _, chat_id, target_id = callback.data.split("_")
        chat_id, target_id = int(chat_id), int(target_id)
        game = db.active_games.get(chat_id)
        
        if not game:
            return await callback.answer("❌ اللعبة انتهت!", show_alert=True)
        
        if target_id not in game.players:
            return await callback.answer("❌ هذا الهدف تم القبض عليه!", show_alert=True)
        
        target_name = game.players[target_id]['name']
        kb = InlineKeyboardMarkup(row_width=2)
        for loc in LOCATIONS:
            kb.insert(InlineKeyboardButton(loc, callback_data=f"s_guess_{chat_id}_{target_id}_{loc}"))
        
        await callback.message.edit_text(
            f"❓ <b>أين يختبئ {target_name}؟</b>",
            reply_markup=kb
        )
    except Exception as e:
        logging.error(f"Error in seeker_pick_loc: {e}")

@dp.callback_query_handler(lambda c: c.data.startswith("s_guess_"))
async def process_seeker_guess(callback: types.CallbackQuery):
    try:
        _, _, chat_id, target_id, guessed_loc = callback.data.split("_")
        chat_id, target_id = int(chat_id), int(target_id)
        game = db.active_games.get(chat_id)
        
        if not game:
            return await callback.answer("❌ اللعبة انتهت!", show_alert=True)
        
        if target_id not in game.players:
            return await callback.answer("❌ هذا الهدف تم القبض عليه!", show_alert=True)

        correct_loc = game.players[target_id]["loc"]
        target_name = game.players[target_id]["name"]

        if guessed_loc == correct_loc:
            await bot.send_message(
                chat_id, 
                f"🎉 <b>{BOT_NAME}:</b>\n"
                f"🔍 أمسك الباحث بـ <b>{target_name}</b>\n"
                f"📍 المكان: {correct_loc}"
            )
            
            del game.players[target_id]
            
            if not game.players:
                await bot.send_message(
                    chat_id, 
                    f"🏆 <b>انتهت اللعبة!</b>\n🎊 فاز الباحث!"
                )
                await callback.message.edit_text("🎉 <b>مبروك!</b>\nأمسكت بجميع المختبئين!")
                if chat_id in db.active_games:
                    del db.active_games[chat_id]
            else:
                await callback.message.answer(f"✅ <b>أحسنت!</b>\nوجدت {target_name}.\n🎯 المتبقي: {len(game.players)} لاعب.")
                await send_seeker_menu_private(callback.from_user.id, chat_id)
        else:
            game.attempts -= 1
            if game.attempts <= 0:
                await bot.send_message(
                    chat_id, 
                    f"💀 <b>خسر الباحث!</b>\n🏆 المختبئون فازوا!"
                )
                await callback.message.edit_text("❌ <b>انتهت محاولاتك!</b>\n😔 لقد خسرت.")
                if chat_id in db.active_games:
                    del db.active_games[chat_id]
            else:
                await callback.answer(
                    f"❌ مكان خاطئ!\n💪 بقي {game.attempts} محاولات.", 
                    show_alert=True
                )
                await send_seeker_menu_private(callback.from_user.id, chat_id)
    except Exception as e:
        logging.error(f"Error in process_seeker_guess: {e}")

if __name__ == '__main__':
    print(f"--- {BOT_NAME} IS RUNNING ---")
    print("✅ البوت يعمل بشكل طبيعي")
    print("📝 الأوامر المتاحة: /start, /start_hide, /help")
    print("💡 تأكد من:")
    print("   1. وضع التوكن الصحيح")
    print("   2. إضافة البوت إلى مجموعة")
    print("   3. البوت لديه صلاحيات إرسال الرسائل")
    executor.start_polling(dp, skip_updates=True)
