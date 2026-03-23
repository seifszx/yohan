import logging
import random
import asyncio
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

def players_text(players):
    names = "\n".join([f"• {p['name']}" for p in players.values()]) if players else "—"
    return (
        f"🕵️ *𝗬𝗢𝗛𝗔𝗡 - لعبة الغموضية!*\n\n"
        f"👥 *#players: {len(players)}*\n{names}"
    )

def join_keyboard(chat_id):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✋ الانضمام للعبة", callback_data=f"join_{chat_id}")
    ]])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return
    await update.message.reply_text(
        "🕵️ *أهلاً في 𝗬𝗢𝗛𝗔𝗡!*\n\n"
        "بوت لعبة الغموضية الجماعية!\n\n"
        "📌 لبدء اللعبة أضف البوت لمجموعتك ثم اكتب /newgame",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("➕ إضافة يوهان للمجموعة",
                                 url=f"https://t.me/{BOT_USERNAME}?startgroup=start")
        ]])
    )

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

    games[chat.id] = {
        "phase": "joining",
        "players": {},
        "hunter_id": None,
        "join_message_id": None,
        "seconds_left": GAME_DURATION,
        "hunter_mistakes": 0,
        "chat_id": chat.id,
    }

    msg = await context.bot.send_message(
        chat_id=chat.id,
        text=players_text({}),
        parse_mode="Markdown",
        reply_markup=join_keyboard(chat.id)
    )
    games[chat.id]["join_message_id"] = msg.message_id

    # شغّل العداد كـ asyncio task مباشرة
    asyncio.create_task(game_timer(chat.id, context))

async def game_timer(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    """عداد اللعبة - يرسل رسالة كل 40 ثانية وينهي التسجيل بعد 3 دقائق"""
    elapsed = 0
    interval = 40

    while elapsed < GAME_DURATION:
        await asyncio.sleep(interval)
        elapsed += interval

        if chat_id not in games or games[chat_id]["phase"] != "joining":
            return

        game = games[chat_id]
        remaining = max(0, GAME_DURATION - elapsed)
        count = len(game["players"])

        await context.bot.send_message(
            chat_id=chat_id,
            text=f"⏳ *بقي {remaining} ثانية حتى بداية اللعبة!*\n"
                 f"👥 المشاركون: *{count}*\n\n"
                 f"👇 اضغط للانضمام",
            parse_mode="Markdown",
            reply_markup=join_keyboard(chat_id)
        )

    # انتهى الوقت - ابدأ اللعبة
    if chat_id in games and games[chat_id]["phase"] == "joining":
        await start_game(chat_id, context)

async def start_game(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    """بدء اللعبة الفعلية"""
    if chat_id not in games:
        return

    game = games[chat_id]
    players = game["players"]

    if len(players) < 3:
        await context.bot.send_message(
            chat_id=chat_id,
            text="❌ *انتهى وقت التسجيل!*\n"
                 "يحتاج 3 لاعبين على الأقل.\n"
                 "استخدم /newgame للبدء من جديد.",
            parse_mode="Markdown"
        )
        games.pop(chat_id, None)
        return

    pids = list(players.keys())
    hunter_id = random.choice(pids)
    game["hunter_id"] = hunter_id
    game["phase"] = "playing"
    game["hunter_mistakes"] = 0

    for pid in pids:
        players[pid].update({
            "alive": True,
            "location": None,
            "role": "hunter" if pid == hunter_id else "hider"
        })

    hunter_name = players[hunter_id]["name"]
    hiders = [players[pid]["name"] for pid in pids if pid != hunter_id]
    hiders_text = "\n".join([f"• {n}" for n in hiders])

    # أعلن في المجموعة من هو المطارد
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"🎮 *بدأت اللعبة!*\n\n"
             f"🕵️ *المطارد:* {hunter_name}\n\n"
             f"🙈 *المختبئون:*\n{hiders_text}\n\n"
             f"📱 تفقد رسائلك الخاصة مع البوت!",
        parse_mode="Markdown"
    )

    # أرسل لكل لاعب دوره في الخاص
    for pid in pids:
        try:
            if players[pid]["role"] == "hunter":
                await send_hunter_menu(context, chat_id, pid)
            else:
                await send_hider_menu(context, chat_id, pid)
        except Exception as e:
            logger.error(f"Error sending role {pid}: {e}")

async def send_hunter_menu(context, chat_id, hunter_id):
    game = games[chat_id]
    hiders = [(pid, game["players"][pid]["name"]) for pid in game["players"]
              if game["players"][pid]["role"] == "hider" and game["players"][pid]["alive"]]
    kb = [[InlineKeyboardButton(f"🎯 {name}", callback_data=f"hunt_{chat_id}_{pid}")] for pid, name in hiders]
    m = game["hunter_mistakes"]
    await context.bot.send_message(
        chat_id=hunter_id,
        text=f"🕵️ *أنت المطارد!*\n\n"
             f"❌ الأخطاء: *{m}/3*\n\n"
             f"اختر شخصاً لتطارده:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb)
    )

async def send_hider_menu(context, chat_id, hider_id, is_change=False):
    spots = random.sample(HIDING_SPOTS, 5)
    kb = [[InlineKeyboardButton(s, callback_data=f"hide_{chat_id}_{s}")] for s in spots]
    txt = "⚠️ *غيّر مكانك بسرعة!*\n\nاختر مكان اختبائك:" if is_change else "🙈 *أنت مختبئ!*\n\nاختر مكان اختبائك:"
    await context.bot.send_message(
        chat_id=hider_id, text=txt,
        parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb)
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    user = q.from_user
    data = q.data
    await q.answer()

    # ── زر الانضمام ──
    if data.startswith("join_"):
        chat_id = int(data.split("_")[1])

        if chat_id not in games:
            await q.answer("❌ لا توجد لعبة نشطة!", show_alert=True)
            return

        game = games[chat_id]

        if game["phase"] != "joining":
            await q.answer("❌ انتهى وقت التسجيل!", show_alert=True)
            return

        if user.id in game["players"]:
            await q.answer("✅ أنت مسجل بالفعل!", show_alert=True)
            return

        game["players"][user.id] = {
            "name": user.first_name,
            "role": None, "location": None, "alive": True,
        }

        # أرسل تأكيد في الخاص
        try:
            await context.bot.send_message(
                chat_id=user.id,
                text=f"✅ *تم تسجيلك في لعبة 𝗬𝗢𝗛𝗔𝗡!*\n\n"
                     f"انتظر بدء اللعبة وستصلك رسالة بدورك 🎮",
                parse_mode="Markdown"
            )
        except Exception:
            game["players"].pop(user.id, None)
            await q.answer("⚠️ ابدأ محادثة مع البوت أولاً @GSKFNBOT", show_alert=True)
            return

        # حدّث رسالة المجموعة فوراً
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=game["join_message_id"],
                text=players_text(game["players"]),
                parse_mode="Markdown",
                reply_markup=join_keyboard(chat_id)
            )
        except Exception as e:
            logger.error(f"Edit error: {e}")

    # ── المطارد يختار ──
    elif data.startswith("hunt_"):
        parts = data.split("_")
        chat_id, target_id = int(parts[1]), int(parts[2])

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
                text=f"🎯 *تم القبض على {target['name']}!*\n"
                     f"وجده المطارد في: {loc}",
                parse_mode="Markdown"
            )
            try:
                await context.bot.send_message(
                    target_id,
                    f"😱 *تم القبض عليك في {loc}!*\nأنت خارج من اللعبة.",
                    parse_mode="Markdown"
                )
            except: pass

            alive = [p for p in game["players"].values() if p["role"] == "hider" and p["alive"]]
            if not alive:
                await context.bot.send_message(
                    chat_id, "🏆 *انتهت اللعبة! المطارد فاز!* 🕵️",
                    parse_mode="Markdown"
                )
                games.pop(chat_id, None)
            else:
                await send_hunter_menu(context, chat_id, user.id)

        else:
            game["hunter_mistakes"] += 1
            m = game["hunter_mistakes"]

            if m >= 3:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="🎉 *انتهت اللعبة!*\n"
                         "أخطأ المطارد 3 مرات!\n"
                         "*المختبئون فازوا!* 🙈",
                    parse_mode="Markdown"
                )
                try:
                    await context.bot.send_message(
                        user.id, "😔 *خسرت!* أخطأت 3 مرات!",
                        parse_mode="Markdown"
                    )
                except: pass
                games.pop(chat_id, None)
                return

            await q.edit_message_text(
                f"❌ *أخطأت!* ({m}/3)\n"
                f"{target['name']} لم يكن هناك!\n"
                f"انتظر دقيقة...",
                parse_mode="Markdown"
            )
            try:
                await context.bot.send_message(
                    target_id,
                    "⚠️ *المطارد يبحث عنك! غيّر مكانك بسرعة!*",
                    parse_mode="Markdown"
                )
                await send_hider_menu(context, chat_id, target_id, is_change=True)
            except: pass

            asyncio.create_task(wait_and_resend_hunter(chat_id, user.id, context))

    # ── المختبئ يختار مكان ──
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

async def wait_and_resend_hunter(chat_id, hunter_id, context):
    await asyncio.sleep(60)
    if chat_id not in games: return
    await context.bot.send_message(
        chat_id=hunter_id,
        text="⏰ *انتهى وقت الانتظار! حاول مجدداً:*",
        parse_mode="Markdown"
    )
    await send_hunter_menu(context, chat_id, hunter_id)

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

