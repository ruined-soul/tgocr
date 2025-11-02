import os
import zipfile
import py7zr
from PIL import Image, UnidentifiedImageError
import pytesseract
import logging

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

    all_text = ""
    for idx, img_path in enumerate(sorted(image_files), start=1):
        # --- Check for cancel flag ---
        if chat_id in active_jobs and active_jobs[chat_id].get("cancel"):
            await update.message.reply_text("🛑 OCR process cancelled.")
            logging.info(f"🛑 OCR cancelled for chat {chat_id}")
            return

        filename = os.path.basename(img_path)
        try:
            img = Image.open(img_path)
            text = pytesseract.image_to_string(img)
            text_out = text.strip() or "(No text detected)"
            all_text += f"\n\n--- {filename} ---\n{text_out}"

            if idx <= 3:
                await update.message.reply_text(
                    f"📄 *{filename}* ({idx}/{len(image_files)}):\n\n{text_out}",
                    parse_mode="Markdown"
                )

                if idx == 3:
                    await update.message.reply_text(
                        "🕐 Please wait — we’re still processing the remaining images. "
                        "You’ll receive the full result file soon."
                    )

        except UnidentifiedImageError:
            logging.warning(f"⚠️ Skipping invalid image: {img_path}")
        except Exception as e:
            logging.error(f"⚠️ OCR error for {img_path}: {e}")
            await update.message.reply_text(f"⚠️ Error reading {filename}: {e}")

    if all_text.strip():
        out_path = os.path.join(temp_dir, "OCR_Result.txt")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(all_text)
        await update.message.reply_document(
            document=open(out_path, "rb"),
            filename="OCR_Result.txt",
            caption="✅ OCR complete — full text extracted."
        )
    else:
        await update.message.reply_text("⚠️ OCR complete, but no readable text was detected.")
