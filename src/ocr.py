import os
import zipfile
import py7zr
from PIL import Image
import pytesseract
from .utils import safe_listdir

async def process_archive(update, context, archive_path, temp_dir):
    extract_dir = os.path.join(temp_dir, "extracted")
    os.makedirs(extract_dir, exist_ok=True)

    print(f"📂 Extracting archive: {archive_path}")

    # --- Handle different formats ---
    if archive_path.endswith((".zip", ".cbz")):
        try:
            with zipfile.ZipFile(archive_path, "r") as z:
                z.extractall(extract_dir)
        except Exception as e:
            await update.message.reply_text(f"❌ Error extracting ZIP/CBZ: {e}")
            print(f"❌ ZIP/CBZ extract error: {e}")
            return

    elif archive_path.endswith(".7z"):
        try:
            with py7zr.SevenZipFile(archive_path, "r") as z:
                z.extractall(path=extract_dir)
        except Exception as e:
            await update.message.reply_text(f"❌ Error extracting 7z archive: {e}")
            print(f"❌ 7z extract error: {e}")
            return

    else:
        await update.message.reply_text("⚠️ Unsupported file format.")
        return

    # --- List all files recursively ---
    all_files = []
    for root, _, files in os.walk(extract_dir):
        for f in files:
            all_files.append(os.path.join(root, f))

    print(f"📄 Extracted files ({len(all_files)}): {all_files}")

    image_files = [
        f for f in all_files
        if f.lower().endswith((".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"))
    ]

    if not image_files:
        await update.message.reply_text("⚠️ No images found inside the archive.")
        print("⚠️ No image files detected.")
        return

    await update.message.reply_text(f"🔍 Found {len(image_files)} image(s) — starting OCR...")

    # --- OCR each image ---
    for idx, img_path in enumerate(sorted(image_files), start=1):
        try:
            img = Image.open(img_path)
            text = pytesseract.image_to_string(img)
            text_out = text.strip() or "(No text detected)"
            filename = os.path.basename(img_path)
            await update.message.reply_text(
                f"📄 *{filename}* ({idx}/{len(image_files)}):\n\n{text_out}",
                parse_mode="Markdown"
            )
        except Exception as e:
            await update.message.reply_text(f"⚠️ Error reading {os.path.basename(img_path)}: {e}")
            print(f"⚠️ OCR error for {img_path}: {e}")
