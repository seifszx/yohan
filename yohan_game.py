import logging
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
BOT_USERNAME = "GSKFNBOT"  # ← غيّر هذا لاسم البوت الحقيقي

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

games = {}

# ── /start في الخاص ──
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user

    if chat.type == "private":
        # تحقق إذا جاء من رابط الانضمام
        if context.args and context.args[0].startswith("join_"):
            chat_id = int(context.args[0].split("_")[1])
            await join_game(update, context, user, chat_id)
        else:
            await update.message.reply_text(
                "𝗬𝗢𝗛𝗔𝗡 🕵️\n\n"
                "بوت لعبة الغموضية!\n"
                "اطلب من مسؤول المجموعة تفعيل اللعبة بأمر /newgame"
            )

# ── انضمام للعبة ──
async def join_game(update, context, user, chat_id):
    if chat_id not in games:
        await update.message.reply_text("❌ لا توجد لعبة نشطة في هذه المجموعة!")
        return

    if games[chat_id]["phase"] != "joining":
        await update.message.reply_text("❌ انتهى وقت التسجيل!")
        return

    if user.id in games[chat_id]["players"]:
        await update.message.reply_text("✅ أنت مسجل بالفعل! انتظر بدء اللعبة.")
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

    # أرسل رسالة تأكيد في الخاص
    await update.message.reply_text(
        f"✅ *تم تسجيلك بنجاح!*\n\n"
        f"انتظر حتى تبدأ اللعبة وستصلك رسالة بدورك 🎮",
        parse_mode="Markdown"
    )

# ── /newgame ──
async def new_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user

    if chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("❌ هذا الأمر للمجموعات فقط!")
        return

    member = await context.bot.get_chat_member(chat.id, user.id)
    if member.status not in ["administrator", "creator"]:
        await update.message.reply_text("❌ هذا الأمر للمسؤولين فقط!")
        return

    if chat.id in games and games[chat.id].get("phase") == "playing":
        await update.message.reply_text("⚠️ يوجد لعبة جارية بالفعل!")
        return

    games[chat.id] = {
        "active": True,
        "phase": "joining",
        "players": {},
        "hunter_id": None,
        "join_message_id": None,
        "admin_id": user.id,
        "chat_id": chat.id,
    }

    # زر يفتح محادثة خاصة مع البوت
    join_url = f"https://t.me/{BOT_USERNAME}?start=join_{chat.id}"
    keyboard = [[InlineKeyboardButton("✋ للمشاركة اضغط هنا!", url=join_url)]]

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

    context.job_queue.run_repeating(
        send_join_reminder,
        interval=60,
        first=60,
        data={"chat_id": chat.id},
        name=f"reminder_{chat.id}"
    )

    context.job_queue.run_once(
        end_joining_phase,
        when=180,
        data={"chat_id": chat.id},
        name=f"end_join_{chat.id}"
    )

# ── رسالة تذكير ──
async def send_join_reminder(context: ContextTypes.DEFAULT_TYPE):
    data = context.job.data
    chat_id = data["chat_id"]

    if chat_id not in games or games[chat_id]["phase"] != "joining":
        context.job.schedule_removal()
        return

    players_count = len(games[chat_id]["players"])
    join_url = f"https://t.me/{BOT_USERNAME}?start=join_{chat_id}"
    keyboard = [[InlineKeyboardButton("✋ للمشاركة اضغط هنا!", url=join_url)]]

    await context.bot.send_message(
        chat_id=chat_id,
        text=f"🔔 *لا تفوت اللعبة!*\n\n"
             f"👥 المشاركون: *{players_count}*\n"
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

    jobs = context.job_queue.get_jobs_by_name(f"reminder_{chat_id}")
    for job in jobs:
        job.schedule_removal()

    if len(players) < 3:
        await context.bot.send_message(
            chat_id=chat_id,
            text="❌ *انتهى وقت التسجيل!*\n\nعدد اللاعبين غير كافٍ (يحتاج 3 على الأقل).\nاستخدم /newgame للبدء من جديد.",
            parse_mode="Markdown"
        )
        games.pop(chat_id, None)
        return

    player_ids = list(players.keys())
    hunter_id = random.choice(player_ids)
    game["hunter_id"] = hunter_id
    game["phase"] = "playing"

    for pid in player_ids:
        players[pid]["alive"] = True
        players[pid]["location"] = None
        players[pid]["role"] = "hunter" if pid == hunter_id else "hider"

    await context.bot.send_message(
        chat_id=chat_id,
        text=f"🎮 *بدأت اللعبة!*\n\n"
             f"👥 عدد اللاعبين: *{len(player_ids)}*\n"
             f"📱 تفقد رسائلك الخاصة مع البوت!",
        parse_mode="Markdown"
    )

    for pid in player_ids:
        try:
            if players[pid]["role"] == "hunter":
                await send_hunter_menu(context, chat_id, pid)
            else:
                await send_hider_menu(context, chat_id, pid)
        except Exception as e:
            logger.error(f"Error sending role to {pid}: {e}")

# ── قائمة الطارد ──
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
        text="🕵️ *أنت الطارد!*\n\nاختر شخصاً لتطارده:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ── قائمة المختبئ ──
async def send_hider_menu(context, chat_id, hider_id, is_change=False):
    spots = random.sample(HIDING_SPOTS, 5)
    keyboard = [[InlineKeyboardButton(spot, callback_data=f"hide_{chat_id}_{spot}")] for spot in spots]

    msg = "⚠️ *غيّر مكانك بسرعة!*\n\nاختر مكان اختبائك:" if is_change else "🙈 *أنت مختبئ!*\n\nاختر مكان اختبائك:"

    await context.bot.send_message(
        chat_id=hider_id,
        text=msg,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ── معالج الأزرار ──
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    data = query.data
    await query.answer()

    # ── الطارد يختار شخصاً ──
    if data.startswith("hunt_"):
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
        if not target or not target["alive"]:
            await query.answer("❌ هذا الشخص غير متاح!", show_alert=True)
            return

        hunter_guess = random.choice(HIDING_SPOTS)
        target_location = target.get("location")

        if target_location and hunter_guess == target_location:
            target["alive"] = False

            await context.bot.send_message(
                chat_id=chat_id,
                text=f"🎯 *تم القبض على {target['name']}!*\n\nوجده الطارد في: {target_location}",
                parse_mode="Markdown"
            )

            try:
                await context.bot.send_message(
                    chat_id=target_id,
                    text=f"😱 *تم القبض عليك!*\n\nوجدك الطارد في {target_location}!\nأنت خارج من اللعبة."
                )
            except:
                pass

            alive_hiders = [pid for pid, p in game["players"].items()
                           if p["role"] == "hider" and p["alive"]]

            if not alive_hiders:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="🏆 *انتهت اللعبة!*\n\nالطارد فاز! 🕵️",
                    parse_mode="Markdown"
                )
                games.pop(chat_id, None)
            else:
                await send_hunter_menu(context, chat_id, user.id)

        else:
            await query.edit_message_text(
                f"❌ *أخطأت!*\n\n{target['name']} لم يكن هناك!\nانتظر دقيقة...",
                parse_mode="Markdown"
            )

            try:
                await context.bot.send_message(
                    chat_id=target_id,
                    text="⚠️ *الطارد يبحث عنك!*\n\nغيّر مكانك بسرعة!",
                    parse_mode="Markdown"
                )
                await send_hider_menu(context, chat_id, target_id, is_change=True)
            except:
                pass

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

        if user.id not in game["players"] or game["players"][user.id]["role"] != "hider":
            return

        old_location = game["players"][user.id]["location"]
        game["players"][user.id]["location"] = spot

        msg = f"✅ *غيّرت مكانك إلى:* {spot} 🙈" if old_location else f"✅ *اخترت الاختباء في:* {spot} 🙈"
        await query.edit_message_text(msg, parse_mode="Markdown")

# ── إعادة قائمة الطارد بعد الانتظار ──
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

    for job_name in [f"reminder_{chat.id}", f"end_join_{chat.id}", f"hunter_wait_{chat.id}"]:
        for job in context.job_queue.get_jobs_by_name(job_name):
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
