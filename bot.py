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
    worker,
    cancel,
    translate_command,
    handle_image,
    set_ocr_mode,
)

# --- Environment variables ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
APP_URL = os.getenv("APP_URL", "").rstrip("/")

if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN environment variable is missing.")
if not APP_URL:
    raise ValueError("❌ APP_URL environment variable is missing.")

# --- Define the bot ---
app = Application.builder().token(BOT_TOKEN).build()


# ============================================================
# 🚀 COMMANDS
# ============================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Welcome message."""
    user = update.effective_user
    welcome_text = (
        f"👋 Hello {user.first_name or 'there'}!\n\n"
        "I'm your **OCR + Hinglish Translation Bot**. Here's what I can do:\n\n"
        "📦 *1. OCR Extraction:*\n"
        "→ Send me a `.zip`, `.cbz`, or `.7z` file containing images.\n"
        "→ I'll extract and read the English dialogues from each image.\n\n"
        "🖼️ *Also:* Send single images and I'll OCR them directly.\n\n"
        "💬 *2. Hinglish Translation:*\n"
        "→ Use `/translate <text>` or reply to any English text with `/translate`.\n\n"
        "⚙️ *3. OCR Mode Control:*\n"
        "→ Use `/ocrmode local` or `/ocrmode online` to choose between local Tesseract and OnlineOCR.\n\n"
        "✨ Try sending me a few dialogues or an image now!"
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Help guide."""
    help_text = (
        "🧠 *Help — OCR + Hinglish Bot*\n\n"
        "📦 **For OCR (archives):**\n"
        "Send a `.zip`, `.cbz`, or `.7z` archive containing image pages.\n"
        "I'll extract and read text from all images automatically.\n\n"
        "🖼️ **For single images:**\n"
        "Send a photo and I'll OCR it directly.\n\n"
        "💬 **For Translation:**\n"
        "Use `/translate <text>` or reply to a message with `/translate`.\n"
        "I’ll translate it into Hinglish.\n\n"
        "⚙️ **OCR Mode:**\n"
        "Use `/ocrmode local` or `/ocrmode online` to switch OCR engines per user.\n\n"
        "📋 *Commands:*\n"
        "• `/translate` — Translate text to Hinglish\n"
        "• `/cancel` — Cancel any ongoing OCR task\n"
        "• `/ocrmode` — View or set OCR mode\n"
        "• `/help` — Show this help message"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")


# ============================================================
# 🌐 WEBHOOK HANDLER
# ============================================================
async def handle_webhook(request):
    try:
        data = await request.json()
        print("📨 Incoming update:", data)
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

    print(f"✅ Webhook set to {webhook_url}")
    print("🤖 Bot is up and running!")

    # Register handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CommandHandler("translate", translate_command))
    app.add_handler(CommandHandler("ocrmode", set_ocr_mode))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_file))
    app.add_handler(MessageHandler(filters.PHOTO, handle_image))

    await asyncio.Event().wait()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print("💥 Startup error:", e)
