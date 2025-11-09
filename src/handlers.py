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

    # --- Handle OCR archives ---
    if any(name.endswith(ext) for ext in (".zip", ".7z", ".cbz")):
        active_jobs[chat_id] = {"cancel": False}
        await update.message.reply_text(
            f"📦 *{doc.file_name}* received — queued for OCR.\n"
            "⚙️ Please wait, I’m extracting and reading your images...",
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

    # --- Unsupported file type ---
    await update.message.reply_text(
        "⚠️ Unsupported file type.\n\n"
        "Send one of these:\n"
        "• `.zip`, `.cbz`, `.7z` → OCR from images\n"
        "• `.txt` → Translate English text to Hinglish\n"
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
    active_jobs[chat_id] = {"cancel": False}

    await update.message.reply_text("🖼️ Image received — queued for OCR...")

    asyncio.create_task(image_worker(update, context, image_path, temp_dir, chat_id))


async def image_worker(update, context, image_path, temp_dir, chat_id):
    """Background worker for single-image OCR."""
    try:
        logging.info(f"🚀 Starting single-image OCR for chat {chat_id} on {image_path}")
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
# 💬 TRANSLATION COMMAND
# ============================================================
def chunk_text_lines(text: str, batch_size: int = 5):
    """Split text into small batches of lines (preserving blank lines)."""
    lines = text.splitlines()
    for i in range(0, len(lines), batch_size):
        yield lines[i:i + batch_size]


def make_progress_bar(current: int, total: int, length: int = 12) -> str:
    """Generate a textual progress bar."""
    filled = int(length * current / total)
    empty = length - filled
    bar = "█" * filled + "░" * empty
    percent = int((current / total) * 100)
    return f"[{bar}] {percent}% ({current}/{total})"


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

    await translate_txt_content(update, context, text)


# ============================================================
# 📄 TRANSLATION HELPER — OUTPUT AS .TXT (with progress bar)
# ============================================================
async def translate_txt_content(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, file_name: str = None):
    """Translate text content (from /translate or .txt file) and return a .txt file."""
    progress_msg = await update.message.reply_text("⏳ Preparing translation...")

    batches = list(chunk_text_lines(text, batch_size=5))
    total_batches = len(batches)
    translated_batches = []

    await progress_msg.edit_text(f"📦 Found {total_batches} batches. Starting translation...")

    for idx, batch in enumerate(batches, start=1):
        batch_text = "\n".join(batch)
        translated = translate_to_hinglish(batch_text)
        translated_batches.append(translated)

        # --- Update progress bar in one message ---
        bar = make_progress_bar(idx, total_batches)
        try:
            await progress_msg.edit_text(f"📝 Translating... {bar}")
        except Exception:
            pass

        await asyncio.sleep(1.0)

    # Combine all batches preserving original formatting
    full_translation = "\n".join(translated_batches)

    # --- Write translation to a .txt file ---
    base_name = os.path.splitext(file_name or "translation")[0]
    output_name = f"{base_name}_hinglish.txt"
    out_path = os.path.join(tempfile.gettempdir(), output_name)

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(full_translation)

    await progress_msg.edit_text("✅ Translation complete! Preparing file...")

    await update.message.reply_document(
        document=open(out_path, "rb"),
        filename=output_name,
        caption="📜 Hinglish Translation (original formatting preserved)"
    )

    try:
        os.remove(out_path)
    except Exception:
        pass

    await progress_msg.edit_text("🎉 Translation completed successfully!")
