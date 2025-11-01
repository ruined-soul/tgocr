import asyncio
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters
from src.handlers import start, handle_file, worker
from os import getenv

BOT_TOKEN = getenv("BOT_TOKEN")

async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_file))

    asyncio.create_task(worker())  # background queue worker

    print("🤖 Bot started and running on Koyeb...")
    await app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    asyncio.run(main())
