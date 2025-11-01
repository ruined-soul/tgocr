import os
import zipfile
import py7zr
from PIL import Image
import pytesseract
from .utils import safe_listdir

async def process_archive(update, context, archive_path, temp_dir):
    extract_dir = os.path.join(temp_dir, "extracted")
    os.makedirs(extract_dir, exist_ok=True)

    if archive_path.endswith(".zip"):
        with zipfile.ZipFile(archive_path, "r") as z:
            z.extractall(extract_dir)
    elif archive_path.endswith((".7z", ".cz")):
        with py7zr.SevenZipFile(archive_path, "r") as z:
            z.extractall(path=extract_dir)

    files = [f for f in safe_listdir(extract_dir) if f.lower().endswith((".jpg", ".jpeg", ".png", ".bmp", ".tiff"))]
    files.sort()

    if not files:
        await update.message.reply_text("⚠️ No images found.")
        return

    await update.message.reply_text(f"🔍 Found {len(files)} images — starting OCR...")

    for img_name in files:
        path = os.path.join(extract_dir, img_name)
        try:
            text = pytesseract.image_to_string(Image.open(path))
            text_out = text.strip() or "(No text detected)"
            await update.message.reply_text(f"📄 *{img_name}*:\n\n{text_out}", parse_mode="Markdown")
        except Exception as e:
            await update.message.reply_text(f"⚠️ Error reading {img_name}: {e}")
