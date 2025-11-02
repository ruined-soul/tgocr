import os
import tempfile
import asyncio
import shutil
from telegram import Update
from telegram.ext import ContextTypes
from .ocr import process_archive

# Queue to manage incoming OCR jobs
processing_queue = asyncio.Queue()


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
        try:
            await process_archive(update, context, file_path, temp_dir)
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {e}")
            print(f"❌ Worker error: {e}")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
            processing_queue.task_done()
