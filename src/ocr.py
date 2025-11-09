# /src/ocr.py
import os
import zipfile
import py7zr
from PIL import Image, UnidentifiedImageError
import pytesseract
import logging
import aiohttp
import asyncio

ONLINEOCR_USERNAME = os.getenv("ONLINEOCR_USERNAME", "YOWEM")
ONLINEOCR_LICENSE_KEY = os.getenv("ONLINEOCR_LICENSE_KEY", "A1833830-53E6-4EE8-BD63-5E5D8291A4FB")

# ============================================================
# 🧠 LOCAL (TESSERACT) OCR
# ============================================================

async def process_archive(update, context, archive_path, temp_dir, active_jobs):
    chat_id = update.effective_chat.id
    extract_dir = os.path.join(temp_dir, "extracted")
    os.makedirs(extract_dir, exist_ok=True)
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
        return await update.message.reply_text(f"❌ Extraction error: {e}")

    image_files = [
        os.path.join(root, f)
        for root, _, files in os.walk(extract_dir)
        for f in files if f.lower().endswith((".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"))
    ]
    if not image_files:
        return await update.message.reply_text("⚠️ No images found.")

    await update.message.reply_text(f"🔍 Found {len(image_files)} images — starting OCR (Tesseract)...")
    all_text = ""

    for idx, img_path in enumerate(sorted(image_files), start=1):
        if chat_id in active_jobs and active_jobs[chat_id].get("cancel"):
            return await update.message.reply_text("🛑 OCR cancelled.")
        try:
            img = Image.open(img_path)
            text = pytesseract.image_to_string(img)
            all_text += f"\n\n--- {os.path.basename(img_path)} ---\n{text.strip()}"
        except Exception as e:
            await update.message.reply_text(f"⚠️ OCR error on {img_path}: {e}")
        if idx % 5 == 0:
            await update.message.reply_text(f"📄 Processed {idx}/{len(image_files)} pages...")

    result_file = os.path.join(temp_dir, os.path.splitext(os.path.basename(archive_path))[0] + ".txt")
    with open(result_file, "w", encoding="utf-8") as f:
        f.write(all_text)
    await update.message.reply_document(open(result_file, "rb"), caption="✅ OCR complete (Tesseract)")

async def process_single_image(update, image_path):
    try:
        img = Image.open(image_path)
        text = pytesseract.image_to_string(img).strip() or "(No readable text found)"
        await update.message.reply_text(f"📄 *Extracted Text (Tesseract):*\n\n{text}", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ OCR error: {e}")

# ============================================================
# 🌐 ONLINEOCR.NET API
# ============================================================

async def onlineocr_extract(image_path: str) -> str:
    api_url = "https://www.onlineocr.net/api/ocr"
    try:
        async with aiohttp.ClientSession() as session:
            form = aiohttp.FormData()
            form.add_field("username", ONLINEOCR_USERNAME)
            form.add_field("licensecode", ONLINEOCR_LICENSE_KEY)
            form.add_field("language", "eng")
            form.add_field("isoverlayrequired", "false")
            form.add_field("file", open(image_path, "rb"), filename=os.path.basename(image_path))
            async with session.post(api_url, data=form) as resp:
                text = await resp.text()
                if "Error" in text:
                    return f"⚠️ {text}"
                return text.strip() or "(No readable text found)"
    except Exception as e:
        return f"❌ OnlineOCR API error: {e}"

async def process_single_image_online(update, image_path):
    await update.message.reply_text("🌐 Using OnlineOCR.net for text extraction...")
    text = await onlineocr_extract(image_path)
    await update.message.reply_text(f"📄 *Extracted Text (OnlineOCR):*\n\n{text}", parse_mode="Markdown")

async def process_archive_online(update, context, archive_path, temp_dir, active_jobs):
    chat_id = update.effective_chat.id
    extract_dir = os.path.join(temp_dir, "extracted")
    os.makedirs(extract_dir, exist_ok=True)
    try:
        if archive_path.endswith((".zip", ".cbz")):
            with zipfile.ZipFile(archive_path, "r") as z:
                z.extractall(extract_dir)
        elif archive_path.endswith(".7z"):
            with py7zr.SevenZipFile(archive_path, "r") as z:
                z.extractall(path=extract_dir)
    except Exception as e:
        return await update.message.reply_text(f"❌ Extraction error: {e}")

    image_files = [
        os.path.join(root, f)
        for root, _, files in os.walk(extract_dir)
        for f in files if f.lower().endswith((".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"))
    ]
    if not image_files:
        return await update.message.reply_text("⚠️ No images found.")

    await update.message.reply_text(f"🌐 Found {len(image_files)} images — using OnlineOCR.net...")
    all_text = ""
    for idx, img_path in enumerate(sorted(image_files), start=1):
        if chat_id in active_jobs and active_jobs[chat_id].get("cancel"):
            return await update.message.reply_text("🛑 OCR cancelled.")
        text = await onlineocr_extract(img_path)
        all_text += f"\n\n--- {os.path.basename(img_path)} ---\n{text}"
        if idx % 3 == 0:
            await update.message.reply_text(f"🌐 Processed {idx}/{len(image_files)} pages...")
        await asyncio.sleep(1.2)

    result_file = os.path.join(temp_dir, os.path.splitext(os.path.basename(archive_path))[0] + "_online.txt")
    with open(result_file, "w", encoding="utf-8") as f:
        f.write(all_text)
    await update.message.reply_document(open(result_file, "rb"), caption="✅ OCR complete (OnlineOCR.net)")
