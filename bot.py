# /bot.py
import os
import asyncio
from aiohttp import web
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from src.handlers import (
    handle_file,
    handle_image,
    worker,
    cancel,
    translate_command,
    set_ocr_mode,
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
APP_URL = os.getenv("APP_URL", "").rstrip("/")

if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN environment variable is missing.")
if not APP_URL:
    raise ValueError("❌ APP_URL environment variable is missing.")

app = Application.builder().token(BOT_TOKEN).build()

# ============================================================
# 🚀 COMMANDS
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    welcome_text = (
        f"👋 Hello {user.first_name or 'there'}!\n\n"
        "I'm your **OCR + Hinglish Translation Bot**.\n\n"
        "📦 *OCR:* Send me a `.zip`, `.7z`, or image to extract text.\n"
        "💬 *Translate:* Use `/translate <text>` for Hinglish.\n\n"
        "🔄 *Modes:*\n"
        "• `/ocrmode tesseract` — Local OCR\n"
        "• `/ocrmode online` — OnlineOCR.net API"
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "🧠 *Help — OCR + Hinglish Bot*\n\n"
        "📦 **OCR Options:**\n"
        "• `/ocrmode tesseract` — Use local Tesseract OCR\n"
        "• `/ocrmode online` — Use OnlineOCR.net API\n\n"
        "💬 **Translate:**\n"
        "Use `/translate <text>` or reply to text to translate."
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

# ============================================================
# 🌐 WEBHOOK HANDLER
# ============================================================

async def handle_webhook(request):
    try:
        data = await request.json()
        update = Update.de_json(data, app.bot)
        await app.process_update(update)
        return web.Response(status=200)
    except Exception as e:
        print("❌ Webhook error:", e)
        return web.Response(status=400)

# ============================================================
# 🏁 MAIN STARTUP
# ============================================================

async def main():
    print("🚀 Starting OCR + Translation Bot...")
    await app.initialize()

    webhook_path = "/webhook"
    webhook_url = f"{APP_URL}{webhook_path}"

    web_app = web.Application()
    web_app.router.add_post(webhook_path, handle_webhook)

    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8000)
    await site.start()

    await app.bot.delete_webhook(drop_pending_updates=True)
    await app.bot.set_webhook(url=webhook_url)

    # Register handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CommandHandler("translate", translate_command))
    app.add_handler(CommandHandler("ocrmode", set_ocr_mode))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_file))
    app.add_handler(MessageHandler(filters.PHOTO, handle_image))

    print(f"✅ Webhook set to {webhook_url}")
    print("🤖 Bot is up and running!")

    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print("💥 Startup error:", e)
