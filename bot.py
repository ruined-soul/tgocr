import asyncio
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters
from src.handlers import start, handle_file, worker
import os

BOT_TOKEN = os.getenv("BOT_TOKEN")

# --- ENTRYPOINT FIXED ---
# Do NOT wrap this in asyncio.run(); python-telegram-bot handles its own loop.
async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_file))

    # Run worker in background once the application is initialized
    asyncio.create_task(worker())

    print("🤖 Bot started and running on Koyeb...")
    await app.run_polling(drop_pending_updates=True)


# Detect if already inside a running loop (Koyeb containers can reuse it)
try:
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
except RuntimeError:
    # If loop already running, schedule main coroutine properly
    asyncio.get_event_loop().create_task(main())
    asyncio.get_event_loop().run_forever()
