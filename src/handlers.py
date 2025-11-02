import os
import tempfile
import asyncio
import shutil
from telegram import Update
from telegram.ext import ContextTypes
from .ocr import process_archive

# Queues and cancellation
processing_queue = asyncio.Queue()
cancelled_jobs = set()


async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc:
        return await update.message.reply_text("⚠️ Please send a valid file.")

    name = doc.file_name.lower()
    if not any(name.endswith(ext) for ext in (".zip", ".7z", ".cbz")):
        return await update.message.reply_text(
            "⚠️ Unsupported file type.\n\n"
            "Please send a `.zip`, `.cbz`, or `.7z` archive containing images."
        )

    temp_dir = tempfile.mkdtemp()
    file_path = os.path.join(temp_dir, name)
    file = await context.bot.get_file(doc.file_id)
    await file.download_to_drive(file_path)

    await update.message.reply_text(
        f"📦 *{doc.file_name}* received — added to the processing queue.\n"
        "⏳ Please wait while I process it...",
        parse_mode="Markdown"
    )

    await processing_queue.put((update, context, file_path, temp_dir))


async def worker():
    """Background task that processes queued OCR jobs sequentially."""
    while True:
        update, context, file_path, temp_dir = await processing_queue.get()
        chat_id = update.effective_chat.id

        if chat_id in cancelled_jobs:
            await update.message.reply_text("❌ Processing cancelled.")
            cancelled_jobs.remove(chat_id)
            shutil.rmtree(temp_dir, ignore_errors=True)
            processing_queue.task_done()
            continue

        try:
            await process_archive(update, context, file_path, temp_dir)
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {e}")
            print(f"❌ Worker error: {e}")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
            processing_queue.task_done()


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel the current OCR task for the user."""
    chat_id = update.effective_chat.id
    cancelled_jobs.add(chat_id)
    await update.message.reply_text("🛑 Cancel request received. Stopping your current OCR task...")
