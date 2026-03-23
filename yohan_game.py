import logging
import random
import string
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    ContextTypes
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = "8779896667:AAEwivan1ZXUI_Y5qt5eoBiu1uW7lCTN6B8"
BOT_USERNAME = "GSKFNBOT"  # ← غيّر لاسم البوت الحقيقي

HIDING_SPOTS = [
    "🌲 الغابة", "🏚️ المستودع القديم", "⛪ الكنيسة المهجورة",
    "🚢 السفينة الغارقة", "🏔️ الكهف الجبلي", "🏭 المصنع المهجور",
    "🌾 حقل القمح", "🏠 المنزل المسكون", "🚉 محطة القطار", "🌊 الشاطئ الخفي",
]

GAME_DURATION = 180  # ثانية
games = {}       # chat_id -> game
tokens = {}      # token -> chat_id

def generate_token():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=20))

def build_join_text(players):
    player_list = "\n".join([f"• {p['name']}" for p in players.values()]) if players else "لا يوجد مشاركين بعد"
    return (
        f"🕵️ *𝗬𝗢𝗛𝗔𝗡 - لعبة الغموضية!*\n\n"
        f"👥 *#players: {len(players)}*\n{player_list}"
    )

def build_join_keyboard(token):
    join_url = f"https://t.me/{BOT_USERNAME}?start={token}"
    return InlineKeyboardMarkup([[InlineKeyboardButton("✋ الانضمام للعبة", url=join_url)]])

# ── /start في الخاص ──
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user

    if chat.type != "private":
        return

    if not context.args:
        await update.message.reply_text("𝗬𝗢𝗛𝗔𝗡 🕵️\n\nبوت لعبة الغموضية!\nاطلب من مسؤول المجموعة تفعيل اللعبة بأمر /newgame")
        return

    token = context.args[0]

    if token not in tokens:
        await update.message.reply_text("❌ رابط غير صحيح أو انتهت صلاحيته!")
        return

    chat_id = tokens[token]

    if chat_id not in games:
        await update.message.reply_text("❌ لا توجد لعبة نشطة!")
        return

    game = games[chat_id]

    if game["phase"] != "joining":
        await update.message.reply_text("❌ انتهى وقت التسجيل!")
        return

    if user.id in game["players"]:
        await update.message.reply_text("✅ أنت مسجل بالفعل! انتظر بدء اللعبة 🎮")
        return

    # أضف اللاعب
    game["players"][user.id] = {
        "name": user.first_name,
        "role": None,
        "location": None,
        "alive": True,
    }

    await update.message.reply_text(
        f"✅ *تم تسجيلك بنجاح!*\n\nانتظر بدء اللعبة وستصلك رسالة بدورك 🎮",
        parse_mode="Markdown"
    )

    # حدّث رسالة المجموعة فوراً
    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=game["join_message_id"],
            text=build_join_text(game["players"]),
            parse_mode="Markdown",
            reply_markup=build_join_keyboard(token)
        )
    except Exception as e:
        logger.error(f"Edit message error: {e}")

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

    # أنشئ token فريد
    token = generate_token()
    tokens[token] = chat.id

    games[chat.id] = {
        "phase": "joining",
        "players": {},
        "hunter_id": None,
        "join_message_id": None,
        "admin_id": user.id,
        "chat_id": chat.id,
        "token": token,
        "seconds_left": GAME_DURATION,
        "hunter_mistakes": 0,
    }

    msg = await update.message.reply_text(
        build_join_text({}),
        parse_mode="Markdown",
        reply_markup=build_join_keyboard(token)
    )
    games[chat.id]["join_message_id"] = msg.message_id

    # رسالة عد تنازلي كل 40 ثانية
    context.job_queue.run_repeating(
        send_countdown,
        interval=40,
        first=40,
        data={"chat_id": chat.id, "token": token},
        name=f"timer_{chat.id}"
    )

    # انتهاء التسجيل بعد 3 دقائق
    context.job_queue.run_once(
        end_joining_phase,
        when=GAME_DURATION,
        data={"chat_id": chat.id},
        name=f"end_join_{chat.id}"
    )

# ── رسالة عد تنازلي كل 40 ثانية ──
async def send_countdown(context: ContextTypes.DEFAULT_TYPE):
    data = context.job.data
    chat_id = data["chat_id"]
    token = data["token"]

    if chat_id not in games or games[chat_id]["phase"] != "joining":
        context.job.schedule_removal()
        return

    game = games[chat_id]
    game["seconds_left"] = max(0, game["seconds_left"] - 40)
    seconds_left = game["seconds_left"]
    players_count = len(game["players"])
    join_url = f"https://t.me/{BOT_USERNAME}?start={token}"
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("✋ الانضمام للعبة", url=join_url)]])

    await context.bot.send_message(
        chat_id=chat_id,
        text=f"⏳ *بقي {seconds_left} ثانية حتى بداية اللعبة!*\n\n"
             f"👥 المشاركون الآن: *{players_count}*\n\n"
             f"👇 اضغط هنا للانضمام",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

# ── انتهاء مرحلة التسجيل ──
async def end_joining_phase(context: ContextTypes.DEFAULT_TYPE):
    data = context.job.data
    chat_id = data["chat_id"]

    if chat_id not in games:
        return

    game = games[chat_id]
    players = game["players"]

    # أوقف العداد
    for job in context.job_queue.get_jobs_by_name(f"timer_{chat_id}"):
        job.schedule_removal()

    if len(players) < 3:
        await context.bot.send_message(
            chat_id=chat_id,
            text="❌ *انتهى وقت التسجيل!*\nعدد اللاعبين غير كافٍ (يحتاج 3+).\nاستخدم /newgame للبدء.",
            parse_mode="Markdown"
        )
        tokens.pop(game["token"], None)
        games.pop(chat_id, None)
        return

    # اختر المطارد
    player_ids = list(players.keys())
    hunter_id = random.choice(player_ids)
    game["hunter_id"] = hunter_id
    game["phase"] = "playing"
    game["hunter_mistakes"] = 0

    for pid in player_ids:
        players[pid]["alive"] = True
        players[pid]["location"] = None
        players[pid]["role"] = "hunter" if pid == hunter_id else "hider"

    player_list = "\n".join([f"• {p['name']}" for p in players.values()])
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"🎮 *بدأت اللعبة!*\n\n"
             f"👥 *اللاعبون:*\n{player_list}\n\n"
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

# ── قائمة المطارد ──
async def send_hunter_menu(context, chat_id, hunter_id):
    game = games[chat_id]
    players = game["players"]
    hiders = [(pid, players[pid]["name"]) for pid in players
              if players[pid]["role"] == "hider" and players[pid]["alive"]]
    mistakes = game["hunter_mistakes"]
    keyboard = [[InlineKeyboardButton(f"🎯 {name}", callback_data=f"hunt_{chat_id}_{pid}")] for pid, name in hiders]

    await context.bot.send_message(
        chat_id=hunter_id,
        text=f"🕵️ *أنت المطارد!*\n\n"
             f"❌ الأخطاء: *{mistakes}/3*\n\n"
             f"اختر شخصاً لتطارده:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ── قائمة المختبئ ──
async def send_hider_menu(context, chat_id, hider_id, is_change=False):
    spots = random.sample(HIDING_SPOTS, 5)
    keyboard = [[InlineKeyboardButton(spot, callback_data=f"hide_{chat_id}_{spot}")] for spot in spots]
    msg = "⚠️ *غيّر مكانك بسرعة!*\n\nاختر مكان اختبائك:" if is_change else "🙈 *أنت مختبئ!*\n\nاختر مكان اختبائك:"
    await context.bot.send_message(chat_id=hider_id, text=msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

# ── معالج الأزرار ──
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    data = query.data
    await query.answer()

    if data.startswith("hunt_"):
        parts = data.split("_")
        chat_id = int(parts[1])
        target_id = int(parts[2])

        if chat_id not in games:
            return

        game = games[chat_id]
        if user.id != game["hunter_id"]:
            await query.answer("❌ لست المطارد!", show_alert=True)
            return

        target = game["players"].get(target_id)
        if not target or not target["alive"]:
            await query.answer("❌ هذا الشخص غير متاح!", show_alert=True)
            return

        hunter_guess = random.choice(HIDING_SPOTS)
        target_location = target.get("location")

        if target_location and hunter_guess == target_location:
            # ✅ إصابة!
            target["alive"] = False
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"🎯 *تم القبض على {target['name']}!*\n\nوجده المطارد في: {target_location}",
                parse_mode="Markdown"
            )
            try:
                await context.bot.send_message(chat_id=target_id, text=f"😱 *تم القبض عليك في {target_location}!*\nأنت خارج.", parse_mode="Markdown")
            except:
                pass

            alive_hiders = [pid for pid, p in game["players"].items() if p["role"] == "hider" and p["alive"]]
            if not alive_hiders:
                await context.bot.send_message(chat_id=chat_id, text="🏆 *انتهت اللعبة! المطارد فاز!* 🕵️", parse_mode="Markdown")
                tokens.pop(game["token"], None)
                games.pop(chat_id, None)
            else:
                await send_hunter_menu(context, chat_id, user.id)

        else:
            # ❌ خطأ
            game["hunter_mistakes"] += 1
            mistakes = game["hunter_mistakes"]

            if mistakes >= 3:
                # انتهت اللعبة - المختبئون فازوا
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"🎉 *انتهت اللعبة!*\n\nأخطأ المطارد 3 مرات!\n*المختبئون فازوا!* 🙈",
                    parse_mode="Markdown"
                )
                # أبلغ المطارد
                try:
                    await context.bot.send_message(chat_id=user.id, text="😔 *خسرت!* أخطأت 3 مرات واللعبة انتهت!", parse_mode="Markdown")
                except:
                    pass
                tokens.pop(game["token"], None)
                games.pop(chat_id, None)
                return

            await query.edit_message_text(
                f"❌ *أخطأت!* ({mistakes}/3)\n\n{target['name']} لم يكن هناك!\nانتظر دقيقة...",
                parse_mode="Markdown"
            )

            try:
                await context.bot.send_message(chat_id=target_id, text="⚠️ *المطارد يبحث عنك! غيّر مكانك!*", parse_mode="Markdown")
                await send_hider_menu(context, chat_id, target_id, is_change=True)
            except:
                pass

            context.job_queue.run_once(
                resend_hunter_menu,
                when=60,
                data={"chat_id": chat_id, "hunter_id": user.id},
                name=f"hunter_wait_{chat_id}"
            )

    elif data.startswith("hide_"):
        parts = data.split("_", 2)
        chat_id = int(parts[1])
        spot = parts[2]

        if chat_id not in games:
            return

        game = games[chat_id]
        if user.id not in game["players"] or game["players"][user.id]["role"] != "hider":
            return

        old = game["players"][user.id]["location"]
        game["players"][user.id]["location"] = spot
        msg = f"✅ *غيّرت مكانك إلى:* {spot} 🙈" if old else f"✅ *اخترت الاختباء في:* {spot} 🙈"
        await query.edit_message_text(msg, parse_mode="Markdown")

async def resend_hunter_menu(context: ContextTypes.DEFAULT_TYPE):
    data = context.job.data
    chat_id = data["chat_id"]
    hunter_id = data["hunter_id"]
    if chat_id not in games:
        return
    await context.bot.send_message(chat_id=hunter_id, text="⏰ *انتهى وقت الانتظار! حاول مجدداً:*", parse_mode="Markdown")
    await send_hunter_menu(context, chat_id, hunter_id)

async def end_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    if chat.type not in ["group", "supergroup"]:
        return
    member = await context.bot.get_chat_member(chat.id, user.id)
    if member.status not in ["administrator", "creator"]:
        await update.message.reply_text("❌ للمسؤولين فقط!")
        return
    if chat.id not in games:
        await update.message.reply_text("❌ لا توجد لعبة جارية!")
        return
    for job_name in [f"timer_{chat.id}", f"end_join_{chat.id}", f"hunter_wait_{chat.id}"]:
        for job in context.job_queue.get_jobs_by_name(job_name):
            job.schedule_removal()
    token = games[chat.id].get("token")
    tokens.pop(token, None)
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

