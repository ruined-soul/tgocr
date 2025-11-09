import os
import asyncio
import tempfile
import zipfile
import aiohttp
import pytesseract
from PIL import Image
from google import genai
from telegram import Update
from telegram.ext import ContextTypes

# -------------------------------
# 🌐 Environment and Config
# -------------------------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY)

MODEL_NAME = "gemini-2.5-flash"
STYLE_GUIDE = (
    "Translate text into natural Hinglish (Roman Hindi). Keep tone conversational, "
    "preserve meaning, and avoid literal translation. Example: 'What are you doing?' → 'Tu kya kar raha hai?'"
)

# Dictionary to track user jobs (for /cancel)
active_jobs = {}

# -------------------------------
# 🧠 Safe Message Sending (to avoid Markdown errors)
# -------------------------------
async def safe_send_message(bot, chat_id, text, **kwargs):
    """Safely send message with Markdown fallback."""
    try:
        await bot.send_message(chat_id, text, **kwargs)
    except Exception:
        # Retry without parse_mode if Telegram markdown fails
        await bot.send_message(chat_id, text, parse_mode=None)

# -------------------------------
# 🚀 Gemini Translation
# -------------------------------
def translate_to_hinglish_sync(text: str) -> str:
    """Blocking Gemini API translation (to run in background thread)."""
    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=[
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": f"{STYLE_GUIDE}\n\nTranslate the following text:\n{text}"
                        }
                    ],
                }
            ],
        )
        return response.text.strip() if response and response.text else "(No translation output)"
    except Exception as e:
        return f"⚠️ Translation failed: {e}"

async def translate_to_hinglish(text: str) -> str:
    """Async wrapper to avoid blocking event loop."""
    return await asyncio.to_thread(translate_to_hinglish_sync, text)

# -------------------------------
# 🏁 Command Handlers
# -------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome! Send me a photo, scanned page, or ZIP file for OCR + Hinglish translation.\n"
        "Use /cancel to stop a running job."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📘 *Available Commands:*\n"
        "/start - Welcome message\n"
        "/help - Show this message\n"
        "/cancel - Cancel running OCR/translation\n\n"
        "📄 *Usage:*\n"
        "• Send an image or ZIP file — I’ll extract the text and translate it into Hinglish.",
        parse_mode="Markdown",
    )

# -------------------------------
# ❌ Cancel Command
# -------------------------------
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel current OCR/translation for the user."""
    user_id = update.effective_user.id
    if user_id in active_jobs:
        job_task = active_jobs.pop(user_id)
        if not job_task.done():
            job_task.cancel()
            await update.message.reply_text("❌ OCR/Translation cancelled successfully.")
        else:
            await update.message.reply_text("⚠️ Task already completed.")
    else:
        await update.message.reply_text("⚠️ No active OCR/Translation to cancel.")

# -------------------------------
# 🖼️ Handle Image Upload
# -------------------------------
async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    photo = update.message.photo[-1]
    file = await photo.get_file()

    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        await file.download_to_drive(custom_path=tmp.name)
        image_path = tmp.name

    status_msg = await update.message.reply_text("🕵️ Running OCR... please wait.")
    active_jobs[user_id] = asyncio.current_task()

    try:
        ocr_text = pytesseract.image_to_string(Image.open(image_path))
        translated = await translate_to_hinglish(ocr_text)

        await safe_send_message(
            context.bot,
            update.effective_chat.id,
            f"📜 *Extracted Text:*\n\n{ocr_text.strip() or '(No text found)'}",
            parse_mode="Markdown",
        )

        await safe_send_message(
            context.bot,
            update.effective_chat.id,
            f"🌐 *Translated (Hinglish):*\n\n{translated}",
            parse_mode="Markdown",
        )

    except asyncio.CancelledError:
        await update.message.reply_text("❌ OCR process was cancelled.")
    except Exception as e:
        await update.message.reply_text(f"⚠️ Error during OCR: {e}")
    finally:
        if user_id in active_jobs:
            active_jobs.pop(user_id, None)
        os.remove(image_path)
        await status_msg.delete()

# -------------------------------
# 📦 Handle File Upload (.zip / .txt)
# -------------------------------
async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    document = update.message.document
    file_name = document.file_name.lower()

    if not any(file_name.endswith(ext) for ext in (".zip", ".7z", ".cbz", ".txt")):
        await update.message.reply_text("⚠️ Unsupported file type. Please upload a ZIP, CBZ, or TXT file.")
        return

    file = await document.get_file()

    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        await file.download_to_drive(custom_path=tmp.name)
        file_path = tmp.name

    active_jobs[user_id] = asyncio.current_task()
    status_msg = await update.message.reply_text("📦 Processing uploaded file... please wait.")

    extracted_text = ""
    try:
        if file_name.endswith(".txt"):
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                extracted_text = f.read()
        else:
            with zipfile.ZipFile(file_path, "r") as archive:
                for member in archive.namelist():
                    if member.lower().endswith((".png", ".jpg", ".jpeg")):
                        with archive.open(member) as img_file:
                            img = Image.open(img_file)
                            extracted_text += pytesseract.image_to_string(img) + "\n"

        if not extracted_text.strip():
            await update.message.reply_text("⚠️ No readable text found in the file.")
            return

        translated = await translate_to_hinglish(extracted_text)

        # Write result to temporary file
        output_file = tempfile.NamedTemporaryFile(delete=False, suffix=".txt")
        output_file.write(translated.encode("utf-8"))
        output_file.close()

        await context.bot.send_document(
            chat_id=update.effective_chat.id,
            document=open(output_file.name, "rb"),
            filename="translated_output.txt",
            caption="✅ OCR + Hinglish translation completed!",
        )

        os.remove(output_file.name)

    except asyncio.CancelledError:
        await update.message.reply_text("❌ Process cancelled.")
    except Exception as e:
        await update.message.reply_text(f"⚠️ Error: {e}")
    finally:
        if user_id in active_jobs:
            active_jobs.pop(user_id, None)
        os.remove(file_path)
        await status_msg.delete()
