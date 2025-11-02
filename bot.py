import os
import asyncio
from aiohttp import web
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)
from src.handlers import handle_file, worker

BOT_TOKEN = os.getenv("BOT_TOKEN")
APP_URL = os.getenv("APP_URL", "").rstrip("/")

# --- Define the bot ---
app = Application.builder().token(BOT_TOKEN).build()


# --- /start command ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    welcome_text = (
        f"👋 Hello {user.first_name or 'there'}!\n\n"
        "I'm your *OCR Bot* — I can extract text from images inside archives.\n\n"
        "📦 *How to use me:*\n"
        "1️⃣ Send me a `.zip`, `.7z`, or `.cz` file containing images (JPG, PNG, etc.)\n"
        "2️⃣ I’ll extract the images and perform OCR on each.\n"
        "3️⃣ I’ll send back the recognized text for every image.\n\n"
        "Ready? Just send your file now or tap below 👇"
    )

    keyboard = [
        [InlineKeyboardButton("📤 Send File", switch_inline_query_current_chat="")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(welcome_text, parse_mode="Markdown", reply_markup=reply_markup)


# --- /help command ---
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "🧠 *Help — OCR Bot*\n\n"
        "Here's what I can do:\n\n"
        "📦 *Supported formats:*\n"
        "• `.zip` — Standard compressed archives\n"
        "• `.7z` or `.cz` — High compression formats\n\n"
        "🖼️ *Supported image types:*\n"
        "• JPG, PNG, BMP, TIFF\n\n"
        "📋 *How it works:*\n"
        "1️⃣ You send a supported archive file.\n"
        "2️⃣ I extract and scan all images for text.\n"
        "3️⃣ I send back the text from each image, one by one.\n\n"
        "💡 *Tip:* Keep archive sizes small for faster processing."
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")


# --- Webhook handler ---
async def handle_webhook(request):
    data = await request.json()
    update = Update.de_json(data, app.bot)
    await app.process_update(update)
    return web.Response(status=200)


# --- Main startup ---
async def main():
    # Initialize app before processing updates
    await app.initialize()

    webhook_path = "/webhook"
    webhook_url = f"{APP_URL}{webhook_path}"

    web_app = web.Application()
    web_app.router.add_post(webhook_path, handle_webhook)

    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8000)
    await site.start()

    # Delete old webhook and set new one
    await app.bot.delete_webhook()
    await app.bot.set_webhook(url=webhook_url)

    print(f"🌐 Webhook set to {webhook_url}")
    print("🤖 Bot running on port 8000")

    # Start background OCR worker
    asyncio.create_task(worker())

    # Add handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_file))

    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
