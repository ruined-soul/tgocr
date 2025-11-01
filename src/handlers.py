import os
import tempfile
import asyncio
import shutil
from telegram import Update
from telegram.ext import ContextTypes
from .ocr import process_archive

processing_queue = asyncio.Queue()


async def start(update: Update, _: ContextTypes.DEFAULT_TYPE):
    msg = (
        "👋 *Welcome to OCR Bot!*\n\n"
        "Send me a `.zip`, `.7z`, or `.cz` file containing images.\n"
        "I'll extract and scan them for text, then send results one by one."
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc:
        return await update.message.reply_text("⚠️ Please send a valid file.")

    name = doc.file_name.lower()
    if not any(name.endswith(ext) for ext in (".zip", ".7z", ".cz")):
        return await update.message.reply_text("⚠️ Supported formats: .zip, .7z, .cz")

    temp_dir = tempfile.mkdtemp()
    file_path = os.path.join(temp_dir, name)
    file = await context.bot.get_file(doc.file_id)
    await file.download_to_drive(file_path)

    await update.message.reply_text("📦 File received — added to processing queue.")
    await processing_queue.put((update, context, file_path, temp_dir))


async def worker():
    while True:
        update, context, file_path, temp_dir = await processing_queue.get()
        try:
            await process_archive(update, context, file_path, temp_dir)
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {e}")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
            processing_queue.task_done()
