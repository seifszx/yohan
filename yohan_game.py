import logging
import random
import asyncio
import json
import os
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)

# ══════════════════════════════════════════════
#                 إعدادات البوت
# ══════════════════════════════════════════════
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN        = "8779896667:AAGtPzYxcko19zaDV6XIWIchtjpR655yvsQ"
BOT_USERNAME = "GSKFNBOT"
BOT_NAME     = "𝗬𝗢𝗛𝗔𝗡"

STATS_FILE   = "stats.json"
HISTORY_FILE = "history.json"

DEFAULT_JOIN_TIME     = 180
DEFAULT_ELIM_INTERVAL = 10
MAX_PLAYERS           = 50

# ══════════════════════════════════════════════
#             البيانات في الذاكرة
# ══════════════════════════════════════════════
games   = {}
stats   = {}
history = {}
member_start_allowed = {}   # { chat_id: True/False } — هل يُسمح للأعضاء ببدء اللعبة
last_winners = {}          # { chat_id: player_info } — الفائز الأخير لكل مجموعة

# ══ نظام المطاردة والاختباء ══
hunter_games = {}
# hunter_games[chat_id] = {
#   'hunter': player_info,        # المطارد
#   'players': [player_info, ...], # المشاركون العاديون
#   'hiding_spots': {},            # { player_id: [مكان1, مكان2, ...] }
#   'attempts': 0,                 # عدد محاولات المطارد الإجمالية
#   'max_attempts': 3,             # الحد الأقصى الحالي للمحاولات
#   'guessed': [],                 # اللاعبون الذين خمّن مكانهم بنجاح
#   'failed_attempts': 0,          # عدد الفشل في الجولة الحالية
# }


HIDING_SPOTS = [
    "🌲 الغابة",
    "🕳️ الكهف",
    "👻 المنزل المسكون",
    "🔪 بيت القاتل",
    "☕ المقهى المهجور",
    "🏫 خلف المدرسة",
]

# ══════════════════════════════════════════════
#           حفظ وتحميل البيانات
# ══════════════════════════════════════════════
def load_data():
    global stats, history
    for fname, container in [(STATS_FILE, 'stats'), (HISTORY_FILE, 'history')]:
        try:
            if os.path.exists(fname):
                with open(fname, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if container == 'stats':
                    stats.update(data)
                else:
                    history.update(data)
        except Exception as e:
            logger.error(f"load {fname}: {e}")

def save_data():
    try:
        with open(STATS_FILE,   'w', encoding='utf-8') as f:
            json.dump(stats,   f, ensure_ascii=False, indent=2)
        with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"save: {e}")

def get_stats(user_id):
    uid = str(user_id)
    if uid not in stats:
        stats[uid] = {'games': 0, 'wins': 0, 'name': '', 'username': '', 'last': ''}
    return stats[uid]

def record_join(user):
    s = get_stats(user.id)
    s['games']   += 1
    s['name']     = user.first_name
    s['username'] = user.username or ''
    s['last']     = datetime.now().strftime('%Y-%m-%d %H:%M')
    save_data()

def record_win(user_id, chat_id=None, player_info=None):
    get_stats(user_id)['wins'] += 1
    if chat_id and player_info:
        last_winners[str(chat_id)] = player_info
    save_data()

def add_history(chat_id, winner_name, count):
    cid = str(chat_id)
    if cid not in history:
        history[cid] = []
    history[cid].insert(0, {
        'winner':  winner_name,
        'players': count,
        'date':    datetime.now().strftime('%Y-%m-%d %H:%M')
    })
    history[cid] = history[cid][:10]
    save_data()

# ══════════════════════════════════════════════
#                دوال مساعدة
# ══════════════════════════════════════════════
def fmt(player: dict) -> str:
    return f"[{player['first_name']}](tg://user?id={player['id']})"

async def is_admin(chat, user_id: int) -> bool:
    try:
        admins = await chat.get_administrators()
        return user_id in [a.user.id for a in admins]
    except:
        return False

async def get_photo_url(bot, user_id: int):
    """جلب صورة المستخدم الشخصية"""
    try:
        photos = await bot.get_user_profile_photos(user_id, limit=1)
        if photos.total_count > 0:
            file = await photos.photos[0][-1].get_file()
            return file.file_path
    except:
        pass
    return None

def join_keyboard(game_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("➕ انضم للعبة", callback_data=f"join_{game_id}")
    ]])

def build_joining_text(game: dict) -> str:
    players  = game['players']
    count    = len(players)
    interval = game.get('elim_interval', DEFAULT_ELIM_INTERVAL)
    names    = "\n".join([f"  {i+1}. {fmt(p)}" for i, p in enumerate(players)]) if players else "  _لا يوجد لاعبون بعد_"
    return (
        f"🎮 **{BOT_NAME} — جولة جديدة!**\n\n"
        f"📋 **قائمة المشاركين ({count}):**\n"
        f"{names}\n\n"
        f"⚡ الإقصاء كل **{interval} ثوانٍ**\n"
        f"━━━━━━━━━━━━━━━\n"
        f"اضغط الزر للانضمام 👇"
    )

def build_hunting_text(game: dict) -> str:
    players  = game['players']
    count    = len(players)
    interval = game.get('elim_interval', DEFAULT_ELIM_INTERVAL)
    names    = "\n".join([f"  {i+1}. {fmt(p)}" for i, p in enumerate(players)]) if players else ""
    return (
        f"🕵️ **{BOT_NAME} — المطاردة جارية!**\n\n"
        f"👥 **المتبقون ({count}):**\n"
        f"{names}\n\n"
        f"⚡ يُقصى لاعب كل **{interval} ثوانٍ**"
    )



# ══════════════════════════════════════════════
#    الأحداث المفاجئة — تعريفها وتنفيذها
# ══════════════════════════════════════════════
RANDOM_EVENTS = [
    {
        'name':  '⚡ زلزال مفاجئ!',
        'desc':  'اهتزت الأرض... يُقصى لاعبان دفعة واحدة!',
        'type':  'double_elim',
    },
    {
        'name':  '🛡 درع الحماية!',
        'desc':  'لاعب عشوائي حصل على حصانة للجولة القادمة!',
        'type':  'shield',
    },
    {
        'name':  '🔀 الفوضى العارمة!',
        'desc':  'تم إعادة ترتيب قائمة اللاعبين عشوائياً!',
        'type':  'shuffle',
    },
    {
        'name':  '⏩ تسارع المطاردة!',
        'desc':  'الإقصاء أصبح أسرع! كل 5 ثوانٍ الآن!',
        'type':  'speedup',
    },
    {
        'name':  '❄️ تجميد!',
        'desc':  'توقفت المطاردة 15 ثانية... استعد!',
        'type':  'freeze',
    },
    {
        'name':  '💀 الموت المزدوج!',
        'desc':  'الأول والأخير في القائمة يخرجان معاً!',
        'type':  'first_last',
    },
]

async def trigger_random_event(game_id: int, context, chat_id: int, msg_id: int):
    """تنفيذ حدث مفاجئ عشوائي"""
    if game_id not in games:
        return

    game    = games[game_id]
    players = game['players']

    if len(players) < 2:
        return

    event = random.choice(RANDOM_EVENTS)

    await context.bot.send_message(
        chat_id=chat_id,
        text=f"🎲 **حدث مفاجئ!**\n\n{event['name']}\n_{event['desc']}_",
        parse_mode='Markdown'
    )
    await asyncio.sleep(2)

    if event['type'] == 'double_elim':
        # إقصاء لاعبين دفعة واحدة
        if len(players) >= 2:
            e1 = random.choice(players)
            players.remove(e1)
            e2 = random.choice(players)
            players.remove(e2)
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"💥 خرج {fmt(e1)} و {fmt(e2)} معاً!",
                parse_mode='Markdown'
            )
            for p in [e1, e2]:
                try:
                    await context.bot.send_message(
                        chat_id=p['id'],
                        text=f"💥 **{BOT_NAME}**: أُقصيت بسبب الزلزال المفاجئ في **{game['chat_title']}**!",
                        parse_mode='Markdown'
                    )
                except:
                    pass

    elif event['type'] == 'shield':
        lucky = random.choice(players)
        game.setdefault('vip_players', []).append(lucky['id'])
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"🛡 {fmt(lucky)} محمي في الجولة القادمة!",
            parse_mode='Markdown'
        )

    elif event['type'] == 'shuffle':
        random.shuffle(players)
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"🔀 تم إعادة الترتيب!",
            parse_mode='Markdown'
        )

    elif event['type'] == 'speedup':
        game['elim_interval'] = max(5, game.get('elim_interval', DEFAULT_ELIM_INTERVAL) - 5)
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"⏩ السرعة الجديدة: كل **{game['elim_interval']} ثوانٍ**!",
            parse_mode='Markdown'
        )

    elif event['type'] == 'freeze':
        await asyncio.sleep(15)
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"▶️ انتهى التجميد! استمرت المطاردة.",
            parse_mode='Markdown'
        )

    elif event['type'] == 'first_last':
        if len(players) >= 2:
            first = players[0]
            last  = players[-1]
            players.remove(first)
            if last in players:
                players.remove(last)
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"💀 {fmt(first)} و {fmt(last)} خرجا معاً!",
                parse_mode='Markdown'
            )
            for p in [first, last]:
                try:
                    await context.bot.send_message(
                        chat_id=p['id'],
                        text=f"💀 **{BOT_NAME}**: أُقصيت بالحدث المفاجئ في **{game['chat_title']}**!",
                        parse_mode='Markdown'
                    )
                except:
                    pass

    # تحديث الرسالة
    try:
        await context.bot.edit_message_text(
            chat_id=chat_id, message_id=msg_id,
            text=build_hunting_text(game),
            parse_mode='Markdown'
        )
    except:
        pass

# ══════════════════════════════════════════════
#         /start — مجموعة وخاص
# ══════════════════════════════════════════════
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user

    if chat.type == 'private':
        await update.message.reply_text(
            f"👋 مرحباً **{user.first_name}**!\n\n"
            f"أهلاً بك في بوت **{BOT_NAME}** للغميضة 🙈\n\n"
            f"🎮 **كيف تعمل اللعبة؟**\n"
            f"  • الأدمن يبدأ جولة في المجموعة\n"
            f"  • تضغط زر الانضمام وتنضم فوراً\n"
            f"  • كل مُقصى يستلم إشعاراً هنا بالخاص\n"
            f"  • آخر لاعب يبقى يفوز 🏆\n\n"
            f"أضف البوت لمجموعتك واكتب /start!\n\n"
            f"/help — قائمة الأوامر\n"
            f"/panel — لوحة تحكم الأدمن",
            parse_mode='Markdown'
        )
        return

    if not await is_admin(chat, user.id):
        await update.message.reply_text(f"❌ {BOT_NAME}: المشرفون فقط يمكنهم بدء اللعبة.")
        return

    game_id = chat.id
    if game_id in games and games[game_id]['active']:
        await update.message.reply_text(f"⚠️ {BOT_NAME}: توجد لعبة نشطة! استخدم /end أو /panel.")
        return

    join_time = DEFAULT_JOIN_TIME
    if context.args:
        try:
            join_time = max(20, min(300, int(context.args[0])))
        except:
            pass

    await create_new_game(update, context, chat, join_time)

async def create_new_game(update_or_query, context, chat, join_time):
    """إنشاء جولة جديدة — يُستخدم من /start ومن لوحة التحكم"""
    game_id = chat.id

    # تسجيل الفائز السابق تلقائياً
    prev_winner = last_winners.get(str(game_id))
    initial_players = [prev_winner] if prev_winner else []

    games[game_id] = {
        'players':          initial_players,
        'active':           True,
        'phase':            'joining',
        'join_time':        join_time,
        'elim_interval':    DEFAULT_ELIM_INTERVAL,
        'message_id':       None,
        'elimination_task': None,
        'total_players':    0,
        'round_num':        0,
        'chat_title':       chat.title or 'المجموعة',
        'vip_players':      [],
        'invite_link':      None,
    }

    # محاولة إنشاء رابط دعوة
    try:
        link = await context.bot.create_chat_invite_link(
            chat_id=game_id,
            name=f"دعوة {BOT_NAME}",
            creates_join_request=False
        )
        games[game_id]['invite_link'] = link.invite_link
    except:
        pass

    # إشعار الفائز السابق بتسجيله تلقائياً
    if prev_winner:
        try:
            await context.bot.send_message(
                chat_id=prev_winner['id'],
                text=(
                    f"🏆 **{BOT_NAME}**: تم تسجيلك تلقائياً في الجولة الجديدة بـ **{chat.title}**!\n"
                    f"فائز الجولة السابقة يدخل مباشرة 😎"
                ),
                parse_mode='Markdown'
            )
        except:
            pass

    keyboard = join_keyboard(game_id)

    if hasattr(update_or_query, 'message') and update_or_query.message:
        msg = await update_or_query.message.reply_text(
            build_joining_text(games[game_id]),
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
    else:
        msg = await context.bot.send_message(
            chat_id=game_id,
            text=build_joining_text(games[game_id]),
            reply_markup=keyboard,
            parse_mode='Markdown'
        )

    games[game_id]['message_id'] = msg.message_id

    asyncio.create_task(
        joining_countdown(game_id, context, game_id, join_time, msg.message_id)
    )

# ══════════════════════════════════════════════
#          العد التنازلي
# ══════════════════════════════════════════════
async def joining_countdown(game_id, context, chat_id, join_time, msg_id):
    try:
        elapsed        = 0
        send_interval  = 30   # كل 30 ثانية يُرسل رسالة جديدة

        while elapsed < join_time:
            await asyncio.sleep(send_interval)
            elapsed += send_interval

            if game_id not in games or not games[game_id]['active']:
                return

            remaining = max(0, join_time - elapsed)
            game      = games[game_id]

            if remaining <= 0:
                break

            # تحويل الثواني لدقائق:ثواني
            mins = remaining // 60
            secs = remaining % 60
            if mins > 0:
                time_str = f"{mins} دقيقة و{secs} ثانية" if secs else f"{mins} دقيقة"
            else:
                time_str = f"{secs} ثانية"

            # حذف الرسالة القديمة وإرسال رسالة جديدة
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
            except:
                pass

            try:
                new_msg = await context.bot.send_message(
                    chat_id=chat_id,
                    text=build_joining_text(game) + f"\n\n⏰ **تبقى: {time_str}**",
                    reply_markup=join_keyboard(game_id),
                    parse_mode='Markdown'
                )
                msg_id = new_msg.message_id
                games[game_id]['message_id'] = msg_id
            except Exception as e:
                logger.warning(f"send new countdown msg: {e}")

        if game_id not in games or not games[game_id]['active']:
            return

        await start_elimination_phase(game_id, context, chat_id, msg_id)

    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"joining_countdown: {e}")

# ══════════════════════════════════════════════
#         بدء مرحلة المطاردة
# ══════════════════════════════════════════════
async def start_elimination_phase(game_id, context, chat_id, msg_id):
    if game_id not in games:
        return

    game    = games[game_id]
    players = game['players']

    if len(players) == 0:
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id, message_id=msg_id,
                text=f"❌ **{BOT_NAME}**: لم ينضم أحد. تم إلغاء الجولة.",
                parse_mode='Markdown'
            )
        except:
            pass
        del games[game_id]
        return

    if len(players) == 1:
        p = players[0]
        record_win(p['id'])
        add_history(chat_id, p['first_name'], 1)
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id, message_id=msg_id,
                text=f"🏆 **{BOT_NAME}**: الفائز هو {fmt(p)}!\n_(اللاعب الوحيد)_",
                parse_mode='Markdown'
            )
        except:
            pass
        del games[game_id]
        return

    game['phase']         = 'hunting'
    game['total_players'] = len(players)
    random.shuffle(players)

    # ══ اختيار مطارد عشوائي وبدء لعبة الاختباء ══
    await start_hunter_game(game_id, context, chat_id, msg_id, players)


async def start_hunter_game(game_id, context, chat_id, msg_id, players):
    """اختيار مطارد عشوائي وإرسال التعليمات لكل طرف"""
    all_players = list(players)
    hunter = random.choice(all_players)
    normal_players = [p for p in all_players if p['id'] != hunter['id']]

    # تهيئة بيانات لعبة المطاردة
    hunter_games[chat_id] = {
        'hunter':         hunter,
        'players':        normal_players,
        'hiding_spots':   {},   # player_id -> spot (string)
        'attempts':       0,
        'max_attempts':   3,
        'failed_guesses': 0,
        'guessed':        [],
        'active':         True,
        'chat_title':     games[game_id]['chat_title'] if game_id in games else '',
        'msg_id':         msg_id,
    }

    # إعلان في المجموعة
    hunter_names = "\n".join([f"  • {fmt(p)}" for p in normal_players])
    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg_id,
            text=(
                f"🕵️ **{BOT_NAME} — لعبة المطاردة والاختباء!**\n\n"
                f"🔴 **المطارد:** {fmt(hunter)}\n\n"
                f"🫣 **المختبئون:**\n{hunter_names}\n\n"
                f"📬 تم إرسال التعليمات للجميع في الخاص!\n"
                f"المطارد يحاول معرفة أماكن الاختباء 🔍"
            ),
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.warning(f"hunter game announcement: {e}")
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                f"🕵️ **{BOT_NAME} — لعبة المطاردة!**\n\n"
                f"🔴 المطارد: {fmt(hunter)}\n"
                f"المختبئون تلقوا تعليماتهم في الخاص!"
            ),
            parse_mode='Markdown'
        )

    await asyncio.sleep(1)

    # ═══ إرسال رسائل خاصة للمختبئين ═══
    for player in normal_players:
        player_spots = list(HIDING_SPOTS)
        hunter_games[chat_id]['hiding_spots'][player['id']] = {
            'options': player_spots,
            'chosen':  None,
        }
        buttons = [
            [InlineKeyboardButton(spot, callback_data=f"hide|{chat_id}|{player['id']}|{j}")]
            for j, spot in enumerate(player_spots)
        ]
        try:
            await context.bot.send_message(
                chat_id=player['id'],
                text=(
                    f"🫣 **{BOT_NAME} — اختر مكان اختبائك!**\n\n"
                    f"🔴 المطارد هو: **{hunter['first_name']}**\n\n"
                    f"اختر أحد الأماكن للاختباء فيه:\n"
                    f"_(اختر بسرعة قبل أن يجدك!)_ 🏃"
                ),
                reply_markup=InlineKeyboardMarkup(buttons),
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"[HIDING SPOT FAILED] to {player['first_name']} id={player['id']}: {e}")
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"⚠️ {BOT_NAME}: فشل إرسال الأماكن لـ {player['first_name']} — يجب أن يبدأ محادثة مع البوت أولاً",
                    parse_mode='Markdown'
                )
            except:
                pass

    await asyncio.sleep(1)

    # ═══ إرسال رسالة خاصة للمطارد ═══
    player_buttons = [
        [InlineKeyboardButton(f"👤 {p['first_name']}", callback_data=f"huntpick|{chat_id}|{p['id']}")]
        for p in normal_players
    ]
    hunter_sent = False
    try:
        await context.bot.send_message(
            chat_id=hunter['id'],
            text=(
                f"🕵️ **{BOT_NAME} — أنت المطارد!**\n\n"
                f"مهمتك: اكتشف أين يختبئ كل لاعب 🔍\n\n"
                f"👥 **المختبئون:**\n" +
                "\n".join([f"  • {p['first_name']}" for p in normal_players]) +
                f"\n\n⚠️ لديك **{hunter_games[chat_id]['max_attempts']} محاولات فقط**\n"
                f"• إذا فشلت: يفوز المشاركون ❌\n"
                f"• إذا نجحت في تخمين الكل: +3 محاولات إضافية ✅\n\n"
                f"اختر لاعباً لتخمين مكانه 👇"
            ),
            reply_markup=InlineKeyboardMarkup(player_buttons),
            parse_mode='Markdown'
        )
        hunter_sent = True
    except Exception as e:
        logger.error(f"send hunter message FAILED for {hunter['first_name']} id={hunter['id']}: {e}")

    if not hunter_sent:
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    f"⚠️ **{BOT_NAME}**: لم أستطع إرسال رسالة للمطارد {fmt(hunter)}\n\n"
                    f"يجب على المطارد أن يبدأ محادثة مع البوت أولاً:\n"
                    f"ابحث عن @{BOT_USERNAME} وأرسل /start في الخاص 👆"
                ),
                parse_mode='Markdown'
            )
        except:
            pass


async def hunter_guess_spots(chat_id, context, hunter_id, target_player_id):
    """إرسال أزرار الأماكن للمطارد ليخمن"""
    if chat_id not in hunter_games:
        return
    hg = hunter_games[chat_id]
    target = next((p for p in hg['players'] if p['id'] == target_player_id), None)
    if not target:
        return

    spot_data = hg['hiding_spots'].get(target_player_id)
    if not spot_data or not spot_data.get('options'):
        try:
            await context.bot.send_message(
                chat_id=hunter_id,
                text=f"❌ هذا اللاعب لم يختر مكاناً بعد، حاول لاحقاً."
            )
        except:
            pass
        return

    if spot_data.get('chosen') is None:
        try:
            await context.bot.send_message(
                chat_id=hunter_id,
                text=f"⏳ **{target['first_name']}** لم يختر مكانه بعد!\nانتظر قليلاً ثم حاول مجدداً.",
                parse_mode='Markdown'
            )
        except:
            pass
        return

    # عرض الأماكن الممكنة للمطارد ليخمن
    spots = spot_data['options']
    buttons = [
        [InlineKeyboardButton(f"🔍 {spot[:35]}", callback_data=f"huntguess|{chat_id}|{target_player_id}|{j}")]
        for j, spot in enumerate(spots)
    ]
    buttons.append([InlineKeyboardButton("🔙 رجوع", callback_data=f"huntback|{chat_id}")])

    try:
        await context.bot.send_message(
            chat_id=hunter_id,
            text=(
                f"🔍 **أين يختبئ {target['first_name']}؟**\n\n"
                f"اختر المكان الذي تظن أنه فيه:\n"
                f"_(المحاولات المتبقية: {hg['max_attempts'] - hg['attempts']})_"
            ),
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.warning(f"hunter guess spots: {e}")

# ══════════════════════════════════════════════
#             حلقة الإقصاء
# ══════════════════════════════════════════════
ELIM_MSGS = [
    "❌ لقيتك! {name} روح للدور الجاي 😂",
    "❌ يا حصراه على التخبيية يا {name}، هذي يديروها الدراري الصغار 😭",
    "❌ خرج خرج يا {name}.. راني نشوف في سباطك باين من تحت الباب 👟",
    "❌ يا مكبوت يا {name} يزي بلا تحلاب 😒",
    "❌ هاك هنا {name}! علابالي بلي ماتقدرش تهرب مني 😏",
    "❌ يا {name} كنت فاكر روحك زهير بن محمود؟ لقيتك 😂",
    "❌ {name} تخبا في الحمام وقعد ساعة... ولقيناه 🚽",
    "❌ سبحان الله يا {name}، حتى الظل متاعك خانك 😅",
    "❌ يا {name} قلتلك ما تاكلش بصلة وانت مخبي 🧅",
    "❌ {name} فكّر روحه نينجا... ماهوش 🥷",
    "❌ يا {name} الكل لقاك غير انت ما علمتش 💀",
    "❌ {name} قام يعدّل في شعره وهو مخبي... شافوه 😭",
]

async def elimination_loop(game_id, context, chat_id, msg_id):
    try:
        round_count = 0
        while game_id in games and games[game_id]['active']:
            game    = games[game_id]
            players = game['players']

            if len(players) <= 1:
                break

            game['round_num'] += 1
            round_count       += 1
            interval           = game.get('elim_interval', DEFAULT_ELIM_INTERVAL)
            await asyncio.sleep(interval)

            if game_id not in games:
                return

            # حدث مفاجئ عشوائي كل 4 جولات (25% احتمال)
            if round_count % 4 == 0 and random.random() < 0.5 and len(players) > 2:
                await trigger_random_event(game_id, context, chat_id, msg_id)
                if game_id not in games:
                    return
                game    = games[game_id]
                players = game['players']
                if len(players) <= 1:
                    break

            # اختيار المُقصى
            eligible  = [p for p in players if p['id'] not in game.get('vip_players', [])]
            if not eligible:
                eligible = players
            eliminated = random.choice(eligible)
            players.remove(eliminated)
            game['vip_players'] = []

            # رسالة خاصة للمُقصى
            try:
                await context.bot.send_message(
                    chat_id=eliminated['id'],
                    text=(
                        f"👀 **{BOT_NAME}**: تم العثور عليك!\n\n"
                        f"أُقصيت من **{game['chat_title']}**.\n"
                        f"تبقّى **{len(players)}** لاعب.\n\n"
                        f"حظاً أوفر! 🎮"
                    ),
                    parse_mode='Markdown'
                )
            except:
                pass

            # رسالة الإقصاء في المجموعة
            elim_text = random.choice(ELIM_MSGS).format(name=fmt(eliminated))
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"❌ {elim_text}",
                parse_mode='Markdown'
            )

            # تحديث لوحة المتبقين
            try:
                await context.bot.edit_message_text(
                    chat_id=chat_id, message_id=msg_id,
                    text=build_hunting_text(game),
                    parse_mode='Markdown'
                )
            except:
                pass

        # ═══ إعلان الفائز ═══
        if game_id not in games:
            return

        game = games[game_id]
        if not game['players']:
            del games[game_id]
            return

        winner = game['players'][0]
        total  = game['total_players']
        record_win(winner['id'], chat_id, winner)
        add_history(chat_id, winner['first_name'], total)

        # رسالة خاصة للفائز
        try:
            await context.bot.send_message(
                chat_id=winner['id'],
                text=(
                    f"🏆 **{BOT_NAME}**: مبروك!\n\n"
                    f"فزت في **{game['chat_title']}**!\n"
                    f"نجوت من **{total - 1}** لاعب 🎉\n\n"
                    f"/mystats — لعرض إحصائياتك"
                ),
                parse_mode='Markdown'
            )
        except:
            pass

        # تحديث الرسالة الرئيسية
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id, message_id=msg_id,
                text=(
                    f"🏆 **{BOT_NAME} — انتهت اللعبة!**\n\n"
                    f"🎉 الفائز: {fmt(winner)}\n"
                    f"👥 نجا من **{total - 1}** لاعب!\n\n"
                    f"_/start لجولة جديدة_ | /panel للوحة التحكم"
                ),
                parse_mode='Markdown'
            )
        except:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"🏆 **{BOT_NAME}**: الفائز {fmt(winner)} — نجا من {total-1} لاعب 🎉",
                parse_mode='Markdown'
            )

        del games[game_id]

    except asyncio.CancelledError:
        logger.info(f"elimination cancelled: {game_id}")
    except Exception as e:
        logger.error(f"elimination_loop: {e}", exc_info=True)
        if game_id in games:
            del games[game_id]

# ══════════════════════════════════════════════
#        معالج الأزرار الكامل
# ══════════════════════════════════════════════
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query   = update.callback_query
    data    = query.data
    user    = query.from_user
    chat    = query.message.chat
    chat_id = chat.id

    # ══ انضمام للعبة ══
    if data.startswith("join_"):
        try:
            game_id = int(data[5:])
        except:
            await query.answer("❌ خطأ.", show_alert=True)
            return

        if game_id not in games or not games[game_id]['active']:
            await query.answer("❌ اللعبة غير متاحة أو انتهت.", show_alert=True)
            return

        game = games[game_id]

        if game['phase'] != 'joining':
            await query.answer("⏰ انتهى وقت الانضمام!", show_alert=True)
            return

        if len(game['players']) >= MAX_PLAYERS:
            await query.answer(f"❌ الغرفة ممتلئة!", show_alert=True)
            return

        if any(p['id'] == user.id for p in game['players']):
            await query.answer("✅ أنت مشترك بالفعل!", show_alert=True)
            return

        player_info = {
            'id':         user.id,
            'first_name': user.first_name,
            'username':   user.username or '',
        }
        game['players'].append(player_info)
        record_join(user)

        await query.answer(f"✅ تم انضمامك! أنت اللاعب رقم {len(game['players'])}", show_alert=True)

        try:
            await query.edit_message_text(
                text=build_joining_text(game),
                reply_markup=join_keyboard(game_id),
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.warning(f"edit join: {e}")

        # إشعار خاص
        try:
            await context.bot.send_message(
                chat_id=user.id,
                text=(
                    f"✅ إنضممت بنجاح للعبة في: **{game['chat_title']}** 🎮\n\n"
                    f"استعد... المطاردة تبدأ قريباً!\n"
                    f"راح تجيك رسالة هنا كي يلقوك 👀"
                ),
                parse_mode='Markdown'
            )
        except:
            pass
        return

    # ══ اختيار مكان الاختباء (من المختبئ في الخاص) ══
    if data.startswith("hide|"):
        parts = data.split("|")
        try:
            hg_chat_id  = int(parts[1])
            player_id   = int(parts[2])
            spot_index  = int(parts[3])
        except:
            await query.answer("❌ خطأ.", show_alert=True)
            return

        if hg_chat_id not in hunter_games:
            await query.answer("❌ اللعبة انتهت.", show_alert=True)
            return

        hg = hunter_games[hg_chat_id]
        if player_id not in hg['hiding_spots']:
            await query.answer("❌ لست في هذه اللعبة.", show_alert=True)
            return

        spot_data = hg['hiding_spots'][player_id]
        if spot_data.get('chosen') is not None:
            await query.answer("✅ اخترت مكانك بالفعل!", show_alert=True)
            return

        chosen_spot = spot_data['options'][spot_index]
        hg['hiding_spots'][player_id]['chosen'] = chosen_spot

        await query.answer(f"✅ اخترت: {chosen_spot[:40]}", show_alert=True)
        try:
            await query.edit_message_text(
                f"✅ **{BOT_NAME}**: اخترت مكان اختبائك!\n\n"
                f"🏠 مكانك: **{chosen_spot}**\n\n"
                f"🤫 لا تخبر أحداً... انتظر المطارد! 🕵️",
                parse_mode='Markdown'
            )
        except:
            pass
        return

    # ══ المطارد يختار لاعباً ليخمن مكانه ══
    if data.startswith("huntpick|"):
        parts = data.split("|")
        try:
            hg_chat_id     = int(parts[1])
            target_player_id = int(parts[2])
        except:
            await query.answer("❌ خطأ.", show_alert=True)
            return

        if hg_chat_id not in hunter_games:
            await query.answer("❌ اللعبة انتهت.", show_alert=True)
            return

        hg = hunter_games[hg_chat_id]
        if user.id != hg['hunter']['id']:
            await query.answer("❌ لست المطارد!", show_alert=True)
            return

        if target_player_id in [p['id'] for p in hg['guessed']]:
            await query.answer("✅ هذا اللاعب تم إيجاده مسبقاً!", show_alert=True)
            return

        await query.answer("🔍 جاري عرض الأماكن...")
        await hunter_guess_spots(hg_chat_id, context, user.id, target_player_id)
        return

    # ══ المطارد يخمن المكان ══
    if data.startswith("huntguess|"):
        parts = data.split("|")
        try:
            hg_chat_id       = int(parts[1])
            target_player_id = int(parts[2])
            guess_index      = int(parts[3])
        except:
            await query.answer("❌ خطأ.", show_alert=True)
            return

        if hg_chat_id not in hunter_games:
            await query.answer("❌ اللعبة انتهت.", show_alert=True)
            return

        hg = hunter_games[hg_chat_id]
        if user.id != hg['hunter']['id']:
            await query.answer("❌ لست المطارد!", show_alert=True)
            return

        # التحقق من المحاولات
        if hg['attempts'] >= hg['max_attempts']:
            await query.answer("❌ انتهت محاولاتك!", show_alert=True)
            return

        target = next((p for p in hg['players'] if p['id'] == target_player_id), None)
        if not target:
            await query.answer("❌ اللاعب غير موجود.", show_alert=True)
            return

        spot_data = hg['hiding_spots'].get(target_player_id)
        if not spot_data or spot_data.get('chosen') is None:
            await query.answer("⏳ اللاعب لم يختر مكانه بعد!", show_alert=True)
            return

        guessed_spot = spot_data['options'][guess_index]
        correct_spot = spot_data['chosen']
        hg['attempts'] += 1

        if guessed_spot == correct_spot:
            # ✅ تخمين صحيح
            hg['guessed'].append(target)
            hg['failed_guesses'] = 0  # إعادة تصفير الفشل

            await query.answer(f"✅ صح! وجدت {target['first_name']}!", show_alert=True)

            # إشعار المجموعة
            try:
                await context.bot.send_message(
                    chat_id=hg_chat_id,
                    text=(
                        f"🎯 **{BOT_NAME}**: المطارد وجده!\n\n"
                        f"🕵️ {fmt(hg['hunter'])} وجد {fmt(target)}!\n"
                        f"🏠 كان مختبئاً في: **{correct_spot}**\n\n"
                        f"المتبقون: {len(hg['players']) - len(hg['guessed'])} لاعب"
                    ),
                    parse_mode='Markdown'
                )
            except:
                pass

            # إشعار اللاعب المكتشف
            try:
                await context.bot.send_message(
                    chat_id=target_player_id,
                    text=f"😱 **{BOT_NAME}**: اكتشفك المطارد!\nكنت في: **{correct_spot}**",
                    parse_mode='Markdown'
                )
            except:
                pass

            # هل وجد الجميع؟
            remaining = [p for p in hg['players'] if p['id'] not in [g['id'] for g in hg['guessed']]]

            if not remaining:
                # المطارد يفوز! + 3 محاولات إضافية
                hg['max_attempts'] += 3
                hg['guessed'] = []
                hg['failed_guesses'] = 0
                # إعادة تعيين الأماكن للجولة الجديدة
                for pid in hg['hiding_spots']:
                    hg['hiding_spots'][pid]['chosen'] = None
                    hg['hiding_spots'][pid]['options'] = list(HIDING_SPOTS)

                try:
                    await context.bot.send_message(
                        chat_id=hg_chat_id,
                        text=(
                            f"🏆 **{BOT_NAME}**: المطارد وجد الجميع!\n\n"
                            f"🕵️ {fmt(hg['hunter'])} فاز بالجولة!\n"
                            f"🎁 +3 محاولات إضافية للجولة القادمة!\n\n"
                            f"🔄 جولة اختباء جديدة تبدأ الآن... 🫣"
                        ),
                        parse_mode='Markdown'
                    )
                except:
                    pass

                # إرسال أماكن جديدة للمختبئين
                for player in hg['players']:
                    player_spots = list(HIDING_SPOTS)
                    buttons = [
                        [InlineKeyboardButton(spot, callback_data=f"hide|{hg_chat_id}|{player['id']}|{j}")]
                        for j, spot in enumerate(player_spots)
                    ]
                    try:
                        await context.bot.send_message(
                            chat_id=player['id'],
                            text=(
                                f"🔄 **{BOT_NAME}**: جولة جديدة!\n\n"
                                f"المطارد وجدكم جميعاً... الآن اختبئوا مجدداً!\n"
                                f"اختر مكانك 👇"
                            ),
                            reply_markup=InlineKeyboardMarkup(buttons),
                            parse_mode='Markdown'
                        )
                    except:
                        pass

                # إرسال قائمة جديدة للمطارد
                player_buttons = [
                    [InlineKeyboardButton(f"👤 {p['first_name']}", callback_data=f"huntpick|{hg_chat_id}|{p['id']}")]
                    for p in hg['players']
                ]
                try:
                    await context.bot.send_message(
                        chat_id=hg['hunter']['id'],
                        text=(
                            f"🏆 وجدت الجميع! +3 محاولات\n\n"
                            f"لديك الآن **{hg['max_attempts']}** محاولة إجمالية\n"
                            f"اختر لاعباً لتخمين مكانه 👇"
                        ),
                        reply_markup=InlineKeyboardMarkup(player_buttons),
                        parse_mode='Markdown'
                    )
                except:
                    pass
            else:
                # لا يزال هناك لاعبون، أرسل للمطارد لاختيار التالي
                player_buttons = [
                    [InlineKeyboardButton(
                        f"✅ {p['first_name']}" if p['id'] in [g['id'] for g in hg['guessed']] else f"👤 {p['first_name']}",
                        callback_data=f"huntpick|{hg_chat_id}|{p['id']}"
                    )]
                    for p in hg['players']
                ]
                remaining_count = len(remaining)
                left_attempts = hg['max_attempts'] - hg['attempts']
                try:
                    await context.bot.send_message(
                        chat_id=hg['hunter']['id'],
                        text=(
                            f"✅ أحسنت! وجدت {target['first_name']}!\n\n"
                            f"المتبقون: **{remaining_count}** لاعب\n"
                            f"المحاولات المتبقية: **{left_attempts}**\n\n"
                            f"اختر اللاعب التالي 👇"
                        ),
                        reply_markup=InlineKeyboardMarkup(player_buttons),
                        parse_mode='Markdown'
                    )
                except:
                    pass

        else:
            # ❌ تخمين خاطئ
            hg['failed_guesses'] = hg.get('failed_guesses', 0) + 1
            left_attempts = hg['max_attempts'] - hg['attempts']

            await query.answer(f"❌ خطأ! {left_attempts} محاولات متبقية", show_alert=True)

            # هل انتهت المحاولات؟
            if hg['attempts'] >= hg['max_attempts']:
                # المشاركون يفوزون!
                try:
                    await context.bot.send_message(
                        chat_id=hg_chat_id,
                        text=(
                            f"🎉 **{BOT_NAME}**: المشاركون فازوا!\n\n"
                            f"❌ المطارد {fmt(hg['hunter'])} فشل في إيجاد الجميع!\n"
                            f"نفدت محاولاته البالغة **{hg['max_attempts']}** 🏆\n\n"
                            f"🎉 مبروك للمختبئين! الجميع فاز!"
                        ),
                        parse_mode='Markdown'
                    )
                except:
                    pass

                # إشعار المطارد
                try:
                    await context.bot.send_message(
                        chat_id=hg['hunter']['id'],
                        text=(
                            f"❌ **{BOT_NAME}**: انتهت محاولاتك!\n\n"
                            f"فشلت في إيجاد جميع المختبئين 😔\n"
                            f"المشاركون فازوا هذه المرة!"
                        ),
                        parse_mode='Markdown'
                    )
                except:
                    pass

                # إشعار المختبئين بالفوز
                for player in hg['players']:
                    try:
                        await context.bot.send_message(
                            chat_id=player['id'],
                            text=(
                                f"🎉 **{BOT_NAME}**: مبروك فزت!\n\n"
                                f"المطارد فشل في إيجادك 🏆"
                            ),
                            parse_mode='Markdown'
                        )
                    except:
                        pass

                # تسجيل فوز المشاركين
                for player in hg['players']:
                    record_win(player['id'], hg_chat_id, player)

                del hunter_games[hg_chat_id]
                if hg_chat_id in games:
                    del games[hg_chat_id]

            else:
                # لا تزال هناك محاولات
                player_buttons = [
                    [InlineKeyboardButton(
                        f"✅ {p['first_name']}" if p['id'] in [g['id'] for g in hg['guessed']] else f"👤 {p['first_name']}",
                        callback_data=f"huntpick|{hg_chat_id}|{p['id']}"
                    )]
                    for p in hg['players']
                ]
                try:
                    await context.bot.send_message(
                        chat_id=hg['hunter']['id'],
                        text=(
                            f"❌ خطأ! ليس هناك...\n\n"
                            f"المحاولات المتبقية: **{left_attempts}**\n\n"
                            f"حاول مع لاعب آخر 👇"
                        ),
                        reply_markup=InlineKeyboardMarkup(player_buttons),
                        parse_mode='Markdown'
                    )
                except:
                    pass
        return

    # ══ رجوع للقائمة الرئيسية (المطارد) ══
    if data.startswith("huntback|"):
        parts = data.split("|")
        try:
            hg_chat_id = int(parts[1])
        except:
            await query.answer("❌ خطأ.", show_alert=True)
            return

        if hg_chat_id not in hunter_games:
            await query.answer("❌ اللعبة انتهت.", show_alert=True)
            return

        hg = hunter_games[hg_chat_id]
        if user.id != hg['hunter']['id']:
            await query.answer("❌ لست المطارد!", show_alert=True)
            return

        player_buttons = [
            [InlineKeyboardButton(
                f"✅ {p['first_name']}" if p['id'] in [g['id'] for g in hg['guessed']] else f"👤 {p['first_name']}",
                callback_data=f"huntpick|{hg_chat_id}|{p['id']}"
            )]
            for p in hg['players']
        ]
        await query.answer()
        try:
            await query.edit_message_text(
                text=(
                    f"🕵️ اختر لاعباً لتخمين مكانه:\n"
                    f"المحاولات المتبقية: **{hg['max_attempts'] - hg['attempts']}**"
                ),
                reply_markup=InlineKeyboardMarkup(player_buttons),
                parse_mode='Markdown'
            )
        except:
            pass
        return

    # ══ إنهاء اللعبة ══
    await query.answer()

    if data.startswith("endconfirm_"):
        try:
            game_id = int(data[11:])
        except:
            return
        if await is_admin(chat, user.id):
            await force_end_game(game_id, context)
            await query.edit_message_text(f"✅ {BOT_NAME}: تم إنهاء اللعبة.")
        else:
            await query.answer("❌ المشرفون فقط!", show_alert=True)

    elif data.startswith("endcancel_"):
        await query.edit_message_text(f"↩️ {BOT_NAME}: تم إلغاء الطلب.")

async def force_end_game(game_id, context):
    if game_id in games:
        task = games[game_id].get('elimination_task')
        if task:
            task.cancel()
        del games[game_id]

# ══════════════════════════════════════════════
#              الأوامر النصية
# ══════════════════════════════════════════════
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id not in games:
        await update.message.reply_text(f"📊 {BOT_NAME}: لا توجد لعبة نشطة.\nاستخدم /panel أو /start")
        return
    game     = games[chat_id]
    phase_ar = {'joining': '⏳ انضمام', 'hunting': '🕵️ مطاردة'}.get(game['phase'], '')
    count    = len(game['players'])
    names    = "\n".join([f"  {i+1}. {fmt(p)}" for i, p in enumerate(game['players'])]) or "  —"
    await update.message.reply_text(
        f"📊 **{BOT_NAME} — حالة اللعبة**\n\n"
        f"🎮 الحالة: {phase_ar}\n"
        f"👥 المتبقون: **{count}** / {game.get('total_players', count)}\n"
        f"🔄 الجولة: {game.get('round_num', 0)}\n\n"
        f"**اللاعبون:**\n{names}",
        parse_mode='Markdown'
    )

async def end_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    if not await is_admin(chat, user.id):
        await update.message.reply_text(f"❌ {BOT_NAME}: المشرفون فقط.")
        return
    game_id = chat.id
    if game_id not in games:
        await update.message.reply_text(f"❌ {BOT_NAME}: لا توجد لعبة نشطة.")
        return
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ إنهاء",  callback_data=f"endconfirm_{game_id}"),
        InlineKeyboardButton("❌ إلغاء", callback_data=f"endcancel_{game_id}"),
    ]])
    await update.message.reply_text(f"⚠️ {BOT_NAME}: هل تريد إنهاء اللعبة؟", reply_markup=keyboard)

async def set_interval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    if not await is_admin(chat, user.id):
        await update.message.reply_text(f"❌ المشرفون فقط.")
        return
    if not context.args:
        await update.message.reply_text("📝 /setinterval <ثواني>  مثال: /setinterval 15")
        return
    try:
        val = max(5, min(60, int(context.args[0])))
    except:
        await update.message.reply_text("❌ رقم بين 5 و60.")
        return
    game_id = chat.id
    if game_id in games:
        games[game_id]['elim_interval'] = val
        await update.message.reply_text(f"✅ مدة الإقصاء: **{val} ثانية**.", parse_mode='Markdown')
    else:
        await update.message.reply_text("❌ لا توجد لعبة نشطة.")

async def kick_player(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    if not await is_admin(chat, user.id):
        await update.message.reply_text(f"❌ المشرفون فقط.")
        return
    game_id = chat.id
    if game_id not in games:
        await update.message.reply_text(f"❌ لا توجد لعبة.")
        return
    if not context.args:
        await update.message.reply_text("📝 /kick @username")
        return
    target = context.args[0].lstrip('@').lower()
    found  = next(
        (p for p in games[game_id]['players']
         if (p.get('username') or '').lower() == target or p['first_name'].lower() == target),
        None
    )
    if not found:
        await update.message.reply_text(f"❌ لم يُعثر على '{target}'.")
        return
    games[game_id]['players'].remove(found)
    await update.message.reply_text(f"🦵 تم طرد {fmt(found)}!", parse_mode='Markdown')

async def protect_player(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    if not await is_admin(chat, user.id):
        await update.message.reply_text(f"❌ المشرفون فقط.")
        return
    game_id = chat.id
    if game_id not in games:
        await update.message.reply_text(f"❌ لا توجد لعبة.")
        return
    if not context.args:
        await update.message.reply_text("📝 /protect @username")
        return
    target = context.args[0].lstrip('@').lower()
    found  = next(
        (p for p in games[game_id]['players']
         if (p.get('username') or '').lower() == target or p['first_name'].lower() == target),
        None
    )
    if not found:
        await update.message.reply_text(f"❌ لم يُعثر على اللاعب.")
        return
    games[game_id].setdefault('vip_players', []).append(found['id'])
    await update.message.reply_text(f"🛡️ {fmt(found)} محمي الجولة القادمة!", parse_mode='Markdown')

async def my_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user   = update.effective_user
    s      = get_stats(user.id)
    played = s.get('games', 0)
    wins   = s.get('wins',  0)
    rate   = round(wins / played * 100, 1) if played > 0 else 0
    medal  = "🥇" if wins >= 10 else "🥈" if wins >= 5 else "🥉" if wins >= 1 else "🎮"
    await update.message.reply_text(
        f"{medal} **إحصائياتك — {user.first_name}**\n\n"
        f"🎮 ألعاب: **{played}**\n"
        f"🏆 انتصارات: **{wins}**\n"
        f"📈 نسبة الفوز: **{rate}%**\n"
        f"📅 آخر لعبة: {s.get('last', 'لم تلعب بعد')}",
        parse_mode='Markdown'
    )

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    top = sorted(
        [(uid, s) for uid, s in stats.items() if s.get('wins', 0) > 0],
        key=lambda x: x[1]['wins'], reverse=True
    )[:10]
    if not top:
        await update.message.reply_text(f"🏆 {BOT_NAME}: لم يفز أحد بعد!")
        return
    medals = ["🥇", "🥈", "🥉"] + ["🏅"] * 7
    lines  = [f"{medals[i]} **{s.get('name','؟')}** — {s['wins']} 🏆 ({s.get('games',0)} لعبة)"
              for i, (uid, s) in enumerate(top)]
    await update.message.reply_text(
        f"🏆 **{BOT_NAME} — لوحة الصدارة**\n\n" + "\n".join(lines),
        parse_mode='Markdown'
    )

async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cid = str(update.effective_chat.id)
    if cid not in history or not history[cid]:
        await update.message.reply_text(f"📜 {BOT_NAME}: لا يوجد سجل بعد.")
        return
    lines = [f"{i+1}. 🏆 **{e['winner']}** | {e['players']} لاعب | {e['date']}"
             for i, e in enumerate(history[cid])]
    await update.message.reply_text(
        f"📜 **{BOT_NAME} — آخر الجولات**\n\n" + "\n".join(lines),
        parse_mode='Markdown'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"🤖 **{BOT_NAME} — لعبة الغميضة**\n\n"
        f"━━━ **أوامر اللعبة** ━━━\n"
        f"/start — بدء جولة جديدة _(أدمن)_\n"
        f"/panel — لوحة تحكم الأدمن 🎛\n"
        f"/end — إنهاء الجولة _(أدمن)_\n"
        f"/status — حالة اللعبة\n\n"
        f"━━━ **إعدادات** _(أدمن)_ ━━━\n"
        f"/setinterval 15 — تغيير مدة الإقصاء\n"
        f"/kick @username — طرد لاعب\n"
        f"/protect @username — حماية لاعب\n\n"
        f"━━━ **الإحصائيات** ━━━\n"
        f"/mystats — إحصائياتك\n"
        f"/leaderboard — لوحة الصدارة\n"
        f"/history — سجل الجولات\n\n"
        f"━━━ **مميزات جديدة** ━━━\n"
        f"🎛 /panel — لوحة تحكم كاملة بالأزرار\n"
        f"🎲 أحداث مفاجئة تلقائية أثناء اللعبة\n"
        f"🖼 عرض صور اللاعبين من اللوحة\n"
        f"🔗 رابط دعوة مباشر للجولة",
        parse_mode='Markdown'
    )

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🏓 {BOT_NAME}: Pong! ✅")


# ══════════════════════════════════════════════
#   معالج الرسائل النصية — "يوهان بدأ لعبة"
# ══════════════════════════════════════════════
MEMBER_START_TRIGGERS = ["يوهان بدأ لعبة", "يوهان ابدا لعبة", "يوهان بدأ", "yohan start"]
ADMIN_ALLOW_TRIGGER   = "يوهان بدأ اعضاء"
ADMIN_BLOCK_TRIGGER   = "يوهان اغلاق بدأ اعضاء"

async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    msg  = update.message

    if not msg or not msg.text:
        return
    if chat.type == 'private':
        return

    text     = msg.text.strip().lower()
    text_raw = msg.text.strip()
    game_id  = chat.id
    admin    = await is_admin(chat, user.id)

    # ── الأدمن يفعّل/يوقف بدء الأعضاء ──
    if admin:
        if ADMIN_ALLOW_TRIGGER in text_raw:
            member_start_allowed[game_id] = True
            await msg.reply_text(
                f"✅ **{BOT_NAME}**: تم تفعيل بدء اللعبة للأعضاء!\n"
                f"الآن يمكن لأي عضو بدء لعبة بكتابة: **يوهان بدأ لعبة**",
                parse_mode='Markdown'
            )
            return

        if ADMIN_BLOCK_TRIGGER in text_raw:
            member_start_allowed[game_id] = False
            await msg.reply_text(
                f"🔒 **{BOT_NAME}**: تم إيقاف بدء اللعبة للأعضاء.\n"
                f"الآن فقط المشرفون يمكنهم البدء.",
                parse_mode='Markdown'
            )
            return

    # ── بدء لعبة بالنص ──
    triggered = any(t in text for t in MEMBER_START_TRIGGERS)
    if not triggered:
        return

    # هل مسموح للأعضاء؟
    if not admin and not member_start_allowed.get(game_id, False):
        await msg.reply_text(
            f"🔒 **{BOT_NAME}**: بدء اللعبة للمشرفين فقط.\n"
            f"_(المشرف يستطيع تفعيل بدء الأعضاء بقول: يوهان بدأ اعضاء)_",
            parse_mode='Markdown'
        )
        return

    # هل توجد لعبة نشطة؟
    if game_id in games and games[game_id]['active']:
        await msg.reply_text(f"⚠️ **{BOT_NAME}**: توجد لعبة نشطة بالفعل!", parse_mode='Markdown')
        return

    await create_new_game(update, context, chat, DEFAULT_JOIN_TIME)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Error: {context.error}", exc_info=context.error)

# ══════════════════════════════════════════════
#                    main
# ══════════════════════════════════════════════
def main():
    load_data()

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start",       start_command))
    app.add_handler(CommandHandler("end",         end_game))
    app.add_handler(CommandHandler("status",      status_command))
    app.add_handler(CommandHandler("setinterval", set_interval))
    app.add_handler(CommandHandler("kick",        kick_player))
    app.add_handler(CommandHandler("protect",     protect_player))
    app.add_handler(CommandHandler("mystats",     my_stats))
    app.add_handler(CommandHandler("leaderboard", leaderboard))
    app.add_handler(CommandHandler("history",     history_command))
    app.add_handler(CommandHandler("help",        help_command))
    app.add_handler(CommandHandler("ping",        ping))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_handler))
    app.add_error_handler(error_handler)

    print(f"🤖 {BOT_NAME} (@{BOT_USERNAME}) يعمل...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
