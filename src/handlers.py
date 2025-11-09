import os
import tempfile
import asyncio
import shutil
import sys
import logging
from telegram import Update
from telegram.ext import ContextTypes
from .ocr import process_archive
from .translate import translate_to_hinglish  # ✅ New import

# --- Logging setup ---
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logging.basicConfig(level=logging.INFO, handlers=[handler])

# --- Global state ---
active_jobs = {}  # {chat_id: {"cancel": bool}}


async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles incoming archive uploads."""
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
        "⚙️ This might take a minute, but you can still chat or cancel with /cancel.",
        parse_mode="Markdown"
    )

    # Run in background
    asyncio.create_task(worker(update, context, file_path, temp_dir, chat_id))


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancels an ongoing OCR process."""
    chat_id = update.effective_chat.id
    if chat_id in active_jobs:
        active_jobs[chat_id]["cancel"] = True
        await update.message.reply_text("🛑 Cancel request received. Stopping your current OCR task...")
        logging.info(f"🛑 Cancel flag set for chat {chat_id}")
    else:
        await update.message.reply_text("⚠️ You don’t have any active OCR process.")


async def worker(update, context, file_path, temp_dir, chat_id):
    """Performs extraction + OCR in background."""
    try:
        logging.info(f"🚀 Starting OCR job for chat {chat_id} on {file_path}")
        await process_archive(update, context, file_path, temp_dir, active_jobs)
        logging.info(f"✅ OCR job completed for chat {chat_id}")
    except Exception as e:
        logging.error(f"❌ Worker error for chat {chat_id}: {e}")
        try:
            await update.message.reply_text(f"❌ Error during OCR: {e}")
        except Exception:
            pass
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
        if chat_id in active_jobs:
            del active_jobs[chat_id]
        logging.info(f"🧹 Cleaned up temp data for chat {chat_id}")


# --- New: Translation Command ---
async def translate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Translates English dialogues to Hinglish using Gemini."""
    text = " ".join(context.args) if context.args else None

    # If no text argument, allow replying to another message
    if not text and update.message.reply_to_message:
        text = update.message.reply_to_message.text or update.message.reply_to_message.caption

    if not text:
        return await update.message.reply_text(
            "💬 Use `/translate <text>` or reply to a message to translate it.",
            parse_mode="Markdown"
        )

    wait_msg = await update.message.reply_text("⏳ Translating your dialogues, please wait...")

    translated = translate_to_hinglish(text)

    if translated.startswith("⚠️"):
        await wait_msg.edit_text(translated)
        return

    if len(translated) > 4000:
        with open("translation.txt", "w", encoding="utf-8") as f:
            f.write(translated)
        await wait_msg.delete()
        await update.message.reply_document(
            "translation.txt", caption="📜 Hinglish Translation (File Version)"
        )
    else:
        await wait_msg.edit_text(
            f"📜 *Hinglish Translation:*\n\n{translated}", parse_mode="Markdown"
        )
