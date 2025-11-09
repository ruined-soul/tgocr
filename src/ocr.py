# /src/ocr.py
import os
import zipfile
import py7zr
import aiohttp
import logging
from PIL import Image, UnidentifiedImageError
import pytesseract

# ============================================================
# 🔐 OCRWebService (REST API) credentials
# ============================================================
OCRWS_USERNAME = os.getenv("OCRWS_USERNAME", "")
OCRWS_LICENSE_KEY = os.getenv("OCRWS_LICENSE_KEY", "")
OCRWS_API_URL = "https://www.ocrwebservice.com/restservices/processDocument"

# ============================================================
# 🌍 OCRWebService.com REST API integration
# ============================================================
async def ocr_image_online(image_path: str) -> str:
    """
    Perform OCR using OCRWebService.com REST API (returns extracted text).
    """
    if not OCRWS_USERNAME or not OCRWS_LICENSE_KEY:
        logging.error("❌ OCRWebService credentials missing.")
        return "⚠️ OCRWebService credentials not configured."

    params = {
        "language": "english",
        "gettext": "true",
        "outputformat": "txt"
    }

    headers = {"Accept": "application/json"}

    try:
        async with aiohttp.ClientSession(
            auth=aiohttp.BasicAuth(OCRWS_USERNAME, OCRWS_LICENSE_KEY)
        ) as session:
            with open(image_path, "rb") as f:
                form = aiohttp.FormData()
                form.add_field("file", f, filename=os.path.basename(image_path))

                async with session.post(OCRWS_API_URL, params=params, data=form, headers=headers) as resp:
                    status = resp.status
                    text = await resp.text()

                    if status == 401:
                        logging.error("❌ Unauthorized: check your OCRWebService username/license key.")
                        return "⚠️ Invalid OCRWebService credentials."
                    if status == 402:
                        return "⚠️ Payment required or quota exceeded on OCRWebService account."
                    if status == 400:
                        logging.error(f"❌ Bad request: {text}")
                        return "⚠️ Bad OCR request (check file format or params)."
                    if status >= 500:
                        return "⚠️ OCRWebService internal error, please try later."

                    # Try JSON parse for OCRText
                    try:
                        data = await resp.json()
                        if data.get("ErrorMessage"):
                            return f"⚠️ OCR Error: {data['ErrorMessage']}"

                        ocr_text = ""
                        ocr_data = data.get("OCRText", [])
                        for zone_group in ocr_data:
                            for page_text in zone_group:
                                if page_text:
                                    ocr_text += page_text.strip() + "\n\n"

                        if not ocr_text.strip() and data.get("OutputFileUrl"):
                            ocr_text = f"📎 Result file: {data['OutputFileUrl']}"

                        return ocr_text.strip() or "⚠️ No text detected."

                    except Exception as parse_err:
                        logging.error(f"⚠️ Could not parse OCR JSON: {parse_err}")
                        return text.strip()

    except Exception as e:
        logging.error(f"❌ OCRWebService API request failed: {e}")
        return f"⚠️ Online OCR error: {e}"


# ============================================================
# 🧠 Local OCR via Tesseract
# ============================================================
def ocr_image_local(image_path: str) -> str:
    """Perform OCR locally using Tesseract."""
    try:
        img = Image.open(image_path)
        return pytesseract.image_to_string(img).strip()
    except Exception as e:
        logging.error(f"❌ Local OCR error: {e}")
        return ""


# ============================================================
# Unified interface for both OCR modes
# ============================================================
async def ocr_image(image_path: str, mode: str = "local") -> str:
    """Dispatch OCR by mode."""
    if mode == "online":
        return await ocr_image_online(image_path)
    return ocr_image_local(image_path)


# ============================================================
# Process archive (.zip/.7z/.cbz) of images
# ============================================================
async def process_archive(update, context, archive_path, temp_dir, active_jobs, ocr_mode_map):
    chat_id = update.effective_chat.id
    extract_dir = os.path.join(temp_dir, "extracted")
    os.makedirs(extract_dir, exist_ok=True)
    mode = ocr_mode_map.get(chat_id, "local")

    await update.message.reply_text(f"📦 Extracting archive — using *{mode.upper()}* OCR...", parse_mode="Markdown")

    try:
        if archive_path.endswith((".zip", ".cbz")):
            with zipfile.ZipFile(archive_path, "r") as z:
                z.extractall(extract_dir)
        elif archive_path.endswith(".7z"):
            with py7zr.SevenZipFile(archive_path, "r") as z:
                z.extractall(path=extract_dir)
        else:
            await update.message.reply_text("⚠️ Unsupported archive format.")
            return
    except Exception as e:
        await update.message.reply_text(f"❌ Error extracting archive: {e}")
        return

    image_files = []
    for root, _, files in os.walk(extract_dir):
        for f in files:
            if f.lower().endswith((".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp", ".gif")):
                image_files.append(os.path.join(root, f))

    if not image_files:
        await update.message.reply_text("⚠️ No images found inside the archive.")
        return

    all_text = ""
    for idx, img_path in enumerate(sorted(image_files), start=1):
        if chat_id in active_jobs and active_jobs[chat_id].get("cancel"):
            await update.message.reply_text("🛑 OCR cancelled.")
            return

        text = await ocr_image(img_path, mode)
        all_text += f"\n\n--- {os.path.basename(img_path)} ---\n{text}"

        if idx <= 2:
            await update.message.reply_text(
                f"📄 *{os.path.basename(img_path)}* ({idx}/{len(image_files)}):\n\n{text}",
                parse_mode="Markdown"
            )

    if all_text.strip():
        result_name = os.path.splitext(os.path.basename(archive_path))[0] + ".txt"
        result_path = os.path.join(temp_dir, result_name)
        with open(result_path, "w", encoding="utf-8") as f:
            f.write(all_text)
        await update.message.reply_document(
            document=open(result_path, "rb"),
            filename=result_name,
            caption=f"✅ OCR complete in *{mode.upper()}* mode.",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("⚠️ OCR complete, but no text detected.")


# ============================================================
# Process a single image
# ============================================================
async def process_single_image(update, context, image_path, active_jobs, ocr_mode_map):
    chat_id = update.effective_chat.id
    mode = ocr_mode_map.get(chat_id, "local")
    await update.message.reply_text(f"🖼️ Using *{mode.upper()}* OCR mode... Please wait.", parse_mode="Markdown")

    text = await ocr_image(image_path, mode)

    if len(text) > 3500:
        out_path = image_path + ".txt"
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(text)
        await update.message.reply_document(
            document=open(out_path, "rb"),
            filename=os.path.basename(out_path),
            caption="📄 OCR result (full text)"
        )
        os.remove(out_path)
    else:
        await update.message.reply_text(f"📄 *Extracted Text:*\n\n{text}", parse_mode="Markdown")
