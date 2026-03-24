import logging
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from automation import process_link

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = "8531850036:AAFQPvuqEByWUKLbLBkotMY9qWbmw4RKr14"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 مرحباً!\n\n"
        "أرسل لي رابط Google SSO وسأقوم بـ:\n"
        "✅ قبول شروط Google\n"
        "✅ قبول شروط Google Cloud\n"
        "✅ إنشاء Cloud Run Service\n"
        "✅ إرسال الـ URL الخاص بك"
    )

async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    
    if "skills.google" not in url and "accounts.google" not in url:
        await update.message.reply_text("❌ الرابط غير صحيح! أرسل رابط Google SSO صحيح.")
        return
    
    msg = await update.message.reply_text("⏳ جاري المعالجة... انتظر")
    
    try:
        result = await asyncio.to_thread(process_link, url)
        
        if result["success"]:
            await msg.edit_text(
                f"✅ تم بنجاح!\n\n"
                f"🔗 رابط الخدمة:\n{result['endpoint_url']}"
            )
        else:
            await msg.edit_text(f"❌ حدث خطأ:\n{result['error']}")
    
    except Exception as e:
        logger.error(f"Error: {e}")
        await msg.edit_text(f"❌ حدث خطأ غير متوقع:\n{str(e)}")

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
    
    logger.info("البوت يعمل...")
    app.run_polling()

if __name__ == "__main__":
    main()
