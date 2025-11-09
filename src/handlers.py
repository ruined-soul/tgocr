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
active_jobs = {}  # {chat_id: {"cancel": bool}}


# ============================================================
# 📦 OCR HANDLING (archives)
# ============================================================
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
        f"📦 *{doc.file_name}* received — queued for OCR.\n"
        "⚙️ Please wait, I’m extracting and reading your images...",
        parse_mode="Markdown"
    )

    # Run archive processing in background
    asyncio.create_task(worker(update, context, file_path, temp_dir, chat_id))


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
    # Telegram photo sizes are provided in increasing order; take the largest
    if not update.message.photo:
        return await update.message.reply_text("⚠️ No photo found in the message.")

    photo = update.message.photo[-1]  # highest resolution
    file = await context.bot.get_file(photo.file_id)

    temp_dir = tempfile.mkdtemp()
    # Keep original extension if available, default to .jpg
    image_path = os.path.join(temp_dir, "uploaded_image.jpg")
    await file.download_to_drive(image_path)

    chat_id = update.effective_chat.id
    active_jobs[chat_id] = {"cancel": False}

    await update.message.reply_text("🖼️ Image received — queued for OCR...")

    # Run single-image OCR in background to avoid blocking webhook processing
    asyncio.create_task(image_worker(update, context, image_path, temp_dir, chat_id))


async def image_worker(update, context, image_path, temp_dir, chat_id):
    """Background worker for single-image OCR."""
    try:
        logging.info(f"🚀 Starting single-image OCR for chat {chat_id} on {image_path}")
        # process_single_image handles sending results/messages
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


# ============================================================
# 💬 TRANSLATION COMMAND (Batch version)
# ============================================================
def chunk_text_lines(text: str, batch_size: int = 5):
    """Split text into small batches of lines."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for i in range(0, len(lines), batch_size):
        yield lines[i:i + batch_size]


async def translate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Translates English dialogues to Hinglish using Gemini in small batches."""
    text = " ".join(context.args) if context.args else None
    if not text and update.message.reply_to_message:
        text = update.message.reply_to_message.text or update.message.reply_to_message.caption

    if not text:
        return await update.message.reply_text(
            "💬 Use `/translate <text>` or reply to a message to translate it.",
            parse_mode="Markdown"
        )

    wait_msg = await update.message.reply_text("⏳ Starting batch translation...")

    batches = list(chunk_text_lines(text, batch_size=5))
    total_batches = len(batches)
    translated_batches = []

    await wait_msg.edit_text(f"📦 Found {total_batches} batches. Starting translation...")

    for idx, batch in enumerate(batches, start=1):
        batch_text = "\n".join(batch)
        status_text = f"🔹 Translating batch {idx}/{total_batches}..."
        try:
            await update.message.reply_text(status_text)
        except Exception:
            pass

        translated = translate_to_hinglish(batch_text)
        translated_batches.append(translated)

        # Send progress sample every 2–3 batches
        if idx % 3 == 0 or idx == total_batches:
            sample_preview = "\n".join(translated_batches[-2:])[:2000]
            await update.message.reply_text(
                f"✅ *Partial Translation (up to batch {idx}/{total_batches}):*\n\n{sample_preview}",
                parse_mode="Markdown",
            )

        await asyncio.sleep(1.5)  # gentle delay to avoid rate limit

    full_translation = "\n\n".join(translated_batches)

    if len(full_translation) > 4000:
        with open("translation_full.txt", "w", encoding="utf-8") as f:
            f.write(full_translation)
        await update.message.reply_document(
            "translation_full.txt", caption="📜 Complete Hinglish Translation"
        )
    else:
        await update.message.reply_text(
            f"📜 *Complete Hinglish Translation:*\n\n{full_translation}",
            parse_mode="Markdown",
        )

    await update.message.reply_text("🎉 Translation completed successfully!")
