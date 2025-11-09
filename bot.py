import os
import asyncio
from aiohttp import web
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)
from src.handlers import handle_file, worker, cancel, translate_command  # ✅ Updated import

# --- Environment variables ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
APP_URL = os.getenv("APP_URL", "").rstrip("/")

if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN environment variable is missing.")
if not APP_URL:
    raise ValueError("❌ APP_URL environment variable is missing.")

# --- Define the bot ---
app = Application.builder().token(BOT_TOKEN).build()


# --- /start command ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    welcome_text = (
        f"👋 Hello {user.first_name or 'there'}!\n\n"
        "I'm your *OCR Bot* — I can extract text from images inside archives.\n\n"
        "📦 *How to use me:*\n"
        "1️⃣ Send me a `.zip`, `.7z`, or `.cbz` file containing images (JPG, PNG, etc.)\n"
        "2️⃣ I’ll extract and perform OCR on each image.\n"
        "3️⃣ I’ll send back the recognized text.\n\n"
        "💡 You can also use /translate to turn English text into Hinglish!"
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")


# --- /help command ---
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "🧠 *Help — OCR Bot*\n\n"
        "📦 *Supported formats:*\n"
        "• `.zip`, `.cbz`, `.7z`\n\n"
        "🖼️ *Supported image types:*\n"
        "• JPG, PNG, BMP, TIFF, WEBP\n\n"
        "📋 *Commands:*\n"
        "• /translate <text> — Translate English → Hinglish\n"
        "• /cancel — Cancel OCR processing\n\n"
        "💡 Tip: You can reply with /translate to any text message!"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")


# --- Webhook handler ---
async def handle_webhook(request):
    try:
        data = await request.json()
        print("📨 Incoming update:", data)
        update = Update.de_json(data, app.bot)
        try:
            await app.process_update(update)
        except Exception as e:
            print("❌ Error while processing update:", e)
        return web.Response(status=200)
    except Exception as e:
        print("❌ Failed to parse webhook request:", e)
        return web.Response(status=400)


# --- Main startup ---
async def main():
    print("🚀 Starting OCR Bot initialization...")

    await app.initialize()

    webhook_path = "/webhook"
    webhook_url = f"{APP_URL}{webhook_path}"

    web_app = web.Application()
    web_app.router.add_post(webhook_path, handle_webhook)

    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8000)
    await site.start()

    print("🌍 Setting Telegram webhook...")
    await app.bot.delete_webhook(drop_pending_updates=True)
    await app.bot.set_webhook(url=webhook_url)

    print(f"✅ Webhook set to {webhook_url}")
    print("🤖 Bot is up and running on port 8000 (Koyeb)")

    # Register handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CommandHandler("translate", translate_command))  # ✅ New command
    app.add_handler(MessageHandler(filters.Document.ALL, handle_file))

    print("📡 Waiting for Telegram updates...")
    await asyncio.Event().wait()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print("💥 Fatal startup error:", e)
