import os
from aiohttp import web
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters
from src.handlers import start, handle_file, worker
import asyncio

BOT_TOKEN = os.getenv("BOT_TOKEN")
PORT = int(os.getenv("PORT", "8000"))
APP_URL = os.getenv("APP_URL")  # e.g. https://your-app-name.koyeb.app

async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_file))

    # Background worker task
    asyncio.create_task(worker())

    # --- webhook setup ---
    async def handle_webhook(request):
        data = await request.json()
        update = Update.de_json(data, app.bot)
        await app.process_update(update)
        return web.Response(text="ok")

    web_app = web.Application()
    web_app.add_routes([web.post("/webhook", handle_webhook)])

    # Set Telegram webhook
    webhook_url = f"{APP_URL}/webhook"
    await app.bot.set_webhook(webhook_url)
    print(f"🌐 Webhook set to {webhook_url}")

    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    print(f"🤖 Bot running on port {PORT}")
    await site.start()

    # Keep alive
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
