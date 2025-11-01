import os
import asyncio
from aiohttp import web
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN")
APP_URL = os.getenv("APP_URL", "").rstrip("/")

# --- Define the bot ---
app = Application.builder().token(BOT_TOKEN).build()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("✅ /start received")
    await update.message.reply_text("👋 Hello! The bot is alive and ready!")

app.add_handler(CommandHandler("start", start))

# --- Webhook handler ---
async def handle_webhook(request):
    data = await request.json()
    update = Update.de_json(data, app.bot)
    await app.process_update(update)
    return web.Response(status=200)

# --- Main startup ---
async def main():
    # **Initialize the Application before processing updates**
    await app.initialize()

    webhook_path = "/webhook"
    webhook_url = f"{APP_URL}{webhook_path}"

    web_app = web.Application()
    web_app.router.add_post(webhook_path, handle_webhook)

    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8000)
    await site.start()

    # Delete any existing webhook and set new one
    await app.bot.delete_webhook()
    await app.bot.set_webhook(url=webhook_url)

    print(f"🌐 Webhook set to {webhook_url}")
    print("🤖 Bot running on port 8000")

    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
