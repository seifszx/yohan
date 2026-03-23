importimport logging
import asyncio
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = "8779896667:AAEwivan1ZXUI_Y5qt5eoBiu1uW7lCTN6B8"

# ── أماكن الاختباء ──
HIDING_SPOTS = [
    "🌲 الغابة",
    "🏚️ المستودع القديم",
    "⛪ الكنيسة المهجورة",
    "🚢 السفينة الغارقة",
    "🏔️ الكهف الجبلي",
    "🏭 المصنع المهجور",
    "🌾 حقل القمح",
    "🏠 المنزل المسكون",
    "🚉 محطة القطار",
    "🌊 الشاطئ الخفي",
]

# ── تخزين بيانات اللعبة ──
# games[chat_id] = {
#   "active": bool,
#   "phase": "joining" | "playing" | "ended",
#   "players": {user_id: {"name": str, "role": "hunter"|"hider", "location": str, "alive": bool}},
#   "hunter_id": int,
#   "join_message_id": int,
#   "admin_id": int,
# }
games = {}

# ── /start في الخاص ──
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private":
        await update.message.reply_text(
            "𝗬𝗢𝗛𝗔𝗡 🕵️\n\n"
            "بوت لعبة الغموضية!\n"
            "اطلب من مسؤول المجموعة تفعيل اللعبة بأمر /newgame"
        )

# ── /newgame في المجموعة ──
async def new_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user

    if chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("❌ هذا الأمر للمجموعات فقط!")
        return

    # تحقق إن المستخدم مسؤول
    member = await context.bot.get_chat_member(chat.id, user.id)
    if member.status not in ["administrator", "creator"]:
        await update.message.reply_text("❌ هذا الأمر للمسؤولين فقط!")
        return

    if chat.id in games and games[chat.id].get("phase") == "playing":
        await update.message.reply_text("⚠️ يوجد لعبة جارية بالفعل!")
        return

    # إنشاء لعبة جديدة
    games[chat.id] = {
        "active": True,
        "phase": "joining",
        "players": {},
        "hunter_id": None,
        "join_message_id": None,
        "admin_id": user.id,
        "chat_id": chat.id,
    }

    keyboard = [[InlineKeyboardButton("✋ للمشاركة اضغط هنا!", callback_data=f"join_{chat.id}")]]
    msg = await update.message.reply_text(
        "🕵️ *𝗬𝗢𝗛𝗔𝗡 - لعبة الغموضية!*\n\n"
        "📋 قواعد اللعبة:\n"
        "• سيُختار طارد واحد سراً\n"
        "• الباقون يختبئون في أماكن مختلفة\n"
        "• الطارد يحاول إيجادهم\n"
        "• إذا أخطأ الطارد، ينتظر دقيقة والشخص يغير مكانه!\n\n"
        "⏳ لديكم *3 دقائق* للانضمام!\n\n"
        "👇 اضغط للمشاركة:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    games[chat.id]["join_message_id"] = msg.message_id

    # أرسل رسالة مشاركة كل دقيقة
    context.job_queue.run_repeating(
        send_join_reminder,
        interval=60,
        first=60,
        data={"chat_id": chat.id, "msg_id": msg.message_id},
        name=f"reminder_{chat.id}"
    )

    # أنهِ التسجيل بعد 3 دقائق
    context.job_queue.run_once(
        end_joining_phase,
        when=180,
        data={"chat_id": chat.id},
        name=f"end_join_{chat.id}"
    )

# ── رسالة تذكير كل دقيقة ──
async def send_join_reminder(context: ContextTypes.DEFAULT_TYPE):
    data = context.job.data
    chat_id = data["chat_id"]

    if chat_id not in games or games[chat_id]["phase"] != "joining":
        context.job.schedule_removal()
        return

    players_count = len(games[chat_id]["players"])
    keyboard = [[InlineKeyboardButton("✋ للمشاركة اضغط هنا!", callback_data=f"join_{chat_id}")]]

    await context.bot.send_message(
        chat_id=chat_id,
        text=f"🔔 *لا تفوت اللعبة!*\n\n"
             f"👥 المشاركون حتى الآن: *{players_count}*\n"
             f"⏳ الوقت ينفد! اضغط للانضمام 👇",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ── انتهاء مرحلة التسجيل ──
async def end_joining_phase(context: ContextTypes.DEFAULT_TYPE):
    data = context.job.data
    chat_id = data["chat_id"]

    if chat_id not in games:
        return

    game = games[chat_id]
    players = game["players"]

    # أوقف رسائل التذكير
    current_jobs = context.job_queue.get_jobs_by_name(f"reminder_{chat_id}")
    for job in current_jobs:
        job.schedule_removal()

    if len(players) < 3:
        await context.bot.send_message(
            chat_id=chat_id,
            text="❌ *انتهى وقت التسجيل!*\n\nعدد اللاعقين غير كافٍ (يحتاج 3 على الأقل).\nاستخدم /newgame للبدء من جديد.",
            parse_mode="Markdown"
        )
        games.pop(chat_id, None)
        return

    # اختر الطارد عشوائياً
    player_ids = list(players.keys())
    hunter_id = random.choice(player_ids)
    game["hunter_id"] = hunter_id
    game["phase"] = "playing"

    # أعطِ كل لاعب دوره
    for pid in player_ids:
        players[pid]["alive"] = True
        players[pid]["location"] = None
        if pid == hunter_id:
            players[pid]["role"] = "hunter"
        else:
            players[pid]["role"] = "hider"

    # أرسل رسالة في المجموعة
    hiders_count = len(player_ids) - 1
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"🎮 *بدأت اللعبة!*\n\n"
             f"👥 عدد اللاعبين: *{len(player_ids)}*\n"
             f"🏃 طارد واحد سيطارد *{hiders_count}* مختبئين!\n\n"
             f"📱 تفقد رسائلك الخاصة مع البوت!",
        parse_mode="Markdown"
    )

    # أرسل لكل لاعب دوره
    for pid in player_ids:
        try:
            if players[pid]["role"] == "hunter":
                # أرسل للطارد قائمة اللاعبين
                await send_hunter_menu(context, chat_id, pid)
            else:
                # أرسل للمختبئ قائمة الأماكن
                await send_hider_menu(context, chat_id, pid)
        except Exception as e:
            logger.error(f"Error sending role to {pid}: {e}")

# ── إرسال قائمة الطارد ──
async def send_hunter_menu(context, chat_id, hunter_id):
    game = games[chat_id]
    players = game["players"]

    hiders = [(pid, players[pid]["name"]) for pid in players
              if players[pid]["role"] == "hider" and players[pid]["alive"]]

    keyboard = []
    for pid, name in hiders:
        keyboard.append([InlineKeyboardButton(
            f"🎯 {name}",
            callback_data=f"hunt_{chat_id}_{pid}"
        )])

    await context.bot.send_message(
        chat_id=hunter_id,
        text="🕵️ *أنت الطارد!*\n\n"
             "مهمتك إيجاد المختبئين!\n"
             "اختر شخصاً لتطارده:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ── إرسال قائمة المختبئ ──
async def send_hider_menu(context, chat_id, hider_id, is_change=False):
    spots = random.sample(HIDING_SPOTS, 5)
    keyboard = []
    for spot in spots:
        keyboard.append([InlineKeyboardButton(
            spot,
            callback_data=f"hide_{chat_id}_{spot}"
        )])

    msg = "⚠️ *غيّر مكانك بسرعة!*\n\n" if is_change else "🙈 *أنت مختبئ!*\n\n"
    msg += "اختر مكان اختبائك:"

    await context.bot.send_message(
        chat_id=hider_id,
        text=msg,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ── معالج الضغط على الأزرار ──
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    data = query.data

    await query.answer()

    # ── الانضمام للعبة ──
    if data.startswith("join_"):
        chat_id = int(data.split("_")[1])

        if chat_id not in games or games[chat_id]["phase"] != "joining":
            await query.answer("❌ التسجيل انتهى!", show_alert=True)
            return

        if user.id in games[chat_id]["players"]:
            await query.answer("✅ أنت مسجل بالفعل!", show_alert=True)
            return

        # أضف اللاعب
        games[chat_id]["players"][user.id] = {
            "name": user.first_name,
            "role": None,
            "location": None,
            "alive": True,
        }

        players_count = len(games[chat_id]["players"])

        # أبلغ المجموعة
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"✅ *{user.first_name}* انضم للعبة!\n👥 إجمالي اللاعبين: *{players_count}*",
            parse_mode="Markdown"
        )

        # أرسل رسالة خاصة
        try:
            await context.bot.send_message(
                chat_id=user.id,
                text=f"✅ *تم تسجيلك في اللعبة!*\n\n"
                     f"انتظر حتى تبدأ اللعبة وستصلك رسالة بدورك 🎮",
                parse_mode="Markdown"
            )
        except Exception:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"⚠️ {user.first_name} يجب أن تبدأ محادثة مع البوت أولاً!\n"
                     f"اضغط هنا: @YohanGameBot ثم اضغط Start"
            )

    # ── الطارد يختار شخصاً ──
    elif data.startswith("hunt_"):
        parts = data.split("_")
        chat_id = int(parts[1])
        target_id = int(parts[2])

        if chat_id not in games:
            return

        game = games[chat_id]

        if user.id != game["hunter_id"]:
            await query.answer("❌ لست الطارد!", show_alert=True)
            return

        target = game["players"].get(target_id)
        hunter = game["players"].get(user.id)

        if not target or not target["alive"]:
            await query.answer("❌ هذا الشخص غير متاح!", show_alert=True)
            return

        # اختر مكان عشوائي للطارد
        hunter_guess = random.choice(HIDING_SPOTS)
        target_location = target.get("location")

        if target_location and hunter_guess == target_location:
            # ✅ إصابة!
            target["alive"] = False

            await context.bot.send_message(
                chat_id=chat_id,
                text=f"🎯 *تم القبض على {target['name']}!*\n\n"
                     f"وجده الطارد في: {target_location}",
                parse_mode="Markdown"
            )

            # أبلغ الشخص المقبوض عليه
            try:
                await context.bot.send_message(
                    chat_id=target_id,
                    text=f"😱 *تم القبض عليك!*\n\nوجدك الطارد في {target_location}!\nأنت خارج من اللعبة."
                )
            except:
                pass

            # تحقق هل انتهت اللعبة
            alive_hiders = [pid for pid, p in game["players"].items()
                           if p["role"] == "hider" and p["alive"]]

            if not alive_hiders:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="🏆 *انتهت اللعبة!*\n\nالطارد فاز بإيجاد جميع المختبئين! 🕵️",
                    parse_mode="Markdown"
                )
                games.pop(chat_id, None)
            else:
                # أرسل للطارد قائمة محدثة
                await send_hunter_menu(context, chat_id, user.id)

        else:
            # ❌ خطأ - انتظر دقيقة
            await query.edit_message_text(
                f"❌ *أخطأت!*\n\n{target['name']} لم يكن هناك!\nانتظر دقيقة قبل المحاولة مجدداً...",
                parse_mode="Markdown"
            )

            # أبلغ الشخص الذي أخطأ فيه
            try:
                await context.bot.send_message(
                    chat_id=target_id,
                    text=f"⚠️ *الطارد يبحث عنك!*\n\nغيّر مكانك بسرعة!",
                    parse_mode="Markdown"
                )
                # أرسل له قائمة تغيير المكان
                await send_hider_menu(context, chat_id, target_id, is_change=True)
            except:
                pass

            # انتظر دقيقة ثم أرسل قائمة الطارد مرة ثانية
            context.job_queue.run_once(
                resend_hunter_menu,
                when=60,
                data={"chat_id": chat_id, "hunter_id": user.id},
                name=f"hunter_wait_{chat_id}"
            )

    # ── المختبئ يختار مكاناً ──
    elif data.startswith("hide_"):
        parts = data.split("_", 2)
        chat_id = int(parts[1])
        spot = parts[2]

        if chat_id not in games:
            return

        game = games[chat_id]

        if user.id not in game["players"]:
            return

        if game["players"][user.id]["role"] != "hider":
            await query.answer("❌ لست مختبئاً!", show_alert=True)
            return

        old_location = game["players"][user.id]["location"]
        game["players"][user.id]["location"] = spot

        if old_location:
            msg = f"✅ *غيّرت مكانك إلى:* {spot}\nكن حذراً! 🙈"
        else:
            msg = f"✅ *اخترت الاختباء في:* {spot}\nانتظر الطارد! 🙈"

        await query.edit_message_text(msg, parse_mode="Markdown")

# ── إعادة إرسال قائمة الطارد بعد الانتظار ──
async def resend_hunter_menu(context: ContextTypes.DEFAULT_TYPE):
    data = context.job.data
    chat_id = data["chat_id"]
    hunter_id = data["hunter_id"]

    if chat_id not in games:
        return

    await context.bot.send_message(
        chat_id=hunter_id,
        text="⏰ *انتهى وقت الانتظار!*\nيمكنك المحاولة مجدداً:",
        parse_mode="Markdown"
    )
    await send_hunter_menu(context, chat_id, hunter_id)

# ── /endgame ──
async def end_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user

    if chat.type not in ["group", "supergroup"]:
        return

    member = await context.bot.get_chat_member(chat.id, user.id)
    if member.status not in ["administrator", "creator"]:
        await update.message.reply_text("❌ هذا الأمر للمسؤولين فقط!")
        return

    if chat.id not in games:
        await update.message.reply_text("❌ لا توجد لعبة جارية!")
        return

    # أوقف كل المهام
    for job_name in [f"reminder_{chat.id}", f"end_join_{chat.id}", f"hunter_wait_{chat.id}"]:
        jobs = context.job_queue.get_jobs_by_name(job_name)
        for job in jobs:
            job.schedule_removal()

    games.pop(chat.id, None)
    await update.message.reply_text("🛑 *تم إنهاء اللعبة!*", parse_mode="Markdown")

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("newgame", new_game))
    app.add_handler(CommandHandler("endgame", end_game))
    app.add_handler(CallbackQueryHandler(button_handler))
    print("🕵️ بوت YOHAN يعمل...", flush=True)
    app.run_polling()

if __name__ == "__main__":
    main()
