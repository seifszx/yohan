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
BOT_USERNAME = "GSKFNBOT"

HIDING_SPOTS = [
    "🌲 الغابة", "🏚️ المستودع القديم", "⛪ الكنيسة المهجورة",
    "🚢 السفينة الغارقة", "🏔️ الكهف الجبلي", "🏭 المصنع المهجور",
    "🌾 حقل القمح", "🏠 المنزل المسكون", "🚉 محطة القطار", "🌊 الشاطئ الخفي",
]

GAME_DURATION = 180
games = {}
tokens = {}

def gen_token():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=30))

def players_text(players):
    names = "\n".join([f"• {p['name']}" for p in players.values()]) if players else "—"
    return (
        f"🕵️ *𝗬𝗢𝗛𝗔𝗡 - لعبة الغموضية!*\n\n"
        f"👥 *#players: {len(players)}*\n{names}"
    )

def join_keyboard(token):
    url = f"https://t.me/{BOT_USERNAME}?start={token}"
    return InlineKeyboardMarkup([[InlineKeyboardButton("✋ الانضمام للعبة", url=url)]])

# ── /start ──
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return

    user = update.effective_user
    args = context.args

    # إذا جاء بـ token
    if args:
        token = args[0]
        if token not in tokens:
            await update.message.reply_text("❌ رابط منتهي الصلاحية!")
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

        game["players"][user.id] = {
            "name": user.first_name,
            "role": None, "location": None, "alive": True,
        }

        await update.message.reply_text(
            f"✅ *تم تسجيلك!*\n\nانتظر بدء اللعبة وستصلك رسالة بدورك 🎮",
            parse_mode="Markdown"
        )

        # حدّث رسالة المجموعة فوراً
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=game["join_message_id"],
                text=players_text(game["players"]),
                parse_mode="Markdown",
                reply_markup=join_keyboard(token)
            )
        except Exception as e:
            logger.error(f"Edit error: {e}")
        return

    # بدون args
    await update.message.reply_text(
        "𝗬𝗢𝗛𝗔𝗡 🕵️\n\n"
        "بوت لعبة الغموضية!\n"
        "اطلب من مسؤول المجموعة تفعيل اللعبة بأمر /newgame"
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
        await update.message.reply_text("❌ للمسؤولين فقط!")
        return

    if chat.id in games and games[chat.id]["phase"] == "playing":
        await update.message.reply_text("⚠️ يوجد لعبة جارية!")
        return

    token = gen_token()
    tokens[token] = chat.id

    games[chat.id] = {
        "phase": "joining",
        "players": {},
        "hunter_id": None,
        "join_message_id": None,
        "token": token,
        "seconds_left": GAME_DURATION,
        "hunter_mistakes": 0,
        "chat_id": chat.id,
    }

    msg = await context.bot.send_message(
        chat_id=chat.id,
        text=players_text({}),
        parse_mode="Markdown",
        reply_markup=join_keyboard(token)
    )
    games[chat.id]["join_message_id"] = msg.message_id

    # عداد كل 40 ثانية
    context.job_queue.run_repeating(
        countdown_job,
        interval=40,
        first=40,
        data={"chat_id": chat.id, "token": token},
        name=f"timer_{chat.id}"
    )

    # انتهاء التسجيل
    context.job_queue.run_once(
        end_joining,
        when=GAME_DURATION,
        data={"chat_id": chat.id},
        name=f"endjoin_{chat.id}"
    )

# ── عداد كل 40 ثانية ──
async def countdown_job(context: ContextTypes.DEFAULT_TYPE):
    d = context.job.data
    chat_id = d["chat_id"]
    token = d["token"]

    if chat_id not in games or games[chat_id]["phase"] != "joining":
        context.job.schedule_removal()
        return

    game = games[chat_id]
    game["seconds_left"] = max(0, game["seconds_left"] - 40)
    secs = game["seconds_left"]
    count = len(game["players"])
    url = f"https://t.me/{BOT_USERNAME}?start={token}"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("✋ الانضمام للعبة", url=url)]])

    await context.bot.send_message(
        chat_id=chat_id,
        text=f"⏳ *بقي {secs} ثانية حتى بداية اللعبة!*\n"
             f"👥 المشاركون: *{count}*\n\n"
             f"👇 اضغط هنا للانضمام",
        parse_mode="Markdown",
        reply_markup=kb
    )

# ── انتهاء التسجيل ──
async def end_joining(context: ContextTypes.DEFAULT_TYPE):
    d = context.job.data
    chat_id = d["chat_id"]

    if chat_id not in games:
        return

    game = games[chat_id]

    for j in context.job_queue.get_jobs_by_name(f"timer_{chat_id}"):
        j.schedule_removal()

    players = game["players"]

    if len(players) < 3:
        await context.bot.send_message(
            chat_id=chat_id,
            text="❌ *انتهى وقت التسجيل!*\nيحتاج 3 لاعبين على الأقل.\nاستخدم /newgame للبدء من جديد.",
            parse_mode="Markdown"
        )
        tokens.pop(game["token"], None)
        games.pop(chat_id, None)
        return

    pids = list(players.keys())
    hunter_id = random.choice(pids)
    game["hunter_id"] = hunter_id
    game["phase"] = "playing"
    game["hunter_mistakes"] = 0

    for pid in pids:
        players[pid].update({"alive": True, "location": None,
                              "role": "hunter" if pid == hunter_id else "hider"})

    names = "\n".join([f"• {p['name']}" for p in players.values()])
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"🎮 *بدأت اللعبة!*\n\n👥 *اللاعبون:*\n{names}\n\n📱 تفقد رسائلك الخاصة!",
        parse_mode="Markdown"
    )

    for pid in pids:
        try:
            if players[pid]["role"] == "hunter":
                await send_hunter_menu(context, chat_id, pid)
            else:
                await send_hider_menu(context, chat_id, pid)
        except Exception as e:
            logger.error(f"Send role error {pid}: {e}")

# ── قائمة المطارد ──
async def send_hunter_menu(context, chat_id, hunter_id):
    game = games[chat_id]
    hiders = [(pid, game["players"][pid]["name"]) for pid in game["players"]
              if game["players"][pid]["role"] == "hider" and game["players"][pid]["alive"]]
    kb = [[InlineKeyboardButton(f"🎯 {name}", callback_data=f"hunt_{chat_id}_{pid}")] for pid, name in hiders]
    mistakes = game["hunter_mistakes"]
    await context.bot.send_message(
        chat_id=hunter_id,
        text=f"🕵️ *أنت المطارد!*\n\n❌ الأخطاء: *{mistakes}/3*\n\nاختر شخصاً لتطارده:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb)
    )

# ── قائمة المختبئ ──
async def send_hider_menu(context, chat_id, hider_id, is_change=False):
    spots = random.sample(HIDING_SPOTS, 5)
    kb = [[InlineKeyboardButton(s, callback_data=f"hide_{chat_id}_{s}")] for s in spots]
    txt = "⚠️ *غيّر مكانك بسرعة!*\n\nاختر مكان اختبائك:" if is_change else "🙈 *أنت مختبئ!*\n\nاختر مكان اختبائك:"
    await context.bot.send_message(chat_id=hider_id, text=txt, parse_mode="Markdown",
                                    reply_markup=InlineKeyboardMarkup(kb))

# ── أزرار ──
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    user = q.from_user
    data = q.data
    await q.answer()

    if data.startswith("hunt_"):
        _, cid, tid = data.split("_")
        chat_id, target_id = int(cid), int(tid)

        if chat_id not in games:
            return
        game = games[chat_id]

        if user.id != game["hunter_id"]:
            await q.answer("❌ لست المطارد!", show_alert=True)
            return

        target = game["players"].get(target_id)
        if not target or not target["alive"]:
            await q.answer("❌ غير متاح!", show_alert=True)
            return

        guess = random.choice(HIDING_SPOTS)
        loc = target.get("location")

        if loc and guess == loc:
            target["alive"] = False
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"🎯 *تم القبض على {target['name']}!*\nوجده المطارد في: {loc}",
                parse_mode="Markdown"
            )
            try:
                await context.bot.send_message(target_id, f"😱 *تم القبض عليك في {loc}!*\nأنت خارج.", parse_mode="Markdown")
            except: pass

            alive = [p for p in game["players"].values() if p["role"] == "hider" and p["alive"]]
            if not alive:
                await context.bot.send_message(chat_id, "🏆 *انتهت اللعبة! المطارد فاز!* 🕵️", parse_mode="Markdown")
                tokens.pop(game["token"], None)
                games.pop(chat_id, None)
            else:
                await send_hunter_menu(context, chat_id, user.id)

        else:
            game["hunter_mistakes"] += 1
            m = game["hunter_mistakes"]

            if m >= 3:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="🎉 *انتهت اللعبة!*\nأخطأ المطارد 3 مرات!\n*المختبئون فازوا!* 🙈",
                    parse_mode="Markdown"
                )
                try: await context.bot.send_message(user.id, "😔 *خسرت!* أخطأت 3 مرات!", parse_mode="Markdown")
                except: pass
                tokens.pop(game["token"], None)
                games.pop(chat_id, None)
                return

            await q.edit_message_text(
                f"❌ *أخطأت!* ({m}/3)\n{target['name']} لم يكن هناك!\nانتظر دقيقة...",
                parse_mode="Markdown"
            )
            try:
                await context.bot.send_message(target_id, "⚠️ *المطارد يبحث عنك! غيّر مكانك!*", parse_mode="Markdown")
                await send_hider_menu(context, chat_id, target_id, is_change=True)
            except: pass

            context.job_queue.run_once(
                lambda ctx: send_hunter_menu(ctx, chat_id, user.id),
                when=60,
                name=f"hwait_{chat_id}"
            )

    elif data.startswith("hide_"):
        parts = data.split("_", 2)
        chat_id, spot = int(parts[1]), parts[2]

        if chat_id not in games: return
        game = games[chat_id]
        if user.id not in game["players"] or game["players"][user.id]["role"] != "hider": return

        old = game["players"][user.id]["location"]
        game["players"][user.id]["location"] = spot
        txt = f"✅ *غيّرت مكانك إلى:* {spot} 🙈" if old else f"✅ *اخترت الاختباء في:* {spot} 🙈"
        await q.edit_message_text(txt, parse_mode="Markdown")

# ── /endgame ──
async def end_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    if chat.type not in ["group", "supergroup"]: return
    member = await context.bot.get_chat_member(chat.id, user.id)
    if member.status not in ["administrator", "creator"]:
        await update.message.reply_text("❌ للمسؤولين فقط!")
        return
    if chat.id not in games:
        await update.message.reply_text("❌ لا توجد لعبة!")
        return
    for jn in [f"timer_{chat.id}", f"endjoin_{chat.id}", f"hwait_{chat.id}"]:
        for j in context.job_queue.get_jobs_by_name(jn): j.schedule_removal()
    tokens.pop(games[chat.id].get("token"), None)
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
