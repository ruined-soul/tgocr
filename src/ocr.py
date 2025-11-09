# /src/ocr.py
import os
import zipfile
import py7zr
from PIL import Image, UnidentifiedImageError
import pytesseract
import logging
import aiohttp
from .handlers import user_settings

# --- OnlineOCR.net config ---
ONLINE_OCR_API_URL = "https://api.onlineocr.net/v1/ocr"
ONLINE_OCR_API_KEY = "A1833830-53E6-4EE8-BD63-5E5D8291A4FB"
ONLINE_OCR_USER_ID = "YOWEM"


async def ocr_image(image_path: str, ocr_mode: str = "local") -> str:
    """Perform OCR using local Tesseract or Online OCR API depending on mode."""
    if ocr_mode == "local":
        try:
            img = Image.open(image_path)
            return pytesseract.image_to_string(img)
        except Exception as e:
            logging.error(f"❌ Local OCR error: {e}")
            return ""
    else:
        try:
            async with aiohttp.ClientSession() as session:
                with open(image_path, "rb") as f:
                    form = aiohttp.FormData()
                    form.add_field("file", f, filename=os.path.basename(image_path))
                    form.add_field("apikey", ONLINE_OCR_API_KEY)
                    form.add_field("user", ONLINE_OCR_USER_ID)
                    async with session.post(ONLINE_OCR_API_URL, data=form) as resp:
                        if resp.status != 200:
                            logging.error(f"❌ Online OCR failed: {resp.status}")
                            return ""
                        data = await resp.json()
                        return data.get("text", "") or ""
        except Exception as e:
            logging.error(f"❌ Online OCR API error: {e}")
            return ""


async def process_archive(update, context, archive_path, temp_dir, active_jobs):
    chat_id = update.effective_chat.id
    extract_dir = os.path.join(temp_dir, "extracted")
    os.makedirs(extract_dir, exist_ok=True)

    logging.info(f"📂 Extracting archive: {archive_path}")

    try:
        if archive_path.endswith((".zip", ".cbz")):
            with zipfile.ZipFile(archive_path, "r") as z:
                z.extractall(extract_dir)
        elif archive_path.endswith(".7z"):
            with py7zr.SevenZipFile(archive_path, "r") as z:
                z.extractall(path=extract_dir)
        else:
            await update.message.reply_text("⚠️ Unsupported file format.")
            return
    except Exception as e:
        await update.message.reply_text(f"❌ Error extracting archive: {e}")
        logging.error(f"❌ Extraction error: {e}")
        return

    image_files = []
    for root, _, files in os.walk(extract_dir):
        for f in files:
            if f.lower().endswith((".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp")):
                image_files.append(os.path.join(root, f))

    if not image_files:
        await update.message.reply_text("⚠️ No images found inside the archive.")
        return

    await update.message.reply_text(f"🔍 Found {len(image_files)} image(s) — starting OCR...")

    ocr_mode = user_settings.get(chat_id, {}).get("ocr_mode", "local")
    all_text = ""

    for idx, img_path in enumerate(sorted(image_files), start=1):
        if chat_id in active_jobs and active_jobs[chat_id].get("cancel"):
            await update.message.reply_text("🛑 OCR process cancelled.")
            logging.info(f"🛑 OCR cancelled for chat {chat_id}")
            return

        filename = os.path.basename(img_path)
        try:
            text = await ocr_image(img_path, ocr_mode)
            text_out = text.strip() or "(No text detected)"
            all_text += f"\n\n--- {filename} ---\n{text_out}"

            if idx <= 3:
                await update.message.reply_text(
                    f"📄 *{filename}* ({idx}/{len(image_files)}):\n\n{text_out}",
                    parse_mode="Markdown"
                )
                if idx == 3:
                    await update.message.reply_text(
                        "🕐 Please wait — still processing remaining images..."
                    )
        except UnidentifiedImageError:
            logging.warning(f"⚠️ Skipping invalid image: {img_path}")
        except Exception as e:
            logging.error(f"⚠️ OCR error for {img_path}: {e}")
            await update.message.reply_text(f"⚠️ Error reading {filename}: {e}")

    if all_text.strip():
        base_name = os.path.splitext(os.path.basename(archive_path))[0]
        result_filename = f"{base_name}.txt"
        out_path = os.path.join(temp_dir, result_filename)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(all_text)
        await update.message.reply_document(
            document=open(out_path, "rb"),
            filename=result_filename,
            caption=f"✅ OCR complete — full text extracted from *{base_name}*.",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("⚠️ OCR complete, but no readable text was detected.")


async def process_single_image(update, context, image_path, active_jobs=None):
    """Run OCR on a single image and send extracted text."""
    chat_id = update.effective_chat.id
    ocr_mode = user_settings.get(chat_id, {}).get("ocr_mode", "local")
    try:
        if active_jobs and chat_id in active_jobs and active_jobs[chat_id].get("cancel"):
            await update.message.reply_text("🛑 OCR cancelled before start.")
            return

        text = (await ocr_image(image_path, ocr_mode)).strip()
        if not text:
            text = "(No text detected)"

        await update.message.reply_text(f"📝 *Extracted Text:*\n\n{text}", parse_mode="Markdown")
    except Exception as e:
        logging.error(f"❌ Single-image OCR error: {e}")
        await update.message.reply_text(f"❌ OCR error: {e}")
