# /src/handlers.py
import os
import tempfile
import asyncio
import shutil
import sys
import logging
from telegram import Update
from telegram.ext import ContextTypes
from .ocr import (
    process_archive,
    process_archive_online,
    process_single_image,
    process_single_image_online,
)
from .translate import translate_to_hinglish

# Logging
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logging.basicConfig(level=logging.INFO, handlers=[handler])

active_jobs = {}     # {chat_id: {"cancel": bool}}
ocr_modes = {}       # {chat_id: "tesseract" or "online"}

# ============================================================
# 📦 FILE OCR HANDLER
# ============================================================

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles incoming OCR files."""
    doc = update.message.document
    if not doc:
        return await update.message.reply_text("⚠️ Please send a valid file.")

    name = doc.file_name.lower()
    if not any(name.endswith(ext) for ext in (".zip", ".7z", ".cbz", ".txt")):
        return await update.message.reply_text(
            "⚠️ Unsupported file type. Send `.zip`, `.7z`, `.cbz`, or `.txt`."
        )

    temp_dir = tempfile.mkdtemp()
    file_path = os.path.join(temp_dir, name)
    file = await context.bot.get_file(doc.file_id)
    await file.download_to_drive(file_path)
    chat_id = update.effective_chat.id
    active_jobs[chat_id] = {"cancel": False}

    if name.endswith(".txt"):
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
        return await translate_txt(update, text, name)

    await update.message.reply_text("📦 File received — queued for OCR.")
    asyncio.create_task(worker(update, context, file_path, temp_dir, chat_id))

# ============================================================
# 🖼️ SINGLE IMAGE HANDLING
# ============================================================

async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)

    temp_dir = tempfile.mkdtemp()
    image_path = os.path.join(temp_dir, "uploaded_image.jpg")
    await file.download_to_drive(image_path)

    chat_id = update.effective_chat.id
    active_jobs[chat_id] = {"cancel": False}
    await update.message.reply_text("🖼️ Image received — running OCR...")

    try:
        mode = ocr_modes.get(chat_id, "tesseract")
        if mode == "online":
            await process_single_image_online(update, image_path)
        else:
            await process_single_image(update, image_path)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
        active_jobs.pop(chat_id, None)

# ============================================================
# 🧠 OCR MODE SWITCH
# ============================================================

async def set_ocr_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    args = context.args

    if not args:
        current = ocr_modes.get(chat_id, "tesseract")
        return await update.message.reply_text(
            f"🧠 Current OCR mode: *{current}*\nUse `/ocrmode tesseract` or `/ocrmode online`.",
            parse_mode="Markdown"
        )

    mode = args[0].lower()
    if mode not in ["tesseract", "online"]:
        return await update.message.reply_text("⚠️ Invalid mode. Use `tesseract` or `online`.")
    ocr_modes[chat_id] = mode
    await update.message.reply_text(f"✅ OCR mode set to *{mode}*", parse_mode="Markdown")

# ============================================================
# ⚙️ BACKGROUND WORKER
# ============================================================

async def worker(update, context, file_path, temp_dir, chat_id):
    try:
        mode = ocr_modes.get(chat_id, "tesseract")
        if mode == "online":
            await process_archive_online(update, context, file_path, temp_dir, active_jobs)
        else:
            await process_archive(update, context, file_path, temp_dir, active_jobs)
    except Exception as e:
        await update.message.reply_text(f"❌ Error during OCR: {e}")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
        active_jobs.pop(chat_id, None)

# ============================================================
# 💬 TRANSLATION HELPERS
# ============================================================

def chunk_text_lines(text: str, batch_size: int = 5):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for i in range(0, len(lines), batch_size):
        yield lines[i:i + batch_size]

async def translate_txt(update: Update, text: str, filename: str):
    """Translate text files preserving formatting."""
    await update.message.reply_text(f"📜 Translating file *{filename}*...", parse_mode="Markdown")

    translated = translate_to_hinglish(text)
    output_name = f"translated_{filename}"
    with open(output_name, "w", encoding="utf-8") as f:
        f.write(translated)

    await update.message.reply_document(open(output_name, "rb"), caption=f"✅ Translation complete: {output_name}")
    os.remove(output_name)

# ============================================================
# 🛑 CANCEL ACTIVE JOB
# ============================================================

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel any running OCR job for this chat."""
    chat_id = update.effective_chat.id
    if chat_id in active_jobs:
        active_jobs[chat_id]["cancel"] = True
        await update.message.reply_text("🛑 OCR process cancelled.")
    else:
        await update.message.reply_text("⚠️ No active OCR process to cancel.")
