import logging
import asyncio
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    ContextTypes
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = "8779896667:AAEwivan1ZXUI_Y5qt5eoBiu1uW7lCTN6B8"
BOT_USERNAME = "GSKFNBOT"  # ← غيّر هذا لاسم البوت الحقيقي

HIDING_SPOTS = [
    "🌲 الغابة", "🏚️ المستودع القديم", "⛪ الكنيسة المهجورة",
    "🚢 السفينة الغارقة", "🏔️ الكهف الجبلي", "🏭 المصنع المهجور",
    "🌾 حقل القمح", "🏠 المنزل المسكون", "🚉 محطة القطار", "🌊 الشاطئ الخفي",
]

games = {}
GAME_DURATION = 180  # 3 دقائق

def build_join_message(chat_id, players, seconds_left):
    player_list = "\n".join([f"• {p['name']}" for p in players.values()]) if players else "لا يوجد مشاركين بعد"
    join_url = f"https://t.me/{BOT_USERNAME}?start=join_{chat_id}"
    keyboard = [[InlineKeyboardButton("✋ Join", url=join_url)]]
    text = (
        f"🕵️ *𝗬𝗢𝗛𝗔𝗡 - لعبة الغموضية!*\n\n"
        f"⏳ بقي *{seconds_left}* ثانية حتى بداية اللعبة\n\n"
        f"👥 *#players: {len(players)}*\n{player_list}\n\n"
        f"👇 اضغط هنا للانضمام"
    )
    return text, InlineKeyboardMarkup(keyboard)

# ── /start في الخاص ──
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user

    if chat.type == "private" and context.args and context.args[0].startswith("join_"):
        chat_id = int(context.args[0].split("_")[1])

        if chat_id not in games:
            await update.message.reply_text("❌ لا توجد لعبة نشطة!")
            return

        if games[chat_id]["phase"] != "joining":
            await update.message.reply_text("❌ انتهى وقت التسجيل!")
            return

        if user.id in games[chat_id]["players"]:
            await update.message.reply_text("✅ أنت مسجل بالفعل! انتظر بدء اللعبة 🎮")
            return

        games[chat_id]["players"][user.id] = {
            "name": user.first_name,
            "role": None,
            "location": None,
            "alive": True,
        }

        await update.message.reply_text(
            f"✅ *تم تسجيلك بنجاح!*\n\nانتظر بدء اللعبة وستصلك رسالة بدورك 🎮",
            parse_mode="Markdown"
        )

        # حدّث رسالة المجموعة
        game = games[chat_id]
        elapsed = GAME_DURATION - game["seconds_left"]
        seconds_left = max(0, game["seconds_left"])
        text, keyboard = build_join_message(chat_id, game["players"], seconds_left)
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=game["join_message_id"],
                text=text,
                parse_mode="Markdown",
                reply_markup=keyboard
            )
        except:
            pass

    elif chat.type == "private":
        await update.message.reply_text(
            "𝗬𝗢𝗛𝗔𝗡 🕵️\n\nبوت لعبة الغموضية!\nاطلب من مسؤول المجموعة تفعيل اللعبة بأمر /newgame"
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
        "phase": "joining",
        "players": {},
        "hunter_id": None,
        "join_message_id": None,
        "admin_id": user.id,
        "chat_id": chat.id,
        "seconds_left": GAME_DURATION,
    }

    text, keyboard = build_join_message(chat.id, {}, GAME_DURATION)
    msg = await update.message.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)
    games[chat.id]["join_message_id"] = msg.message_id

    # رسالة كل 40 ثانية
    context.job_queue.run_repeating(
        update_join_message,
        interval=40,
        first=40,
        data={"chat_id": chat.id},
        name=f"timer_{chat.id}"
    )

    # انتهاء التسجيل بعد 3 دقائق
    context.job_queue.run_once(
        end_joining_phase,
        when=GAME_DURATION,
        data={"chat_id": chat.id},
        name=f"end_join_{chat.id}"
    )

# ── تحديث رسالة الانضمام كل 40 ثانية ──
async def update_join_message(context: ContextTypes.DEFAULT_TYPE):
    data = context.job.data
    chat_id = data["chat_id"]

    if chat_id not in games or games[chat_id]["phase"] != "joining":
        context.job.schedule_removal()
        return

    game = games[chat_id]
    game["seconds_left"] = max(0, game["seconds_left"] - 40)
    seconds_left = game["seconds_left"]

    text, keyboard = build_join_message(chat_id, game["players"], seconds_left)

    # أرسل رسالة جديدة
    try:
        new_msg = await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        # احذف الرسالة القديمة
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=game["join_message_id"])
        except:
            pass
        game["join_message_id"] = new_msg.message_id
    except Exception as e:
        logger.error(f"Error updating join message: {e}")

# ── انتهاء مرحلة التسجيل ──
async def end_joining_phase(context: ContextTypes.DEFAULT_TYPE):
    data = context.job.data
    chat_id = data["chat_id"]

    if chat_id not in games:
        return

    game = games[chat_id]
    players = game["players"]

    for job_name in [f"timer_{chat_id}"]:
        for job in context.job_queue.get_jobs_by_name(job_name):
            job.schedule_removal()

    if len(players) < 3:
        await context.bot.send_message(
            chat_id=chat_id,
            text="❌ *انتهى وقت التسجيل!*\nعدد اللاعبين غير كافٍ (يحتاج 3+).\nاستخدم /newgame للبدء.",
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

# ── قائمة الطارد ──
async def send_hunter_menu(context, chat_id, hunter_id):
    game = games[chat_id]
    players = game["players"]
    hiders = [(pid, players[pid]["name"]) for pid in players
              if players[pid]["role"] == "hider" and players[pid]["alive"]]

    keyboard = [[InlineKeyboardButton(f"🎯 {name}", callback_data=f"hunt_{chat_id}_{pid}")] for pid, name in hiders]

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
                await context.bot.send_message(chat_id=target_id, text=f"😱 *تم القبض عليك في {target_location}!*\nأنت خارج.", parse_mode="Markdown")
            except:
                pass

            alive_hiders = [pid for pid, p in game["players"].items() if p["role"] == "hider" and p["alive"]]
            if not alive_hiders:
                await context.bot.send_message(chat_id=chat_id, text="🏆 *انتهت اللعبة! الطارد فاز!* 🕵️", parse_mode="Markdown")
                games.pop(chat_id, None)
            else:
                await send_hunter_menu(context, chat_id, user.id)
        else:
            await query.edit_message_text(f"❌ *أخطأت!*\n\n{target['name']} لم يكن هناك!\nانتظر دقيقة...", parse_mode="Markdown")
            try:
                await context.bot.send_message(chat_id=target_id, text="⚠️ *الطارد يبحث عنك! غيّر مكانك!*", parse_mode="Markdown")
                await send_hider_menu(context, chat_id, target_id, is_change=True)
            except:
                pass
            context.job_queue.run_once(resend_hunter_menu, when=60, data={"chat_id": chat_id, "hunter_id": user.id}, name=f"hunter_wait_{chat_id}")

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
