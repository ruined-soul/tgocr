import os
import tempfile
import asyncio
import shutil
import logging
from telegram import Update
from telegram.ext import ContextTypes
from .ocr import process_archive

# --- Logging setup ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", flush=True)

# --- Global state ---
processing_queue = asyncio.Queue()
active_jobs = {}  # {chat_id: {"cancel": bool}}

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc:
        return await update.message.reply_text("⚠️ Please send a valid file.")

    name = doc.file_name.lower()
    if not any(name.endswith(ext) for ext in (".zip", ".7z", ".cbz")):
        return await update.message.reply_text(
            "⚠️ Unsupported file type.\n\nPlease send a `.zip`, `.cbz`, or `.7z` archive containing images."
        )

    temp_dir = tempfile.mkdtemp()
    file_path = os.path.join(temp_dir, name)

    file = await context.bot.get_file(doc.file_id)
    await file.download_to_drive(file_path)

    chat_id = update.effective_chat.id
    active_jobs[chat_id] = {"cancel": False}

    await update.message.reply_text(
        f"📦 *{doc.file_name}* received — queued for processing.\n"
        "⚙️ This might take a minute, but you can still chat or cancel (/cancel).",
        parse_mode="Markdown"
    )

    # Queue it for background processing
    asyncio.create_task(worker(update, context, file_path, temp_dir, chat_id))


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in active_jobs:
        active_jobs[chat_id]["cancel"] = True
        await update.message.reply_text("🛑 Cancel request received. Stopping your current OCR task...")
        logging.info(f"🛑 Cancel flag set for chat {chat_id}")
    else:
        await update.message.reply_text("⚠️ You don’t have any active OCR process.")


async def worker(update, context, file_path, temp_dir, chat_id):
    """Runs OCR job in background while bot stays responsive."""
    try:
        logging.info(f"🚀 Starting OCR job for chat {chat_id} on {file_path}")
        await process_archive(update, context, file_path, temp_dir, active_jobs)
        logging.info(f"✅ OCR job completed for chat {chat_id}")
    except Exception as e:
        logging.error(f"❌ Worker error for chat {chat_id}: {e}")
        await update.message.reply_text(f"❌ Error during OCR: {e}")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
        if chat_id in active_jobs:
            del active_jobs[chat_id]
