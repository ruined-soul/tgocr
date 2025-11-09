# /src/handlers.py
import os
import tempfile
import asyncio
import shutil
import sys
import logging
from telegram import Update
from telegram.ext import ContextTypes
from .ocr import process_archive, process_single_image
from .translate import translate_to_hinglish

# --- Logging setup ---
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logging.basicConfig(level=logging.INFO, handlers=[handler])

# --- Global state ---
active_jobs = {}   # {chat_id: {"cancel": bool}}
user_settings = {}  # {chat_id: {"ocr_mode": "local" or "online"}}


# ============================================================
# ⚙️ OCR MODE COMMAND
# ============================================================
async def set_ocr_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Allows each user to choose OCR mode: local or online."""
    chat_id = update.effective_chat.id

    if not context.args:
        current = user_settings.get(chat_id, {}).get("ocr_mode", "local")
        await update.message.reply_text(
            f"⚙️ Current OCR mode: *{current}*\n\n"
            "Use `/ocrmode local` or `/ocrmode online` to switch.",
            parse_mode="Markdown"
        )
        return

    mode = context.args[0].lower()
    if mode not in ("local", "online"):
        await update.message.reply_text("❌ Invalid mode. Use `local` or `online`.", parse_mode="Markdown")
        return

    user_settings.setdefault(chat_id, {})["ocr_mode"] = mode
    await update.message.reply_text(f"✅ OCR mode set to *{mode}* for this chat.", parse_mode="Markdown")


# ============================================================
# 📦 FILE HANDLING (OCR archives + .txt translation)
# ============================================================
async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles incoming archive or text uploads."""
    doc = update.message.document
    if not doc:
        return await update.message.reply_text("⚠️ Please send a valid file.")

    name = doc.file_name.lower()
    temp_dir = tempfile.mkdtemp()
    file_path = os.path.join(temp_dir, name)

    file = await context.bot.get_file(doc.file_id)
    await file.download_to_drive(file_path)

    chat_id = update.effective_chat.id
    ocr_mode = user_settings.get(chat_id, {}).get("ocr_mode", "local")

    # --- Handle OCR archives ---
    if any(name.endswith(ext) for ext in (".zip", ".7z", ".cbz")):
        active_jobs[chat_id] = {"cancel": False}
        await update.message.reply_text(
            f"📦 *{doc.file_name}* received — queued for OCR.\n"
            f"⚙️ Using *{ocr_mode}* OCR mode. Please wait...",
            parse_mode="Markdown"
        )
        asyncio.create_task(worker(update, context, file_path, temp_dir, chat_id))
        return

    # --- Handle text files for translation ---
    if name.endswith(".txt"):
        await update.message.reply_text(
            f"📄 *{doc.file_name}* received — reading text for translation...",
            parse_mode="Markdown"
        )
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            if len(content) > 15000:
                await update.message.reply_text(
                    "⚠️ File too large for translation (>15 KB). Please send a smaller `.txt` file."
                )
            elif not content.strip():
                await update.message.reply_text("⚠️ The file seems empty.")
            else:
                await translate_txt_content(update, context, content, file_name=name)
        except Exception as e:
            await update.message.reply_text(f"❌ Error reading `.txt`: {e}")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
        return

    await update.message.reply_text(
        "⚠️ Unsupported file type.\n\n"
        "Send one of these:\n"
        "• `.zip`, `.cbz`, `.7z` → OCR from images\n"
        "• `.txt` → Translate text\n"
        "• Or send an image directly"
    )
    shutil.rmtree(temp_dir, ignore_errors=True)


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancels an ongoing OCR process."""
    chat_id = update.effective_chat.id
    if chat_id in active_jobs:
        active_jobs[chat_id]["cancel"] = True
        await update.message.reply_text("🛑 Cancel request received. Stopping your OCR task...")
        logging.info(f"🛑 Cancel flag set for chat {chat_id}")
    else:
        await update.message.reply_text("⚠️ You don’t have any active OCR process.")


async def worker(update, context, file_path, temp_dir, chat_id):
    """Performs extraction + OCR in background for archives."""
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


# ============================================================
# 🖼️ SINGLE IMAGE HANDLING
# ============================================================
async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles single image uploads (photo messages) for OCR."""
    if not update.message.photo:
        return await update.message.reply_text("⚠️ No photo found in the message.")

    photo = update.message.photo[-1]  # highest resolution
    file = await context.bot.get_file(photo.file_id)

    temp_dir = tempfile.mkdtemp()
    image_path = os.path.join(temp_dir, "uploaded_image.jpg")
    await file.download_to_drive(image_path)

    chat_id = update.effective_chat.id
    ocr_mode = user_settings.get(chat_id, {}).get("ocr_mode", "local")

    active_jobs[chat_id] = {"cancel": False}

    await update.message.reply_text(f"🖼️ Image received — using *{ocr_mode}* OCR mode...", parse_mode="Markdown")
    asyncio.create_task(image_worker(update, context, image_path, temp_dir, chat_id))


async def image_worker(update, context, image_path, temp_dir, chat_id):
    """Background worker for single-image OCR."""
    try:
        logging.info(f"🚀 Starting single-image OCR for chat {chat_id}")
        await process_single_image(update, context, image_path, active_jobs)
        logging.info(f"✅ Single-image OCR completed for chat {chat_id}")
    except Exception as e:
        logging.error(f"❌ Image worker error for chat {chat_id}: {e}")
        try:
            await update.message.reply_text(f"❌ Error during image OCR: {e}")
        except Exception:
            pass
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
        if chat_id in active_jobs:
            del active_jobs[chat_id]
        logging.info(f"🧹 Cleaned up image temp data for chat {chat_id}")
