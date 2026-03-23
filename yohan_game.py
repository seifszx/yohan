import logging
import random
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

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

def players_text(players):
    names = "\n".join([f"• {p['name']}" for p in players.values()]) if players else "—"
    return f"🕵️ *𝗬𝗢𝗛𝗔𝗡 - لعبة الغموضية!*\n\n👥 *#players: {len(players)}*\n{names}"

def join_kb(chat_id):
    return InlineKeyboardMarkup([[InlineKeyboardButton("✋ الانضمام للعبة", callback_data=f"join_{chat_id}")]])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return
    await update.message.reply_text(
        "🕵️ *أهلاً في 𝗬𝗢𝗛𝗔𝗡!*\n\nبوت لعبة الغموضية!\nأضف البوت لمجموعتك ثم اكتب /newgame",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("➕ إضافة يوهان", url=f"https://t.me/{BOT_USERNAME}?startgroup=start")
        ]])
    )

async def new_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user

    if chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("❌ للمجموعات فقط!")
        return

    member = await context.bot.get_chat_member(chat.id, user.id)
    if member.status not in ["administrator", "creator"]:
        await update.message.reply_text("❌ للمسؤولين فقط!")
        return

    if chat.id in games:
        await update.message.reply_text("⚠️ يوجد لعبة جارية! استخدم /endgame أولاً")
        return

    games[chat.id] = {
        "phase": "joining",
        "players": {},
        "hunter_id": None,
        "join_message_id": None,
        "hunter_mistakes": 0,
        "running": True,
    }

    msg = await context.bot.send_message(
        chat_id=chat.id,
        text=players_text({}),
        parse_mode="Markdown",
        reply_markup=join_kb(chat.id)
    )
    games[chat.id]["join_message_id"] = msg.message_id

    asyncio.create_task(game_loop(chat.id, context.bot))

async def game_loop(chat_id, bot):
    game = games.get(chat_id)
    if not game:
        return

    # ── رسائل العداد كل 40 ثانية ──
    for remaining in [140, 100, 60, 20]:
        await asyncio.sleep(40)
        game = games.get(chat_id)
        if not game or not game["running"] or game["phase"] != "joining":
            return

        count = len(game["players"])
        await bot.send_message(
            chat_id=chat_id,
            text=f"⏳ *بقي {remaining} ثانية حتى بداية اللعبة!*\n"
                 f"👥 المشاركون: *{count}*\n\n👇 اضغط للانضمام",
            parse_mode="Markdown",
            reply_markup=join_kb(chat_id)
        )

    # ── انتهى وقت التسجيل ──
    game = games.get(chat_id)
    if not game or not game["running"]:
        return

    players = game["players"]

    if len(players) < 3:
        await bot.send_message(
            chat_id=chat_id,
            text="❌ *انتهى وقت التسجيل!*\nيحتاج 3 لاعبين على الأقل.",
            parse_mode="Markdown"
        )
        games.pop(chat_id, None)
        return

    # ── اختر المطارد ──
    pids = list(players.keys())
    hunter_id = random.choice(pids)
    game["hunter_id"] = hunter_id
    game["hunter_mistakes"] = 0

    for pid in pids:
        players[pid].update({
            "alive": True, "location": None,
            "role": "hunter" if pid == hunter_id else "hider"
        })

    # ── أخبر المطارد بالانتظار ──
    try:
        await bot.send_message(
            chat_id=hunter_id,
            text="🕵️ *أنت المطارد!*\n\n⏳ انتظر 30 ثانية حتى يختبأ الآخرون...",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Hunter notify error: {e}")

    # ── أرسل للمختبئين أماكن الاختباء ──
    for pid in pids:
        if players[pid]["role"] == "hider":
            try:
                spots = random.sample(HIDING_SPOTS, 5)
                kb = [[InlineKeyboardButton(s, callback_data=f"hide_{chat_id}_{s}")] for s in spots]
                await bot.send_message(
                    chat_id=pid,
                    text="🙈 *أنت مختبئ!*\n\n⏰ لديك 30 ثانية للاختباء!\nاختر مكانك:",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(kb)
                )
            except Exception as e:
                logger.error(f"Hider notify error {pid}: {e}")

    # ── انتظر 30 ثانية للاختباء ──
    await asyncio.sleep(30)

    game = games.get(chat_id)
    if not game or not game["running"]:
        return

    game["phase"] = "playing"

    # ── أعلن في المجموعة ──
    hunter_name = players[hunter_id]["name"]
    hiders_text = "\n".join([f"• {players[p]['name']}" for p in pids if p != hunter_id])

    await bot.send_message(
        chat_id=chat_id,
        text=f"🎮 *بدأت اللعبة!*\n\n"
             f"🕵️ *المطارد:* {hunter_name}\n\n"
             f"🙈 *المختبئون:*\n{hiders_text}\n\n"
             f"🏁 المطارد يبدأ الآن!",
        parse_mode="Markdown"
    )

    # ── أرسل قائمة المطارد ──
    try:
        await send_hunter_menu(bot, chat_id, hunter_id)
    except Exception as e:
        logger.error(f"Hunter menu error: {e}")

async def send_hunter_menu(bot, chat_id, hunter_id):
    if chat_id not in games:
        return
    game = games[chat_id]
    hiders = [(pid, game["players"][pid]["name"]) for pid in game["players"]
              if game["players"][pid]["role"] == "hider" and game["players"][pid]["alive"]]
    kb = [[InlineKeyboardButton(f"🎯 {name}", callback_data=f"hunt_{chat_id}_{pid}")] for pid, name in hiders]
    m = game["hunter_mistakes"]
    await bot.send_message(
        chat_id=hunter_id,
        text=f"🕵️ *أنت المطارد!*\n\n❌ الأخطاء: *{m}/3*\n\nاختر شخصاً لتطارده:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb)
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    user = q.from_user
    data = q.data
    await q.answer()

    # ── انضمام ──
    if data.startswith("join_"):
        chat_id = int(data.split("_")[1])
        if chat_id not in games:
            await q.answer("❌ لا توجد لعبة!", show_alert=True)
            return
        game = games[chat_id]
        if game["phase"] != "joining":
            await q.answer("❌ انتهى وقت التسجيل!", show_alert=True)
            return
        if user.id in game["players"]:
            await q.answer("✅ أنت مسجل بالفعل!", show_alert=True)
            return

        game["players"][user.id] = {"name": user.first_name, "role": None, "location": None, "alive": True}

        try:
            await context.bot.send_message(
                chat_id=user.id,
                text="✅ *تم تسجيلك في لعبة 𝗬𝗢𝗛𝗔𝗡!*\n\nانتظر بدء اللعبة 🎮",
                parse_mode="Markdown"
            )
        except:
            game["players"].pop(user.id, None)
            await q.answer("⚠️ ابدأ محادثة مع البوت @GSKFNBOT أولاً!", show_alert=True)
            return

        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=game["join_message_id"],
                text=players_text(game["players"]),
                parse_mode="Markdown",
                reply_markup=join_kb(chat_id)
            )
        except Exception as e:
            logger.error(f"Edit error: {e}")

    # ── مطارد يختار ──
    elif data.startswith("hunt_"):
        parts = data.split("_")
        chat_id, target_id = int(parts[1]), int(parts[2])
        if chat_id not in games: return
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
                games.pop(chat_id, None)
            else:
                await send_hunter_menu(context.bot, chat_id, user.id)
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
                games.pop(chat_id, None)
                return

            await q.edit_message_text(
                f"❌ *أخطأت!* ({m}/3)\n{target['name']} لم يكن هناك!\nانتظر دقيقة...",
                parse_mode="Markdown"
            )
            try:
                await context.bot.send_message(target_id, "⚠️ *المطارد يبحث عنك! غيّر مكانك!*", parse_mode="Markdown")
                spots = random.sample(HIDING_SPOTS, 5)
                kb = [[InlineKeyboardButton(s, callback_data=f"hide_{chat_id}_{s}")] for s in spots]
                await context.bot.send_message(
                    target_id, "⚠️ *غيّر مكانك بسرعة!*\nاختر مكان اختبائك:",
                    parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb)
                )
            except: pass

            asyncio.create_task(wait_hunter(chat_id, user.id, context.bot))

    # ── مختبئ يختار مكان ──
    elif data.startswith("hide_"):
        parts = data.split("_", 2)
        chat_id, spot = int(parts[1]), parts[2]
        if chat_id not in games: return
        game = games[chat_id]
        if user.id not in game["players"]: return
        if game["players"][user.id]["role"] != "hider": return
        old = game["players"][user.id]["location"]
        game["players"][user.id]["location"] = spot
        txt = f"✅ *غيّرت مكانك إلى:* {spot} 🙈" if old else f"✅ *اخترت الاختباء في:* {spot} 🙈"
        await q.edit_message_text(txt, parse_mode="Markdown")

async def wait_hunter(chat_id, hunter_id, bot):
    await asyncio.sleep(60)
    if chat_id not in games: return
    await bot.send_message(chat_id=hunter_id, text="⏰ *انتظر انتهى! حاول مجدداً:*", parse_mode="Markdown")
    await send_hunter_menu(bot, chat_id, hunter_id)

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
    games[chat.id]["running"] = False
    games.pop(chat.id, None)
    await update.message.reply_text("🛑 *تم إنهاء اللعبة!*", parse_mode="Markdown")

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("newgame", new_game))
    app.add_handler(CommandHandler("endgame", end_game))
    app.add_handler(CallbackQueryHandler(button_handler))
    print("🕵️ بوت YOHAN يعمل...", flush=True)
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
