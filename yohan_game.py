import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode
import json
import os

# تفعيل التسجيل
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

TOKEN = '8779896667:AAEwivan1ZXUI_Y5qt5eoBiu1uW7lCTN6B8'

# هيكل البيانات
games_data: Dict[str, Dict] = {}  # {chat_id: game_data}
user_states: Dict[str, Dict] = {}  # {user_id: state}
game_sessions: Dict[str, Dict] = {}  # {chat_id: session_data}

# خيارات أماكن الاختباء
HIDING_SPOTS = [
    "🏠 تحت السرير",
    "🚪 خلف الباب",
    "🗄️ داخل الخزانة",
    "🪟 خلف الستارة",
    "🍽️ تحت الطاولة"
]

class GameManager:
    def __init__(self, chat_id: int):
        self.chat_id = chat_id
        self.is_active = False
        self.participants: List[int] = []
        self.seeker: Optional[int] = None
        self.hiders: Dict[int, str] = {}  # {user_id: hiding_spot}
        self.current_seeker_mistakes = 0
        self.seeker_chances = 3
        self.current_guess = None
        self.game_start_time = None
        self.last_warning_time = None

async def start_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بدء اللعبة (للمسؤول فقط)"""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    # التحقق من أن المستخدم مسؤول
    chat_member = await context.bot.get_chat_member(chat_id, user_id)
    if not chat_member.status in ['administrator', 'creator']:
        await update.message.reply_text("❌ فقط المسؤول يمكنه بدء اللعبة!")
        return
    
    if chat_id in games_data and games_data[chat_id].is_active:
        await update.message.reply_text("🎮 اللعبة نشطة بالفعل!")
        return
    
    # تهيئة لعبة جديدة
    games_data[chat_id] = GameManager(chat_id)
    games_data[chat_id].is_active = True
    games_data[chat_id].game_start_time = datetime.now()
    
    # بدء المهمة المجدولة لإرسال رسائل المشاركة
    if chat_id not in context.chat_data:
        context.chat_data[chat_id] = {}
    
    context.chat_data[chat_id]['join_task'] = asyncio.create_task(
        send_join_messages(context, chat_id)
    )
    
    await update.message.reply_text(
        "🎮 **تم بدء اللعبة!** 🎮\n\n"
        "سيتم إرسال رسائل للمشاركة كل دقيقة.\n"
        "اضغط على الزر أدناه للمشاركة!",
        parse_mode=ParseMode.MARKDOWN
    )

async def send_join_messages(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    """إرسال رسائل المشاركة كل دقيقة"""
    while chat_id in games_data and games_data[chat_id].is_active:
        try:
            keyboard = [[InlineKeyboardButton("🎮 اضغط هنا للمشاركة", callback_data="join_game")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await context.bot.send_message(
                chat_id=chat_id,
                text="🎮 **مشاركة في لعبة الغميضة!** 🎮\n\n"
                     "هل تريد المشاركة في اللعبة؟\n"
                     f"⏰ لديك 3 دقائق للمشاركة!",
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )
            
            # انتظار 60 ثانية
            await asyncio.sleep(60)
            
        except Exception as e:
            logging.error(f"Error in send_join_messages: {e}")
            await asyncio.sleep(60)

async def join_game_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج المشاركة في اللعبة"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    username = query.from_user.username or query.from_user.first_name
    chat_id = query.message.chat_id
    
    if chat_id not in games_data or not games_data[chat_id].is_active:
        await query.edit_message_text("❌ اللعبة غير نشطة حالياً!")
        return
    
    game = games_data[chat_id]
    
    if user_id in game.participants:
        await query.edit_message_text("✅ أنت مشترك بالفعل!")
        return
    
    # إضافة المستخدم للمشاركين
    game.participants.append(user_id)
    
    # تحويل المستخدم للخاص
    keyboard = [[InlineKeyboardButton("🎮 انتقل إلى الخاص", url=f"https://t.me/{context.bot.username}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"✅ **تمت مشاركتك بنجاح!** {username}\n\n"
        "🔜 سيتم تحويلك إلى الخاص لتحديد دورك...",
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )
    
    # إرسال رسالة في الخاص
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=f"🎮 **مرحباً بك في لعبة الغميضة!** 🎮\n\n"
                 f"المجموعة: {query.message.chat.title}\n\n"
                 "⏳ انتظر حتى يتم اختيار المطارد...",
            parse_mode=ParseMode.MARKDOWN
        )
    except:
        pass

async def assign_roles(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """توزيع الأدوار (يتم استدعاؤها بعد انتهاء فترة المشاركة)"""
    chat_id = update.effective_chat.id
    
    if chat_id not in games_data:
        return
    
    game = games_data[chat_id]
    
    if len(game.participants) < 2:
        await context.bot.send_message(
            chat_id=chat_id,
            text="❌ عدد المشاركين غير كافٍ (يحتاج على الأقل شخصين)! انتهت اللعبة."
        )
        game.is_active = False
        return
    
    # اختيار مطارد عشوائي
    game.seeker = random.choice(game.participants)
    hiders = [p for p in game.participants if p != game.seeker]
    
    # إرسال رسالة للمجموعة
    seeker_name = (await context.bot.get_chat(game.seeker)).first_name
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"🎮 **تم توزيع الأدوار!** 🎮\n\n"
             f"🔍 المطارد: {seeker_name}\n"
             f"🙈 عدد المختبئين: {len(hiders)}\n\n"
             f"🔜 يتم الآن إرسال التعليمات للجميع...",
        parse_mode=ParseMode.MARKDOWN
    )
    
    # إرسال للمطارد
    seeker_keyboard = [[InlineKeyboardButton("👥 عرض اللائحة", callback_data="show_list")]]
    seeker_reply_markup = InlineKeyboardMarkup(seeker_keyboard)
    
    await context.bot.send_message(
        chat_id=game.seeker,
        text=f"🔍 **أنت المطارد!** 🔍\n\n"
             f"مهمتك: ابحث عن المختبئين!\n"
             f"✅ لديك {game.seeker_chances} محاولات\n"
             f"🎯 كلما نجحت في القبض على أحد، تزيد محاولاتك 3\n\n"
             f"اضغط على الزر أدناه لعرض قائمة المختبئين:",
        reply_markup=seeker_reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )
    
    # إرسال للمختبئين
    for hider in hiders:
        hiding_spot = random.choice(HIDING_SPOTS)
        game.hiders[hider] = hiding_spot
        
        hiding_keyboard = [[InlineKeyboardButton("🙈 اختيار مكان للاختباء", callback_data="choose_spot")]]
        hiding_reply_markup = InlineKeyboardMarkup(hiding_keyboard)
        
        await context.bot.send_message(
            chat_id=hider,
            text=f"🙈 **أنت مختبئ!** 🙈\n\n"
                 f"اختر مكاناً للاختباء:\n"
                 f"⚠️ إذا أخطأ المطارد، سيتم إرسال لك رسالة لتغيير مكانك!",
            reply_markup=hiding_reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )

async def show_hiders_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض لائحة المختبئين للمطارد"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    # البحث عن اللعبة التي فيها هذا المستخدم مطارد
    for chat_id, game in games_data.items():
        if game.is_active and game.seeker == user_id:
            if not game.hiders:
                await query.edit_message_text("❌ لا يوجد مختبئون حالياً!")
                return
            
            # إنشاء أزرار للمختبئين
            keyboard = []
            for hider_id in game.hiders:
                try:
                    user = await context.bot.get_chat(hider_id)
                    keyboard.append([InlineKeyboardButton(
                        f"🔍 {user.first_name}", 
                        callback_data=f"hunt_{hider_id}"
                    )])
                except:
                    continue
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                f"👥 **قائمة المختبئين:**\n\n"
                f"عدد المختبئين: {len(game.hiders)}\n"
                f"✅ محاولاتك المتبقية: {game.seeker_chances}\n\n"
                f"اختر من تريد البحث عنه:",
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )
            return
    
    await query.edit_message_text("❌ لست مطارداً في أي لعبة!")

async def hunt_player(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مطاردة لاعب معين"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    hunted_id = int(data.split('_')[1])
    
    # البحث عن اللعبة
    for chat_id, game in games_data.items():
        if game.is_active and game.seeker == user_id and hunted_id in game.hiders:
            # عرض أماكن الاختباء
            keyboard = []
            for spot in HIDING_SPOTS:
                keyboard.append([InlineKeyboardButton(spot, callback_data=f"guess_{hunted_id}_{spot}")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                f"🔍 **اختر مكان اختباء {hunted_id}:**\n\n"
                f"✅ محاولاتك المتبقية: {game.seeker_chances}\n"
                f"⚠️ إذا أخطأت {3 - game.current_seeker_mistakes + 1} مرات ستنتهي اللعبة!",
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )
            return
    
    await query.edit_message_text("❌ حدث خطأ!")

async def make_guess(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج التخمين"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    _, hunted_id, guessed_spot = data.split('_', 2)
    hunted_id = int(hunted_id)
    user_id = query.from_user.id
    
    # البحث عن اللعبة
    for chat_id, game in games_data.items():
        if game.is_active and game.seeker == user_id:
            if hunted_id not in game.hiders:
                await query.edit_message_text("❌ هذا اللاعب ليس مختبئاً!")
                return
            
            actual_spot = game.hiders[hunted_id]
            
            if guessed_spot == actual_spot:
                # تم القبض على المختبئ
                hunted_name = (await context.bot.get_chat(hunted_id)).first_name
                
                # إرسال رسالة للمجموعة
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"🎉 **تم القبض على {hunted_name}!** 🎉\n\n"
                         f"تم العثور عليه في: {actual_spot}\n"
                         f"✅ المطارد يحصل على 3 محاولات إضافية!",
                    parse_mode=ParseMode.MARKDOWN
                )
                
                # حذف المختبئ من القائمة
                del game.hiders[hunted_id]
                
                # زيادة محاولات المطارد
                game.seeker_chances += 3
                game.current_seeker_mistakes = 0
                
                # إعلام المختبئ
                try:
                    await context.bot.send_message(
                        chat_id=hunted_id,
                        text=f"🔴 **تم القبض عليك!** 🔴\n\n"
                             f"تم العثور عليك في: {actual_spot}\n"
                             f"لعبة جيدة في المرة القادمة!",
                        parse_mode=ParseMode.MARKDOWN
                    )
                except:
                    pass
                
                # التحقق من انتهاء اللعبة
                if not game.hiders:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=f"🏆 **انتهت اللعبة!** 🏆\n\n"
                             f"🔍 المطارد نجح في القبض على جميع المختبئين!\n"
                             f"🎮 شكراً للمشاركة!",
                        parse_mode=ParseMode.MARKDOWN
                    )
                    game.is_active = False
                    return
                
                await query.edit_message_text(f"✅ **صحيح!** تم القبض على المختبئ!\n\nمحاولاتك المتبقية: {game.seeker_chances}")
                
            else:
                # تخمين خاطئ
                game.current_seeker_mistakes += 1
                game.seeker_chances -= 1
                
                if game.seeker_chances <= 0:
                    # انتهت اللعبة
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=f"💔 **انتهت اللعبة!** 💔\n\n"
                             f"🔍 المطارد استنفذ جميع محاولاته!\n"
                             f"🏆 فوز المختبئين!",
                        parse_mode=ParseMode.MARKDOWN
                    )
                    game.is_active = False
                    await query.edit_message_text("❌ انتهت اللعبة! استنفذت جميع محاولاتك.")
                    return
                
                # إرسال رسالة للمختبئ لتغيير مكانه
                try:
                    await context.bot.send_message(
                        chat_id=hunted_id,
                        text=f"⚠️ **تنبيه!** ⚠️\n\n"
                             f"المطارد أخطأ في تخمين مكانك!\n"
                             f"🏃‍♂️ غير مكانك بسرعة قبل أن يعود!",
                        parse_mode=ParseMode.MARKDOWN
                    )
                    
                    # تغيير مكان المختبئ عشوائياً
                    new_spot = random.choice([s for s in HIDING_SPOTS if s != actual_spot])
                    game.hiders[hunted_id] = new_spot
                    
                    await context.bot.send_message(
                        chat_id=hunted_id,
                        text=f"📍 تم تغيير مكانك إلى:\n{new_spot}",
                        parse_mode=ParseMode.MARKDOWN
                    )
                except:
                    pass
                
                await query.edit_message_text(
                    f"❌ **خطأ!** المكان الذي اخترته غير صحيح.\n\n"
                    f"✅ محاولاتك المتبقية: {game.seeker_chances}\n"
                    f"⚠️ تنبيه: تم تغيير مكان المختبئ!",
                    parse_mode=ParseMode.MARKDOWN
                )
            return
    
    await query.edit_message_text("❌ حدث خطأ!")

async def choose_hiding_spot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """اختيار مكان للاختباء"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    # البحث عن اللعبة
    for chat_id, game in games_data.items():
        if game.is_active and user_id in game.hiders:
            keyboard = []
            for spot in HIDING_SPOTS:
                keyboard.append([InlineKeyboardButton(spot, callback_data=f"set_spot_{spot}")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                "🙈 **اختر مكان اختبائك:**\n\n"
                "⚠️ اختر بحكمة، المطارد سيحاول العثور عليك!",
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )
            return
    
    await query.edit_message_text("❌ لست مختبئاً في أي لعبة!")

async def set_hiding_spot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تحديد مكان الاختباء"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    spot = data.replace('set_spot_', '')
    user_id = query.from_user.id
    
    # البحث عن اللعبة
    for chat_id, game in games_data.items():
        if game.is_active and user_id in game.hiders:
            game.hiders[user_id] = spot
            await query.edit_message_text(
                f"✅ **تم اختيار مكان اختبائك!**\n\n"
                f"📍 المكان: {spot}\n\n"
                f"🎮 اللعبة بدأت الآن، حظاً سعيداً!",
                parse_mode=ParseMode.MARKDOWN
            )
            return
    
    await query.edit_message_text("❌ حدث خطأ!")

async def end_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إنهاء اللعبة (للمسؤول)"""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    # التحقق من الصلاحيات
    chat_member = await context.bot.get_chat_member(chat_id, user_id)
    if not chat_member.status in ['administrator', 'creator']:
        await update.message.reply_text("❌ فقط المسؤول يمكنه إنهاء اللعبة!")
        return
    
    if chat_id in games_data:
        games_data[chat_id].is_active = False
        if 'join_task' in context.chat_data.get(chat_id, {}):
            context.chat_data[chat_id]['join_task'].cancel()
        
        await update.message.reply_text("🛑 **تم إنهاء اللعبة!** 🛑")
    else:
        await update.message.reply_text("❌ لا توجد لعبة نشطة!")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مساعدة"""
    help_text = """
🎮 **بوت الغميضة YOHAN** 🎮

**الأوامر المتاحة:**
/start_game - بدء لعبة جديدة (للمسؤول فقط)
/end_game - إنهاء اللعبة الحالية (للمسؤول فقط)
/help - عرض هذه المساعدة

**كيفية اللعب:**
1️⃣ المسؤول يبدأ اللعبة بـ /start_game
2️⃣ كل دقيقة يتم إرسال رسالة للمشاركة
3️⃣ اضغط على الزر للمشاركة (لديك 3 دقائق)
4️⃣ يتم توزيع الأدوار عشوائياً
5️⃣ المطارد يحاول العثور على المختبئين
6️⃣ كل نجاح يمنح المطارد 3 محاولات إضافية
7️⃣ إذا أخطأ المطارد 3 مرات، تنتهي اللعبة

**ملاحظات:**
- فقط المسؤول يمكنه بدء/إنهاء اللعبة
- يلزم وجود شخصين على الأقل للمشاركة
"""
    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)

def main():
    """تشغيل البوت"""
    application = Application.builder().token(TOKEN).build()
    
    # إضافة المعالجات
    application.add_handler(CommandHandler("start_game", start_game))
    application.add_handler(CommandHandler("end_game", end_game))
    application.add_handler(CommandHandler("help", help_command))
    
    # معالجات الكولباك
    application.add_handler(CallbackQueryHandler(join_game_callback, pattern="join_game"))
    application.add_handler(CallbackQueryHandler(show_hiders_list, pattern="show_list"))
    application.add_handler(CallbackQueryHandler(hunt_player, pattern="hunt_"))
    application.add_handler(CallbackQueryHandler(make_guess, pattern="guess_"))
    application.add_handler(CallbackQueryHandler(choose_hiding_spot, pattern="choose_spot"))
    application.add_handler(CallbackQueryHandler(set_hiding_spot, pattern="set_spot_"))
    
    # تشغيل البوت
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
