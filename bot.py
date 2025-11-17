# bot.py
import os
import asyncio
import warnings
from aiohttp import web
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ContextTypes,
    filters, CallbackQueryHandler, ConversationHandler,
)
from telegram.warnings import PTBUserWarning

# Suppress PTB warnings (optional but clean)
warnings.filterwarnings("ignore", category=PTBUserWarning)

# Import handlers
from src.handlers import (
    handle_file, cancel, translate_command, handle_image,
    set_ocr_mode, model_command, button_callback,
    style_command, receive_style_guide, cancel_style,
)
from src.user_handlers import get_api_handlers
from src.handlers import WAITING_FOR_STYLE

BOT_TOKEN = os.getenv("BOT_TOKEN")
APP_URL = os.getenv("APP_URL", "").rstrip("/")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN missing.")
if not APP_URL:
    raise ValueError("APP_URL missing.")

app = Application.builder().token(BOT_TOKEN).build()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"Hello {user.first_name or 'there'}!\n\n"
        "Send `.zip/.cbz/.7z`, images, or text.\n"
        "Use `/translate`, `/model`, `/style`, `/ocrmode`, `/api` to customize.\n\n"
        "_You need your own Gemini API key! Use /api_",
        parse_mode="Markdown"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "*Commands:*\n"
        "`/translate` – English → Hinglish\n"
        "`/ocrmode local|online` – OCR engine\n"
        "`/model` – pick Gemini model\n"
        "`/style` – custom translation style\n"
        "`/api` – *manage your Gemini API keys (required!)*\n"
        "`/cancel` – stop OCR\n\n"
        "_Get free key: https://aistudio.google.com/app/apikey_",
        parse_mode="Markdown"
    )


# ————————————————————————
# AIOHTTP Webhook Handler
# ————————————————————————
async def handle_webhook(request):
    try:
        data = await request.json()
        update = Update.de_json(data, app.bot)
        await app.process_update(update)
        return web.Response(status=200)
    except Exception as e:
        print("Webhook error:", e)
        return web.Response(status=400)


# ————————————————————————
# MAIN
# ————————————————————————
async def main():
    print("Starting bot...")
    await app.initialize()

    webhook_path = "/webhook"
    webhook_url = f"{APP_URL}{webhook_path}"

    # Setup aiohttp server
    web_app = web.Application()
    web_app.router.add_post(webhook_path, handle_webhook)

    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8000)
    await site.start()

    # Set webhook
    await app.bot.delete_webhook(drop_pending_updates=True)
    await app.bot.set_webhook(url=webhook_url)
    print(f"Webhook set: {webhook_url}")

    # —————— HANDLERS ——————

    # 1) MODEL CALLBACKS (must be first)
    app.add_handler(CallbackQueryHandler(button_callback, pattern=r"^model\|"))

    # 2) API MENU HANDLERS (new clean version)
    from src.user_handlers import get_api_handlers
    for handler in get_api_handlers():
        app.add_handler(handler)

    # 3) STYLE CONVERSATION
    style_conv = ConversationHandler(
        entry_points=[CommandHandler("style", style_command)],
        states={
            WAITING_FOR_STYLE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_style_guide)
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel_style)],
        per_message=False,
    )
    app.add_handler(style_conv)

    # 4) NORMAL COMMANDS
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CommandHandler("translate", translate_command))
    app.add_handler(CommandHandler("ocrmode", set_ocr_mode))
    app.add_handler(CommandHandler("model", model_command))

    # 5) FILE & IMAGE HANDLERS
    app.add_handler(MessageHandler(filters.Document.ALL, handle_file))
    app.add_handler(MessageHandler(filters.PHOTO, handle_image))

    # Keep alive
    print("Bot is running...")
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
